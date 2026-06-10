# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/tools/security.py
"""Lot 4 — Security tools 33-38.

All tools are C3 (classification 3 = analysis/reporting, no external calls,
no live infrastructure changes). Tools never execute untrusted code.

Tool 33: audit_code_no_network — static AST analysis
Tool 34: audit_dockerfile_security — Dockerfile lint
Tool 35: scan_data_leakage_risk — sanitize-based log scan
Tool 36: verify_model_license — registry lookup
Tool 37: generate_security_report — aggregate → Markdown + optional PDF
Tool 38: sanitize_logs_for_claude — thin sanitize_text wrapper
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ..envelope import fail, ok
from ..render import markdown_file_to_pdf, sha256_file, write_text_atomic
from ..sanitize import sanitize_text
from ..store import Store, workspace_root

# ---------------------------------------------------------------------------
# Tool 33: audit_code_no_network (C3 — static AST only)
# ---------------------------------------------------------------------------

_NETWORK_MODULES = frozenset(
    [
        "socket",
        "urllib",
        "urllib.request",
        "requests",
        "httpx",
        "http.client",
        "ftplib",
        "smtplib",
        "asyncio",  # includes asyncio streams
    ]
)
_SUBPROCESS_NETWORK_TOOLS = frozenset(["curl", "wget"])

# Attribute calls that indicate network usage
_NETWORK_ATTRS: dict[str, frozenset[str]] = {
    "socket": frozenset(["connect", "create_connection", "socket"]),
    "urllib": frozenset(["urlopen", "urlretrieve"]),
    "requests": frozenset(["get", "post", "put", "delete", "patch", "head", "request", "Session"]),
    "httpx": frozenset(["get", "post", "put", "delete", "patch", "Client", "AsyncClient"]),
}


class _NetworkVisitor(ast.NodeVisitor):
    """Walk an AST and record network-related findings."""

    def __init__(self, source_lines: list[str], allowlist: frozenset[str]) -> None:
        self.findings: list[dict[str, Any]] = []
        self._lines = source_lines
        self._allowlist = allowlist

    def _add(self, lineno: int, kind: str, detail: str) -> None:
        self.findings.append({"line": lineno, "kind": kind, "detail": detail})

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        # FIX #1: use `continue` (not `return`) so all aliases in the same
        # statement are checked independently (e.g. `import asyncio, requests`
        # with allowlist=["asyncio"] must still flag `requests`).
        for alias in node.names:
            mod = alias.name
            if mod in self._allowlist:
                continue
            root = mod.split(".")[0]
            if mod in _NETWORK_MODULES or root in _NETWORK_MODULES:
                self._add(node.lineno, "network_import", f"import {mod}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        mod = node.module or ""
        if mod in self._allowlist:
            self.generic_visit(node)
            return
        root = mod.split(".")[0]
        if mod in _NETWORK_MODULES or root in _NETWORK_MODULES:
            self._add(node.lineno, "network_import", f"from {mod} import ...")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # Detect attr calls: requests.get(...), httpx.post(...), etc.
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if isinstance(node.func.value, ast.Name):
                obj = node.func.value.id
                if obj in _NETWORK_ATTRS and attr in _NETWORK_ATTRS[obj]:
                    if obj not in self._allowlist:
                        self._add(node.lineno, "network_call", f"{obj}.{attr}()")
            # urllib.request.urlopen style (chained attr)
            if attr == "urlopen":
                self._add(node.lineno, "network_call", "*.urlopen()")

        # subprocess calls that invoke network tools
        if isinstance(node.func, ast.Attribute) and node.func.attr in (
            "run",
            "call",
            "check_call",
            "check_output",
            "Popen",
        ):
            for arg in ast.walk(node):
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    for tool in _SUBPROCESS_NETWORK_TOOLS:
                        if tool in arg.value:
                            self._add(
                                node.lineno, "subprocess_network", f"subprocess with '{tool}'"
                            )
                            break
        self.generic_visit(node)


def audit_code_no_network(
    source: str | None = None,
    code_path: str | None = None,
    allowlist: list[str] | None = None,
) -> dict[str, Any]:
    """Static AST analysis — flag network imports and calls. No code execution.

    Accepts either `source` (Python source string) or `code_path` (file path).
    `allowlist` is a list of module names that are permitted.
    Returns findings [{line, kind, detail}] + verdict (clean|violations).
    """
    if source is None and code_path is None:
        return fail("Provide either 'source' or 'code_path'").to_dict()

    allowed = frozenset(allowlist or [])

    # Load source
    if source is None:
        p = Path(code_path)  # type: ignore[arg-type]
        if not p.exists():
            return fail(f"file not found: {code_path}").to_dict()
        try:
            source = p.read_text(encoding="utf-8")
        except OSError as exc:
            return fail(str(exc)).to_dict()

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return fail(f"syntax error: {exc}").to_dict()

    lines = source.splitlines()
    visitor = _NetworkVisitor(source_lines=lines, allowlist=allowed)
    visitor.visit(tree)

    findings = visitor.findings
    verdict = "clean" if not findings else "violations"
    return ok({"findings": findings, "verdict": verdict, "num_findings": len(findings)}).to_dict()


# ---------------------------------------------------------------------------
# Tool 34: audit_dockerfile_security (C3)
# ---------------------------------------------------------------------------

_SECRET_NAME_RE = re.compile(r"(?i)(secret|token|password|api[_-]?key)")
_NETWORK_FETCH_RE = re.compile(
    r"(curl\s+\S*\s*\|\s*(ba)?sh|wget\s+\S*\s*\|\s*(ba)?sh)", re.IGNORECASE
)
_ADD_HTTP_RE = re.compile(r"^ADD\s+https?://", re.IGNORECASE)
_NO_CHECK_CERT_RE = re.compile(r"--no-check-certificate", re.IGNORECASE)


def _parse_dockerfile(text: str) -> list[tuple[int, str, str]]:
    """Parse Dockerfile into [(lineno, instruction, rest)] skipping comments."""
    instructions = []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        instr = parts[0].upper()
        rest = parts[1] if len(parts) > 1 else ""
        instructions.append((i, instr, rest))
    return instructions


def _check_from_instruction(
    lineno: int, rest: str, findings: list[dict[str, Any]], has_from: list[bool]
) -> None:
    """Check FROM instruction for unpinned base images."""
    has_from[0] = True
    image = rest.split()[0] if rest.split() else ""
    if image.endswith(":latest"):
        findings.append(
            {
                "line": lineno,
                "kind": "unpinned_image",
                "detail": f"Base image uses ':latest' tag: {image}",
                "severity": "high",
            }
        )
    elif ":" not in image and "@" not in image:
        findings.append(
            {
                "line": lineno,
                "kind": "unpinned_image",
                "detail": f"Base image has no tag or digest: {image}",
                "severity": "high",
            }
        )


def _check_env_arg_instruction(
    lineno: int, instr: str, rest: str, findings: list[dict[str, Any]]
) -> None:
    """Check ENV/ARG instructions for secret-looking names."""
    for token in rest.split():
        name = token.split("=")[0]
        if _SECRET_NAME_RE.search(name):
            findings.append(
                {
                    "line": lineno,
                    "kind": "secret_in_env",
                    "detail": f"{instr} uses secret-looking name: {name}",
                    "severity": "critical",
                }
            )


def _check_run_instruction(lineno: int, rest: str, findings: list[dict[str, Any]]) -> None:
    """Check RUN instructions for unsafe network fetches and cert bypasses."""
    if _NETWORK_FETCH_RE.search(rest):
        findings.append(
            {
                "line": lineno,
                "kind": "pipe_install",
                "detail": f"RUN pipes network content to shell: {rest[:80]}",
                "severity": "critical",
            }
        )
    if _NO_CHECK_CERT_RE.search(rest):
        findings.append(
            {
                "line": lineno,
                "kind": "no_cert_check",
                "detail": "RUN uses --no-check-certificate",
                "severity": "high",
            }
        )


def _check_dockerfile_instruction(
    lineno: int,
    instr: str,
    rest: str,
    findings: list[dict[str, Any]],
    last_user: list[str | None],
    has_from: list[bool],
) -> None:
    """Dispatch a single Dockerfile instruction to the appropriate checker."""
    if instr == "FROM":
        _check_from_instruction(lineno, rest, findings, has_from)
    elif instr == "USER":
        # FIX #3: track LAST user, not a boolean flag
        last_user[0] = rest.strip().split(":")[0]
    elif instr in ("ENV", "ARG"):
        _check_env_arg_instruction(lineno, instr, rest, findings)
    elif instr == "ADD":
        if _ADD_HTTP_RE.match(f"ADD {rest}"):
            findings.append(
                {
                    "line": lineno,
                    "kind": "network_fetch",
                    "detail": f"ADD fetches over HTTP/HTTPS: {rest[:80]}",
                    "severity": "high",
                }
            )
    elif instr == "RUN":
        _check_run_instruction(lineno, rest, findings)


def audit_dockerfile_security(
    dockerfile_text: str | None = None,
    dockerfile_path: str | None = None,
) -> dict[str, Any]:
    """Parse a Dockerfile and flag security issues.

    Checks: missing non-root USER, unpinned base image, secrets in ENV/ARG,
    ADD/RUN fetching over network, --no-check-certificate.
    """
    if dockerfile_text is None and dockerfile_path is None:
        return fail("Provide either 'dockerfile_text' or 'dockerfile_path'").to_dict()

    if dockerfile_text is None:
        p = Path(dockerfile_path)  # type: ignore[arg-type]
        if not p.exists():
            return fail(f"file not found: {dockerfile_path}").to_dict()
        try:
            dockerfile_text = p.read_text(encoding="utf-8")
        except OSError as exc:
            return fail(str(exc)).to_dict()

    instructions = _parse_dockerfile(dockerfile_text)
    findings: list[dict[str, Any]] = []

    # FIX #3: use mutable containers so the helper can update them
    last_user: list[str | None] = [None]
    has_from: list[bool] = [False]

    for lineno, instr, rest in instructions:
        _check_dockerfile_instruction(lineno, instr, rest, findings, last_user, has_from)

    # FIX #3: flag if the LAST user instruction ends up as root (or there is none)
    if has_from[0] and last_user[0] in (None, "0", "root"):
        findings.append(
            {
                "line": 0,
                "kind": "runs_as_root",
                "detail": "No non-root USER instruction found — container runs as root",
                "severity": "high",
            }
        )

    verdict = "clean" if not findings else "violations"
    return ok({"findings": findings, "verdict": verdict, "num_findings": len(findings)}).to_dict()


# ---------------------------------------------------------------------------
# Tool 35: scan_data_leakage_risk (C3)
# ---------------------------------------------------------------------------

_LEAKAGE_CATEGORIES = {
    "credential_url": re.compile(r"\[REDACTED:URL_CRED\]"),
    "email": re.compile(r"\[REDACTED:EMAIL\]"),
    "ip_address": re.compile(r"\[REDACTED:IP\]"),
    "blob_token": re.compile(r"\[REDACTED:BLOB\]"),
}


def scan_data_leakage_risk(
    text: str | None = None,
    logs_path: str | None = None,
) -> dict[str, Any]:
    """Scan logs/artifacts for real-text leakage using sanitize_text heuristics.

    Reports categories and counts of would-be-leaked items WITHOUT echoing
    raw sensitive strings.
    """
    if text is None and logs_path is None:
        return fail("Provide either 'text' or 'logs_path'").to_dict()

    if text is None:
        p = Path(logs_path)  # type: ignore[arg-type]
        if not p.exists():
            return fail(f"file not found: {logs_path}").to_dict()
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            return fail(str(exc)).to_dict()

    _masked, total_masked = sanitize_text(text)

    if total_masked == 0:
        return ok(
            {
                "risk": "none",
                "total_masked": 0,
                "categories": {},
                "note": "No sensitive patterns detected",
            }
        ).to_dict()

    # Count by category from masked output
    category_counts: dict[str, int] = {}
    for cat, pattern in _LEAKAGE_CATEGORIES.items():
        count = len(pattern.findall(_masked))
        if count > 0:
            category_counts[cat] = count

    risk_level = "high" if total_masked >= 5 else "medium" if total_masked >= 2 else "low"

    return ok(
        {
            "risk": risk_level,
            "total_masked": total_masked,
            "categories": category_counts,
            "note": "Raw sensitive values are NOT echoed — review source before sharing logs",
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 36: verify_model_license (C3 — in-module registry)
# ---------------------------------------------------------------------------

_LICENSE_REGISTRY: list[dict[str, Any]] = [
    {
        "pattern": "qwen",
        "license": "Apache-2.0",
        "commercial_ok": True,
        "notes": "Apache-2.0 — safe for commercial use",
    },
    {
        "pattern": "mistral",
        "license": "Apache-2.0",
        "commercial_ok": True,
        "notes": "Apache-2.0 (Small/7B/8x7B) — verify tier for Medium/Large variants",
    },
    {
        "pattern": "deepseek",
        "license": "MIT",
        "commercial_ok": True,
        "notes": "MIT license — safe for commercial use",
    },
    {
        "pattern": "glm",
        "license": "MIT",
        "commercial_ok": True,
        "notes": "MIT license — safe for commercial use",
    },
    {
        "pattern": "zhipu",
        "license": "MIT",
        "commercial_ok": True,
        "notes": "MIT license — safe for commercial use",
    },
    {
        "pattern": "phi",
        "license": "MIT",
        "commercial_ok": True,
        "notes": "MIT license — safe for commercial use",
    },
    {
        "pattern": "gemma",
        "license": "Gemma license (restrictions)",
        "commercial_ok": True,
        "notes": "Commercial use allowed but read Gemma terms — usage limits and attribution apply",
    },
    {
        "pattern": "llama",
        "license": "Llama Community License",
        "commercial_ok": True,
        "notes": "Commercial use allowed — MAU thresholds/attribution required; audit before deployment",
    },
    {
        "pattern": "kimi",
        "license": "check",
        "commercial_ok": None,
        "notes": "Frontier model — verify current license directly with Moonshot AI",
    },
]


def verify_model_license(repo_id: str) -> dict[str, Any]:
    """Look up the base-model license from the in-module registry.

    Matches by substring (case-insensitive). Unknown models → manual review.
    """
    if not repo_id or not repo_id.strip():
        return fail("repo_id must not be empty").to_dict()

    lower = repo_id.lower()
    for entry in _LICENSE_REGISTRY:
        if entry["pattern"] in lower:
            return ok(
                {
                    "repo_id": repo_id,
                    "license": entry["license"],
                    "commercial_ok": entry["commercial_ok"],
                    "notes": entry["notes"],
                }
            ).to_dict()

    return ok(
        {
            "repo_id": repo_id,
            "license": "unknown",
            "commercial_ok": None,
            "notes": "Unknown model — manual review required before commercial use",
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 37: generate_security_report (C1)
# ---------------------------------------------------------------------------


def _get_store(store: Store | None) -> Store:
    return store if store is not None else Store(root=workspace_root())


def _append_code_audit_section(sections: list[str], code_audit: dict[str, Any]) -> None:
    """Append the code audit section to sections list."""
    if code_audit:
        verdict = code_audit.get("verdict", "N/A")
        num = code_audit.get("num_findings", 0)
        sections.append(
            f"## Code Audit (no-network)\n\n- Verdict: **{verdict}**\n- Findings: {num}\n"
        )
        for f_item in code_audit.get("findings", []):
            sections.append(
                f"  - Line {f_item.get('line')}: `{f_item.get('kind')}` — {f_item.get('detail')}\n"
            )
    else:
        sections.append("## Code Audit (no-network)\n\n_Not run._\n")


def _append_dockerfile_section(sections: list[str], df_audit: dict[str, Any]) -> None:
    """Append the Dockerfile audit section to sections list."""
    if df_audit:
        verdict = df_audit.get("verdict", "N/A")
        num = df_audit.get("num_findings", 0)
        sections.append(f"## Dockerfile Security\n\n- Verdict: **{verdict}**\n- Findings: {num}\n")
        for f_item in df_audit.get("findings", []):
            sev = f_item.get("severity", "info")
            sections.append(
                f"  - [{sev.upper()}] Line {f_item.get('line')}: `{f_item.get('kind')}` — {f_item.get('detail')}\n"
            )
    else:
        sections.append("## Dockerfile Security\n\n_Not run._\n")


def _append_leakage_section(sections: list[str], leakage: dict[str, Any]) -> None:
    """Append the data leakage scan section to sections list."""
    if leakage:
        risk = leakage.get("risk", "N/A")
        total = leakage.get("total_masked", 0)
        sections.append(
            f"## Data Leakage Scan\n\n- Risk level: **{risk}**\n- Items masked: {total}\n"
        )
        for cat, cnt in leakage.get("categories", {}).items():
            sections.append(f"  - {cat}: {cnt}\n")
    else:
        sections.append("## Data Leakage Scan\n\n_Not run._\n")


def _append_license_section(sections: list[str], license_info: dict[str, Any]) -> None:
    """Append the model license section to sections list."""
    if license_info:
        sections.append(
            f"## Model License\n\n"
            f"- repo_id: `{license_info.get('repo_id')}`\n"
            f"- License: {license_info.get('license')}\n"
            f"- Commercial OK: {license_info.get('commercial_ok')}\n"
            f"- Notes: {license_info.get('notes')}\n"
        )
    else:
        sections.append("## Model License\n\n_Not run._\n")


def generate_security_report(
    project_id: str,
    findings: dict[str, Any] | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Aggregate security audit results into a Markdown report with optional PDF.

    Writes under <project>/reports/security_report.md (and .pdf if WeasyPrint
    available). Returns paths + SHA256.
    """
    if not project_id or not project_id.strip():
        return fail("project_id must not be empty").to_dict()

    s = _get_store(store)
    try:
        pdir = s.project_dir(project_id)
    except ValueError as exc:
        return fail(str(exc)).to_dict()

    findings = findings or {}

    sections = [f"# Security Report — Project `{project_id}`\n"]
    _append_code_audit_section(sections, findings.get("code_audit", {}))
    _append_dockerfile_section(sections, findings.get("dockerfile_audit", {}))
    _append_leakage_section(sections, findings.get("leakage_scan", {}))
    _append_license_section(sections, findings.get("license", {}))

    md_content = "\n".join(sections)

    reports_dir = pdir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    md_path = reports_dir / "security_report.md"

    try:
        write_text_atomic(md_path, md_content)
    except OSError as exc:
        return fail(f"failed to write report: {exc}").to_dict()

    # FIX #5: guard sha256_file against OSError
    try:
        sha = sha256_file(md_path)
    except OSError as exc:
        return fail(f"failed to hash report: {exc}").to_dict()

    result: dict[str, Any] = {"md_path": str(md_path), "sha256": sha}

    # Optional PDF — skip gracefully if WeasyPrint absent
    pdf_path = reports_dir / "security_report.pdf"
    try:
        markdown_file_to_pdf(md_path, pdf_path)
        result["pdf_path"] = str(pdf_path)
    except ImportError:
        result["pdf_path"] = None
        result["pdf_note"] = "WeasyPrint not installed — PDF skipped"
    except Exception as exc:  # noqa: BLE001  # broad catch for optional-PDF degradation
        result["pdf_path"] = None
        result["pdf_note"] = f"PDF generation failed: {exc}"

    return ok(result).to_dict()


