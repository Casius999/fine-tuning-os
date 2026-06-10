# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/tools/client.py
"""Lot 6 — Client relationship tools 55-60.

C1 tools (55, 58, 59, 60): offline, deterministic, store-backed.
C2 tools (56 send_status_update — smtp|slack, 57 schedule_meeting — calendly).

C2 contract:
  configured, meta = gate(kind)
  command/message = <exact runnable string>  # ALWAYS computed
  not configured → ok({message/command:..., ...}, **meta)  # dry_run, no network
  configured → real action via _get_target_config(kind), sanitize external text,
               never put secret VALUES in output (env NAME refs only).

Never raise to caller — wrap I/O in try/except and return fail(str(exc)).
"""

from __future__ import annotations

import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httpx

from ..envelope import fail, ok
from ..render import markdown_file_to_pdf, sha256_bytes, write_text_atomic
from ..sanitize import sanitize_text
from ..store import Store, workspace_root
from ..targets import _get_target_config, gate
from ..templating import render_template

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_store(store: Store | None) -> Store:
    return store if store is not None else Store(root=workspace_root())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(company: str) -> str:
    """Convert company name to a filesystem-safe project_id slug."""
    return "".join(c if c.isalnum() else "_" for c in company).strip("_").lower()[:40]


def _try_pdf(md_path: Path) -> tuple[str | None, str | None]:
    """Attempt to produce a PDF; return (pdf_path_str, error_or_skip_msg)."""
    try:
        pdf_path = md_path.with_suffix(".pdf")
        markdown_file_to_pdf(md_path, pdf_path)
        return str(pdf_path), None
    except ImportError:
        return None, "weasyprint not installed"
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


# ---------------------------------------------------------------------------
# C2 private helpers for send_status_update
# ---------------------------------------------------------------------------