# MCP wrapper — keep signature in sync with generate_security_report
def _mcp_generate_security_report(
    project_id: str,
    findings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return generate_security_report(project_id=project_id, findings=findings)


# ---------------------------------------------------------------------------
# Tool 38: sanitize_logs_for_claude (C3 — thin sanitize_text wrapper)
# ---------------------------------------------------------------------------


def sanitize_logs_for_claude(
    text: str | None = None,
    log_path: str | None = None,
) -> dict[str, Any]:
    """Sanitize text or a log file via sanitize_text.

    Returns {sanitized, masked_count}. Unlike scan_data_leakage_risk, this
    tool IS allowed to return the sanitized body — that is its purpose.
    """
    if text is None and log_path is None:
        return fail("Provide either 'text' or 'log_path'").to_dict()

    if text is None:
        p = Path(log_path)  # type: ignore[arg-type]
        if not p.exists():
            return fail(f"file not found: {log_path}").to_dict()
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            return fail(str(exc)).to_dict()

    sanitized, masked_count = sanitize_text(text)
    return ok({"sanitized": sanitized, "masked_count": masked_count}).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration
# ---------------------------------------------------------------------------

_MCP_TOOLS = [
    (
        audit_code_no_network,
        "Static AST analysis of Python source — flag network imports/calls without executing code.",
    ),
    (
        audit_dockerfile_security,
        "Parse a Dockerfile and flag: root user, unpinned images, secrets in ENV/ARG, network fetches.",
    ),
    (
        scan_data_leakage_risk,
        "Scan logs/artifacts for sensitive data leakage — reports counts by category, never raw values.",
    ),
    (
        verify_model_license,
        "Look up base-model license and commercial-use compatibility from the in-module registry.",
    ),
    (
        _mcp_generate_security_report,
        "Aggregate security audit results into a Markdown (+ optional PDF) report for a project.",
    ),
    (
        sanitize_logs_for_claude,
        "Sanitize text or a log file via pattern masking — returns the sanitized body and masked count.",
    ),
]


def register(mcp: Any) -> None:
    """Register all security tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)