def _send_smtp(
    cfg: dict[str, Any],
    subject: str,
    rendered: str,
    recipient: str | None,
    smtp_meta: dict[str, Any],
) -> dict[str, Any]:
    """Send a status update via SMTP and return an envelope dict.

    Port is read from FTOS_SMTP_PORT (default 587). When FTOS_SMTP_PASSWORD is
    absent or empty the STARTTLS + login steps are skipped so the tool can talk
    to a plain (no-auth) sink — useful for local integration testing with
    aiosmtpd.
    """
    import os

    try:
        port = int(os.environ.get("FTOS_SMTP_PORT", "587"))
        password = cfg.get("FTOS_SMTP_PASSWORD", "")
        use_auth = bool(password)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = cfg["FTOS_SMTP_USER"]
        msg["To"] = recipient or cfg["FTOS_SMTP_USER"]
        msg.attach(MIMEText(rendered, "plain", "utf-8"))

        with smtplib.SMTP(cfg["FTOS_SMTP_HOST"], port, timeout=30) as server:
            if use_auth:
                server.starttls()
                server.login(cfg["FTOS_SMTP_USER"], password)
            server.send_message(msg)

        return ok(
            {
                "message": rendered,
                "channel": "smtp",
                "host_env": "FTOS_SMTP_HOST",
                "recipient": recipient or "[FTOS_SMTP_USER]",
            },
            **smtp_meta,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        return fail(f"smtp error: {exc}").to_dict()


def _send_slack(
    cfg: dict[str, Any],
    subject: str,
    body: str,
    rendered: str,
    slack_meta: dict[str, Any],
) -> dict[str, Any]:
    """Post a status update to a Slack webhook and return an envelope dict."""
    try:
        resp = httpx.post(
            cfg["FTOS_SLACK_WEBHOOK"],
            json={"text": f"*{subject}*\n\n{body}"},
            timeout=10,
        )
        resp.raise_for_status()
        raw = resp.text
        sanitized, _ = sanitize_text(raw)
        return ok(
            {
                "message": rendered,
                "channel": "slack",
                "webhook_env": "FTOS_SLACK_WEBHOOK",
                "response": sanitized,
            },
            **slack_meta,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        return fail(f"slack error: {exc}").to_dict()


def _render_status_update(project_id: str, subject: str, body: str) -> tuple[str | None, str]:
    """Render the status_update template. Returns (rendered, error_or_empty)."""
    try:
        rendered = render_template(
            "business/status_update.md.j2",
            project_id=project_id,
            date=_now_iso(),
            status=subject,
            progression=None,
            completed_items=[body],
            in_progress_items=[],
            next_steps=[],
            risques=[],
            metriques={},
        )
        return rendered, ""
    except Exception as exc:  # noqa: BLE001
        return None, f"template error: {exc}"


def _fetch_calendly_slots(
    cfg: dict[str, Any],
    dry_command: str,
    duration: int,
    window: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Call the Calendly API and return an envelope dict."""
    try:
        resp = httpx.get(
            "https://api.calendly.com/event_types",
            headers={
                "Authorization": f"Bearer {cfg['FTOS_CALENDLY_TOKEN']}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()
        sanitized_str, _ = sanitize_text(str(raw))
        scheduling_url = raw.get("scheduling_url") or raw.get("resource", {}).get(
            "scheduling_url", ""
        )
        san_url, _ = sanitize_text(str(scheduling_url))
        return ok(
            {
                "command": dry_command,
                "scheduling_url": san_url,
                "duration": duration,
                "window": window,
            },
            **meta,
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        return fail(f"calendly error: {exc}").to_dict()


def _compute_invoice_totals(
    lines: list[dict[str, Any]],
) -> tuple[float | None, int, float, float, str]:
    """Compute (subtotal, tva_rate, tva_amt, ttc, error). On error subtotal is None."""
    try:
        subtotal = sum(float(ln.get("montant", 0)) for ln in lines)
        tva_rate = 20
        tva_amt = round(subtotal * tva_rate / 100, 2)
        ttc = round(subtotal + tva_amt, 2)
        return subtotal, tva_rate, tva_amt, ttc, ""
    except (TypeError, ValueError) as exc:
        return None, 0, 0.0, 0.0, f"invalid line amounts: {exc}"


def _map_invoice_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise raw line dicts to the keys expected by the invoice template."""
    return [
        {
            "desc": ln.get("desc", ln.get("label", "")),
            "qty": ln.get("qty", 1),
            "pu": ln.get("pu", ln.get("amount", 0)),
            "montant": ln.get("montant", ln.get("amount", 0)),
        }
        for ln in lines
    ]


def _write_invoice_md(project_id: str, content: str, store: Store) -> tuple[Path | None, str]:
    """Write invoice content atomically; return (dest_path, error_or_empty)."""
    try:
        dest = store.project_dir(project_id) / "deliverables" / "invoice.md"
        write_text_atomic(dest, content)
        return dest, ""
    except (ValueError, OSError) as exc:
        return None, str(exc)


def _render_invoice_content(
    project_id: str,
    ref: str,
    prestataire_nom: str,
    client_nom: str,
    date_str: str,
    template_lines: list[dict[str, Any]],
    subtotal: float,
    tva_rate: int,
    tva_amt: float,
    ttc: float,
    conditions_paiement: str | None,
) -> tuple[str | None, str]:
    """Render the invoice template. Returns (content, error_or_empty)."""
    try:
        content = render_template(
            "business/invoice.md.j2",
            project_id=project_id,
            invoice_ref=ref,
            prestataire_nom=prestataire_nom,
            client_nom=client_nom,
            date=date_str,
            echeance=None,
            lignes=template_lines,
            montant_ht=subtotal,
            tva_taux=tva_rate,
            montant_tva=tva_amt,
            montant_ttc=ttc,
            iban=None,
            bic=None,
            conditions_paiement=conditions_paiement,
        )
        return content, ""
    except Exception as exc:  # noqa: BLE001
        return None, f"template error: {exc}"


# ---------------------------------------------------------------------------
# Tool 55: onboard_client (C1)
# ---------------------------------------------------------------------------


def onboard_client(
    company: str,
    needs: str,
    contact_email: str | None = None,
    base_model: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Collect client info and create the project workspace.

    Persists: company name, needs, status="onboarded", optional contact_email
    and base_model. Returns {project_id, state}.
    """
    if not company or not company.strip():
        return fail("company must not be empty").to_dict()

    s = _get_store(store)
    project_id = _slug(company) + "_" + uuid.uuid4().hex[:8]

    try:
        state = s.init_project(project_id, client=company)
        updates: dict[str, Any] = {
            "needs": needs,
            "status": "onboarded",
        }
        if contact_email is not None:
            updates["contact_email"] = contact_email
        if base_model is not None:
            updates["base_model"] = base_model
        state = s.update_project(project_id, **updates)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok({"project_id": project_id, "state": state}).to_dict()


# ---------------------------------------------------------------------------
# Tool 56: send_status_update (C2 — smtp | slack)
# ---------------------------------------------------------------------------


def send_status_update(
    project_id: str,
    subject: str,
    body: str,
    recipient: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render status_update.md.j2 and deliver via SMTP or Slack webhook.

    Priority: SMTP if configured; else Slack if configured; else dry_run.
    The rendered Markdown message is always returned as 'message'.
    """
    if not project_id or not project_id.strip():
        return fail("project_id must not be empty").to_dict()

    # Render the template (offline, always)
    rendered, err = _render_status_update(project_id, subject, body)
    if rendered is None:
        return fail(err).to_dict()

    # Try SMTP first
    smtp_configured, smtp_meta = gate("smtp")
    if smtp_configured:
        cfg = _get_target_config("smtp")
        if cfg is None:
            return fail("smtp config unavailable after gate check").to_dict()
        return _send_smtp(cfg, subject, rendered, recipient, smtp_meta)

    # Try Slack second
    slack_configured, slack_meta = gate("slack")
    if slack_configured:
        cfg = _get_target_config("slack")
        if cfg is None:
            return fail("slack config unavailable after gate check").to_dict()
        return _send_slack(cfg, subject, body, rendered, slack_meta)

    # Dry-run: neither configured
    return ok(
        {
            "message": rendered,
            "note": "Configure FTOS_SMTP_HOST/USER/PASSWORD or FTOS_SLACK_WEBHOOK to send",
        },
        executed=False,
        dry_run=True,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 57: schedule_meeting (C2 — calendly)
# ---------------------------------------------------------------------------


def schedule_meeting(
    duration: int,
    window: str,
) -> dict[str, Any]:
    """Propose meeting slots via Calendly API, or emit the API call as dry_run.

    duration: meeting length in minutes.
    window:   ISO date range or descriptive string (e.g. "next-week").
    """
    dry_command = (
        f"GET https://api.calendly.com/event_types "
        f"Authorization: Bearer $FTOS_CALENDLY_TOKEN "
        f"# duration={duration}min window={window}"
    )

    configured, meta = gate("calendly")
    if not configured:
        return ok(
            {"command": dry_command, "duration": duration, "window": window}, **meta
        ).to_dict()

    cfg = _get_target_config("calendly")
    if cfg is None:
        return fail("calendly config unavailable after gate check").to_dict()
    return _fetch_calendly_slots(cfg, dry_command, duration, window, meta)


# ---------------------------------------------------------------------------
# Tool 58: log_project_event (C1)
# ---------------------------------------------------------------------------


def log_project_event(
    project_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Append a timestamped event to events.jsonl via Store.append_event."""
    s = _get_store(store)
    try:
        event_id = s.append_event(project_id, event_type, payload)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok({"event_id": event_id, "type": event_type}).to_dict()


# ---------------------------------------------------------------------------
# Tool 59: request_client_approval (C1)
# ---------------------------------------------------------------------------


def request_client_approval(
    project_id: str,
    question: str,
    artifacts: list[str],
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Create a formal approval request (status='pending') in project state.

    Persists an approval record under project["approvals"] and logs an event.
    """
    if not question or not question.strip():
        return fail("question must not be empty").to_dict()

    s = _get_store(store)
    try:
        state = s.read_project(project_id)
    except (ValueError, OSError, FileNotFoundError) as exc:
        return fail(str(exc)).to_dict()

    approval_id = uuid.uuid4().hex
    approval: dict[str, Any] = {
        "id": approval_id,
        "status": "pending",
        "question": question,
        "artifacts": artifacts,
        "requested_at": _now_iso(),
    }

    approvals: list[dict[str, Any]] = list(state.get("approvals", []))
    approvals.append(approval)

    try:
        s.update_project(project_id, approvals=approvals)
        s.append_event(
            project_id, "approval_requested", {"approval_id": approval_id, "question": question}
        )
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok({"approval_id": approval_id, "status": "pending"}).to_dict()


# ---------------------------------------------------------------------------
# Tool 60: generate_invoice (C1)
# ---------------------------------------------------------------------------


def generate_invoice(
    project_id: str,
    lines: list[dict[str, Any]],
    prestataire_nom: str = "[PRESTATAIRE]",
    client_nom: str = "[CLIENT]",
    invoice_ref: str | None = None,
    conditions_paiement: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render invoice.md.j2 and write under <project>/deliverables/invoice.md.

    lines: list of {desc, qty, pu, montant}.
    Returns {md_path, pdf_path?, sha256}.
    """
    if not lines:
        return fail("lines must not be empty").to_dict()

    ref = invoice_ref or f"INV-{uuid.uuid4().hex[:8].upper()}"
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    subtotal, tva_rate, tva_amt, ttc, tot_err = _compute_invoice_totals(lines)
    if subtotal is None:
        return fail(tot_err).to_dict()

    content, tmpl_err = _render_invoice_content(
        project_id,
        ref,
        prestataire_nom,
        client_nom,
        date_str,
        _map_invoice_lines(lines),
        subtotal,
        tva_rate,
        tva_amt,
        ttc,
        conditions_paiement,
    )
    if content is None:
        return fail(tmpl_err).to_dict()

    dest, write_err = _write_invoice_md(project_id, content, _get_store(store))
    if dest is None:
        return fail(write_err).to_dict()

    md_sha256 = sha256_bytes(content.encode())
    result_data: dict[str, Any] = {"md_path": str(dest), "sha256": md_sha256}

    pdf_path, pdf_msg = _try_pdf(dest)
    if pdf_path:
        result_data["pdf_path"] = pdf_path
    elif pdf_msg:
        result_data["pdf_skipped"] = pdf_msg

    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrappers without `store` kwarg
# ---------------------------------------------------------------------------


# MCP wrapper — keep signature in sync with onboard_client
def _mcp_onboard_client(
    company: str,
    needs: str,
    contact_email: str | None = None,
    base_model: str | None = None,
) -> dict[str, Any]:
    return onboard_client(
        company=company,
        needs=needs,
        contact_email=contact_email,
        base_model=base_model,
    )


# MCP wrapper — keep signature in sync with send_status_update
def _mcp_send_status_update(
    project_id: str,
    subject: str,
    body: str,
    recipient: str | None = None,
) -> dict[str, Any]:
    return send_status_update(
        project_id=project_id,
        subject=subject,
        body=body,
        recipient=recipient,
    )


# MCP wrapper — keep signature in sync with schedule_meeting
def _mcp_schedule_meeting(
    duration: int,
    window: str,
) -> dict[str, Any]:
    return schedule_meeting(duration=duration, window=window)


# MCP wrapper — keep signature in sync with log_project_event
def _mcp_log_project_event(
    project_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return log_project_event(
        project_id=project_id,
        event_type=event_type,
        payload=payload,
    )


# MCP wrapper — keep signature in sync with request_client_approval
def _mcp_request_client_approval(
    project_id: str,
    question: str,
    artifacts: list[str],
) -> dict[str, Any]:
    return request_client_approval(
        project_id=project_id,
        question=question,
        artifacts=artifacts,
    )


# MCP wrapper — keep signature in sync with generate_invoice
def _mcp_generate_invoice(
    project_id: str,
    lines: list[dict[str, Any]],
    prestataire_nom: str = "[PRESTATAIRE]",
    client_nom: str = "[CLIENT]",
    invoice_ref: str | None = None,
    conditions_paiement: str | None = None,
) -> dict[str, Any]:
    return generate_invoice(
        project_id=project_id,
        lines=lines,
        prestataire_nom=prestataire_nom,
        client_nom=client_nom,
        invoice_ref=invoice_ref,
        conditions_paiement=conditions_paiement,
    )


_MCP_TOOLS = [
    (
        _mcp_onboard_client,
        "Onboard a new client: collect company info and create the project workspace.",
    ),
    (
        _mcp_send_status_update,
        "Render a status update and deliver via SMTP or Slack webhook (dry-run if neither configured).",
    ),
    (
        _mcp_schedule_meeting,
        "Propose meeting slots via Calendly API (dry-run if FTOS_CALENDLY_TOKEN not configured).",
    ),
    (
        _mcp_log_project_event,
        "Append a timestamped event to the project events.jsonl log.",
    ),
    (
        _mcp_request_client_approval,
        "Create a formal approval request (status='pending') persisted in project state.",
    ),
    (
        _mcp_generate_invoice,
        "Render an invoice from prestation lines as Markdown + optional PDF.",
    ),
]


def register(mcp: Any) -> None:
    """Register all client tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)
