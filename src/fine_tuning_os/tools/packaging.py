# src/fine_tuning_os/tools/packaging.py
"""Lot 5 — Packaging tools 39-46.

C2 contract (tools 39, 40, 41, 43, 45):
  configured, meta = gate(kind)
  command = <exact runnable command string>   # ALWAYS computed
  if not configured: return ok({command:..., ...}, **meta).to_dict()
  # configured -> real action; sanitize ALL external text before returning
  Never put secret VALUES in command/output (env NAME refs only).

C1 tools (42, 44, 46): pure, offline, deterministic.
Never raise to caller — wrap I/O in try/except and return fail(str(exc)).
"""

from __future__ import annotations

import shutil
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paramiko

from ..crypto import decrypt_file, encrypt_file, generate_key  # noqa: F401
from ..envelope import fail, ok
from ..render import markdown_file_to_pdf, sha256_bytes, sha256_file, write_text_atomic
from ..sanitize import sanitize_text
from ..store import Store, workspace_root
from ..targets import _get_target_config, gate
from ..templating import render_template

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_store(store: Store | None) -> Store:
    return store if store is not None else Store(root=workspace_root())


def _sftp_gate() -> tuple[bool, dict[str, Any], dict[str, Any] | None]:
    """Run the SFTP C2 gate and return (configured, meta, cfg)."""
    configured, meta = gate("sftp")
    cfg = _get_target_config("sftp") if configured else None
    return configured, meta, cfg


# ---------------------------------------------------------------------------
# Tool 39: merge_lora_weights (C2 — local_python gate)
# ---------------------------------------------------------------------------


def merge_lora_weights(
    base_model: str,
    adapter_path: str,
    output_path: str,
    local_python: bool = False,
) -> dict[str, Any]:
    """Emit the LoRA merge command (base + adapter -> merged 16-bit).

    Routes to local Python if FTOS_LOCAL_PYTHON is configured and
    local_python=True; otherwise emits the exact command (dry_run).
    """
    cmd = (
        f'python3 -c "'
        f"from peft import PeftModel; "
        f"from transformers import AutoModelForCausalLM, AutoTokenizer; "
        f"import torch; "
        f"model = AutoModelForCausalLM.from_pretrained('{base_model}', "
        f"torch_dtype=torch.float16); "
        f"model = PeftModel.from_pretrained(model, '{adapter_path}'); "
        f"model = model.merge_and_unload(); "
        f"model.save_pretrained('{output_path}'); "
        f"AutoTokenizer.from_pretrained('{base_model}')"
        f".save_pretrained('{output_path}')\""
    )

    if local_python:
        configured, meta = gate("local_python")
        if configured:
            cfg = _get_target_config("local_python")
            python_bin = cfg["FTOS_LOCAL_PYTHON"]  # type: ignore[index]
            live_cmd = cmd.replace("python3 ", f"{python_bin} ", 1)
            import subprocess  # noqa: PLC0415

            try:
                result = subprocess.run(
                    live_cmd,
                    shell=True,  # noqa: S602
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                sanitized_out, n = sanitize_text(result.stdout + result.stderr)
                return ok(
                    {
                        "command": cmd,
                        "output": sanitized_out,
                        "masked_count": n,
                        "returncode": result.returncode,
                        "output_path": output_path,
                    },
                    **meta,
                ).to_dict()
            except (subprocess.TimeoutExpired, OSError) as exc:
                return fail(str(exc)).to_dict()

    return ok(
        {
            "command": cmd,
            "base_model": base_model,
            "adapter_path": adapter_path,
            "output_path": output_path,
            "note": "Run this command in your Python environment with peft+transformers installed",
        },
        executed=False,
        dry_run=True,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 40: quantize_model (C2 — local_python gate)
# ---------------------------------------------------------------------------

_VALID_QUANT_FORMATS = frozenset(["gguf", "gptq", "awq"])


def quantize_model(
    model_path: str,
    format: str = "gguf",
    bits: int = 4,
    output_path: str | None = None,
    local_python: bool = False,
) -> dict[str, Any]:
    """Emit the quantization command for GGUF/GPTQ/AWQ."""
    fmt = format.lower()
    if fmt not in _VALID_QUANT_FORMATS:
        return fail(f"unknown format: {format!r}; valid: {sorted(_VALID_QUANT_FORMATS)}").to_dict()

    out = output_path or f"{model_path}-{fmt}-{bits}bit"

    if fmt == "gguf":
        cmd = (
            f"python3 llama.cpp/convert-hf-to-gguf.py {model_path} "
            f"--outfile {out}.gguf --outtype q{bits}_0"
        )
    elif fmt == "gptq":
        cmd = (
            f'python3 -c "'
            f"from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig; "
            f"from transformers import AutoTokenizer; "
            f"config = BaseQuantizeConfig(bits={bits}, group_size=128); "
            f"model = AutoGPTQForCausalLM.from_pretrained('{model_path}', config); "
            f"tokenizer = AutoTokenizer.from_pretrained('{model_path}'); "
            f"model.quantize([]); "
            f"model.save_quantized('{out}')\""
        )
    else:  # awq
        cmd = (
            f'python3 -c "'
            f"from awq import AutoAWQForCausalLM; "
            f"from transformers import AutoTokenizer; "
            f"model = AutoAWQForCausalLM.from_pretrained('{model_path}'); "
            f"tokenizer = AutoTokenizer.from_pretrained('{model_path}'); "
            f"quant_config = {{'zero_point': True, 'q_group_size': 128, 'w_bit': {bits}}}; "
            f"model.quantize(tokenizer, quant_config=quant_config); "
            f"model.save_quantized('{out}')\""
        )

    if local_python:
        configured, meta = gate("local_python")
        if configured:
            cfg = _get_target_config("local_python")
            python_bin = cfg["FTOS_LOCAL_PYTHON"]  # type: ignore[index]
            live_cmd = cmd.replace("python3 ", f"{python_bin} ", 1)
            import subprocess  # noqa: PLC0415

            try:
                result = subprocess.run(
                    live_cmd,
                    shell=True,  # noqa: S602
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
                sanitized_out, n = sanitize_text(result.stdout + result.stderr)
                return ok(
                    {
                        "command": cmd,
                        "output": sanitized_out,
                        "masked_count": n,
                        "returncode": result.returncode,
                        "output_path": out,
                    },
                    **meta,
                ).to_dict()
            except (subprocess.TimeoutExpired, OSError) as exc:
                return fail(str(exc)).to_dict()

    return ok(
        {
            "command": cmd,
            "model_path": model_path,
            "format": fmt,
            "bits": bits,
            "output_path": out,
        },
        executed=False,
        dry_run=True,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 41: build_inference_container (C2 — docker gate)
# ---------------------------------------------------------------------------

_VALID_ENGINES = frozenset(["vllm", "sglang", "generic"])


def build_inference_container(
    model_path: str,
    engine: str = "vllm",
    project_id: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render Dockerfile.infer.j2 and emit docker build command.

    Docker gate: executes if FTOS_LOCAL_PYTHON is set AND docker is on PATH;
    otherwise dry_run.
    """
    eng = engine.lower()
    if eng not in _VALID_ENGINES:
        return fail(f"unknown engine: {engine!r}; valid: {sorted(_VALID_ENGINES)}").to_dict()

    try:
        dockerfile_content = render_template(
            "docker/Dockerfile.infer.j2",
            engine=eng,
            model_path=model_path,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    # Determine output path
    s = _get_store(store)
    if project_id:
        try:
            dest_dir = s.project_dir(project_id) / "docker"
        except ValueError as exc:
            return fail(str(exc)).to_dict()
    else:
        dest_dir = Path("docker")

    dockerfile_path = dest_dir / "Dockerfile.infer"

    try:
        write_text_atomic(dockerfile_path, dockerfile_content)
    except OSError as exc:
        return fail(f"write error: {exc}").to_dict()

    image_tag = f"ftos-infer-{project_id or 'model'}:latest"
    cmd = f"docker build -t {image_tag} -f {dockerfile_path} ."

    # Gate: docker available locally
    docker_available = shutil.which("docker") is not None
    local_configured, meta = gate("local_python")
    live = docker_available and local_configured

    if live:
        import subprocess  # noqa: PLC0415

        try:
            result = subprocess.run(
                ["docker", "build", "-t", image_tag, "-f", str(dockerfile_path), "."],
                capture_output=True,
                text=True,
                timeout=600,
                shell=False,
            )
            sanitized_out, n = sanitize_text(result.stdout + result.stderr)
            return ok(
                {
                    "command": cmd,
                    "dockerfile_path": str(dockerfile_path),
                    "image_tag": image_tag,
                    "output": sanitized_out,
                    "masked_count": n,
                    "returncode": result.returncode,
                },
                **meta,
            ).to_dict()
        except (subprocess.TimeoutExpired, OSError) as exc:
            return fail(str(exc)).to_dict()

    return ok(
        {
            "command": cmd,
            "dockerfile_path": str(dockerfile_path),
            "dockerfile_content": dockerfile_content,
            "image_tag": image_tag,
        },
        executed=False,
        dry_run=True,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 42: generate_inference_config (C1 — offline)
# ---------------------------------------------------------------------------


def generate_inference_config(
    port: int = 8000,
    context_length: int = 4096,
    max_concurrent: int = 4,
    engine: str = "vllm",
    api_key_env_name: str = "API_KEY",
    extra_params: dict[str, Any] | None = None,
    project_id: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Produce inference server config (port, api key NAME ref, context, limits).

    The API key is referenced by environment variable NAME only —
    no real key value is ever embedded in the config.
    """
    config: dict[str, Any] = {
        "engine": engine,
        "port": port,
        "context_length": context_length,
        "max_concurrent_requests": max_concurrent,
        # Reference by env var NAME — never the value
        "api_key_env": api_key_env_name,
        "note": (
            f"Set ${api_key_env_name} in your environment. "
            "The key value is never stored in this config."
        ),
    }
    if extra_params:
        config.update({k: v for k, v in extra_params.items() if k != "api_key"})

    import json  # noqa: PLC0415

    config_str = json.dumps(config, indent=2)

    result_data: dict[str, Any] = {"config": config, "config_json": config_str}

    if project_id is not None:
        s = _get_store(store)
        try:
            dest = s.project_dir(project_id) / "config" / "inference.json"
            write_text_atomic(dest, config_str)
            result_data["path"] = str(dest)
        except (ValueError, OSError) as exc:
            return fail(str(exc)).to_dict()

    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# Tool 43: test_inference_api (C2 — base_url / endpoint gate)
# ---------------------------------------------------------------------------


def test_inference_api(
    prompts: list[str],
    base_url: str | None = None,
    model: str = "ftos-model",
    max_tokens: int = 64,
    api_key_env: str = "API_KEY",
) -> dict[str, Any]:
    """Send test requests to a running inference container.

    If base_url is provided, attempts a live call via httpx.
    Otherwise emits the exact curl commands (dry_run).
    """
    if not prompts:
        return fail("prompts list must not be empty").to_dict()

    # Build curl commands for dry-run documentation
    curl_cmds = []
    for prompt in prompts[:3]:  # Show up to 3 example commands
        safe_prompt = prompt.replace('"', '\\"')
        curl_cmds.append(
            f'curl -X POST {base_url or "$INFERENCE_BASE_URL"}/v1/chat/completions \\\n'
            f'  -H "Authorization: Bearer ${api_key_env}" \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f"  -d '"
            + '{"model": "'
            + model
            + '", "messages": [{"role": "user", "content": "'
            + safe_prompt
            + '"}], "max_tokens": '
            + str(max_tokens)
            + "}'"
        )

    if not base_url:
        return ok(
            {
                "command": curl_cmds[0] if curl_cmds else "",
                "all_commands": curl_cmds,
                "prompts_count": len(prompts),
                "note": "Provide base_url to execute live tests",
            },
            executed=False,
            dry_run=True,
        ).to_dict()

    # Live call via httpx
    try:
        import httpx  # noqa: PLC0415
        import os  # noqa: PLC0415
    except ImportError:
        return fail("httpx is required for live API testing; install it first").to_dict()

    api_key = os.environ.get(api_key_env, "")
    results = []

    for prompt in prompts:
        try:
            sanitized_prompt, _ = sanitize_text(prompt)
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": sanitized_prompt}],
                "max_tokens": max_tokens,
            }
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            resp = httpx.post(
                f"{base_url}/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=30.0,
            )
            resp.raise_for_status()
            raw_content = resp.text
            sanitized_content, n_masked = sanitize_text(raw_content)
            results.append(
                {
                    "prompt_index": len(results),
                    "status_code": resp.status_code,
                    "response": sanitized_content,
                    "masked_count": n_masked,
                    "ok": True,
                }
            )
        except Exception as exc:  # noqa: BLE001
            sanitized_err, _ = sanitize_text(str(exc))
            results.append(
                {
                    "prompt_index": len(results),
                    "error": sanitized_err,
                    "ok": False,
                }
            )

    return ok(
        {
            "command": curl_cmds[0] if curl_cmds else "",
            "base_url": base_url,
            "results": results,
            "total": len(prompts),
            "succeeded": sum(1 for r in results if r.get("ok")),
        },
        executed=True,
        dry_run=False,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 44: encrypt_deliverable (C1 — crypto)
# ---------------------------------------------------------------------------


def encrypt_deliverable(
    paths: list[str],
    output_dir: str | None = None,
) -> dict[str, Any]:
    """AES-256-GCM encrypt deliverable file(s).

    The key is returned ONCE in data (hex) and is NEVER persisted to disk
    or project.json. If multiple paths are given, they are archived into a
    single .tar.gz before encryption.
    """
    if not paths:
        return fail("paths list must not be empty").to_dict()

    input_paths = [Path(p) for p in paths]
    for p in input_paths:
        if not p.exists():
            return fail(f"file not found: {p}").to_dict()

    out_dir = Path(output_dir) if output_dir else input_paths[0].parent

    try:
        out_dir.mkdir(parents=True, exist_ok=True)

        # If multiple files, archive them first
        if len(input_paths) > 1:
            archive_path = out_dir / "deliverables.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tf:
                for p in input_paths:
                    tf.add(p, arcname=p.name)
            src_path = archive_path
        else:
            src_path = input_paths[0]

        # Generate a fresh key — never persisted
        key = generate_key()
        key_hex = key.hex()

        # Encrypt
        enc_path = out_dir / (src_path.name + ".enc")
        encrypt_file(src_path, enc_path, key)

        # Hash of encrypted file for integrity
        enc_sha256 = sha256_file(enc_path)

        # Clean up temp archive if created
        if len(input_paths) > 1:
            archive_path.unlink(missing_ok=True)  # type: ignore[union-attr]

    except (OSError, ValueError) as exc:
        return fail(str(exc)).to_dict()

    return ok(
        {
            "encrypted_path": str(enc_path),
            "key_hex": key_hex,
            "sha256": enc_sha256,
            "source_count": len(input_paths),
            "warning": (
                "Store key_hex securely and separately from the encrypted file. "
                "The key is shown ONCE and is not stored anywhere."
            ),
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 45: upload_deliverable (C2 — sftp)
# ---------------------------------------------------------------------------


def upload_deliverable(
    path: str,
    destination: str = ".",
) -> dict[str, Any]:
    """Upload the encrypted deliverable over SFTP (paramiko) if configured.

    dry_run: emits the exact sftp command with $FTOS_SFTP_* NAME placeholders.
    live: uses paramiko with the actual config values (never surfaced in output).
    """
    src = Path(path)
    fname = src.name

    # Build dry-run command with env var NAME refs (never values)
    remote_dest = f"{destination}/{fname}" if destination != "." else fname
    cmd = (
        f"sftp -i $FTOS_SFTP_KEY $FTOS_SFTP_USER@$FTOS_SFTP_HOST:{destination} "
        f"<<< $'put {path}'"
    )

    configured, meta, cfg = _sftp_gate()

    if not configured:
        return ok(
            {
                "command": cmd,
                "path": path,
                "destination": destination,
                "note": "Set FTOS_SFTP_HOST, FTOS_SFTP_USER, FTOS_SFTP_KEY to upload live",
            },
            **meta,
        ).to_dict()

    if not src.exists():
        return fail(f"file not found: {path}").to_dict()

    host = cfg["FTOS_SFTP_HOST"]  # type: ignore[index]
    user = cfg["FTOS_SFTP_USER"]  # type: ignore[index]
    key_path = cfg["FTOS_SFTP_KEY"]  # type: ignore[index]

    try:
        transport = paramiko.Transport((host, 22))
        transport.connect(username=user, pkey=paramiko.RSAKey.from_private_key_file(key_path))
        sftp = paramiko.SFTPClient.from_transport(transport)  # type: ignore[arg-type]
        try:
            sftp.put(str(src), remote_dest)
        finally:
            sftp.close()
            transport.close()
    except (paramiko.SSHException, OSError) as exc:
        sanitized_err, _ = sanitize_text(str(exc))
        return fail(sanitized_err).to_dict()

    return ok(
        {
            "command": cmd,
            "path": path,
            "destination": destination,
            "remote_path": remote_dest,
            "uploaded": True,
        },
        **meta,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 46: generate_delivery_note (C1 — render)
# ---------------------------------------------------------------------------


def generate_delivery_note(
    project_id: str,
    files: list[dict[str, Any]],
    prestataire_nom: str = "[PRESTATAIRE]",
    client_nom: str = "[CLIENT]",
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render delivery_note.md.j2 with file list + SHA256 each.

    Also produces PDF if weasyprint is available.
    """
    if not files:
        return fail("files list must not be empty").to_dict()

    # Compute SHA256 for each file if not provided
    enriched: list[dict[str, Any]] = []
    for f in files:
        entry = dict(f)
        fp = Path(f.get("path", f.get("name", "")))
        if "sha256" not in entry and fp.exists():
            try:
                entry["sha256"] = sha256_file(fp)
            except OSError:
                entry["sha256"] = "[error computing sha256]"
        elif "sha256" not in entry:
            entry["sha256"] = "[sha256 not computed]"
        if "name" not in entry:
            entry["name"] = fp.name
        enriched.append(entry)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    file_names = [e["name"] for e in enriched]

    try:
        content = render_template(
            "legal/delivery_note.md.j2",
            project_id=project_id,
            files=enriched,
            file_names=file_names,
            delivery_date=now_str,
            prestataire_nom=prestataire_nom,
            client_nom=client_nom,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    s = _get_store(store)
    try:
        dest = s.project_dir(project_id) / "deliverables" / "delivery_note.md"
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    md_sha256 = sha256_bytes(content.encode())
    result_data: dict[str, Any] = {
        "md_path": str(dest),
        "sha256": md_sha256,
        "files_count": len(enriched),
    }

    # Attempt PDF generation — skip gracefully if weasyprint absent
    try:
        pdf_dest = dest.with_suffix(".pdf")
        markdown_file_to_pdf(dest, pdf_dest)
        result_data["pdf_path"] = str(pdf_dest)
    except ImportError:
        result_data["pdf_skipped"] = "weasyprint not installed"
    except Exception as exc:  # noqa: BLE001
        result_data["pdf_error"] = str(exc)

    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrappers without `store` kwarg
# ---------------------------------------------------------------------------


# MCP wrapper — keep signature in sync with merge_lora_weights
def _mcp_merge_lora_weights(
    base_model: str,
    adapter_path: str,
    output_path: str,
    local_python: bool = False,
) -> dict[str, Any]:
    return merge_lora_weights(
        base_model=base_model,
        adapter_path=adapter_path,
        output_path=output_path,
        local_python=local_python,
    )


# MCP wrapper — keep signature in sync with quantize_model
def _mcp_quantize_model(
    model_path: str,
    format: str = "gguf",
    bits: int = 4,
    output_path: str | None = None,
    local_python: bool = False,
) -> dict[str, Any]:
    return quantize_model(
        model_path=model_path,
        format=format,
        bits=bits,
        output_path=output_path,
        local_python=local_python,
    )


# MCP wrapper — keep signature in sync with build_inference_container
def _mcp_build_inference_container(
    model_path: str,
    engine: str = "vllm",
    project_id: str | None = None,
) -> dict[str, Any]:
    return build_inference_container(
        model_path=model_path,
        engine=engine,
        project_id=project_id,
    )


# MCP wrapper — keep signature in sync with generate_inference_config
def _mcp_generate_inference_config(
    port: int = 8000,
    context_length: int = 4096,
    max_concurrent: int = 4,
    engine: str = "vllm",
    api_key_env_name: str = "API_KEY",
    extra_params: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    return generate_inference_config(
        port=port,
        context_length=context_length,
        max_concurrent=max_concurrent,
        engine=engine,
        api_key_env_name=api_key_env_name,
        extra_params=extra_params,
        project_id=project_id,
    )


# MCP wrapper — keep signature in sync with test_inference_api
def _mcp_test_inference_api(
    prompts: list[str],
    base_url: str | None = None,
    model: str = "ftos-model",
    max_tokens: int = 64,
    api_key_env: str = "API_KEY",
) -> dict[str, Any]:
    return test_inference_api(
        prompts=prompts,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        api_key_env=api_key_env,
    )


# MCP wrapper — keep signature in sync with encrypt_deliverable
def _mcp_encrypt_deliverable(
    paths: list[str],
    output_dir: str | None = None,
) -> dict[str, Any]:
    return encrypt_deliverable(paths=paths, output_dir=output_dir)


# MCP wrapper — keep signature in sync with upload_deliverable
def _mcp_upload_deliverable(
    path: str,
    destination: str = ".",
) -> dict[str, Any]:
    return upload_deliverable(path=path, destination=destination)


# MCP wrapper — keep signature in sync with generate_delivery_note
def _mcp_generate_delivery_note(
    project_id: str,
    files: list[dict[str, Any]],
    prestataire_nom: str = "[PRESTATAIRE]",
    client_nom: str = "[CLIENT]",
) -> dict[str, Any]:
    return generate_delivery_note(
        project_id=project_id,
        files=files,
        prestataire_nom=prestataire_nom,
        client_nom=client_nom,
    )


_MCP_TOOLS = [
    (
        _mcp_merge_lora_weights,
        "Emit the LoRA merge command (base + adapter → merged 16-bit) — dry_run unless FTOS_LOCAL_PYTHON configured.",
    ),
    (
        _mcp_quantize_model,
        "Emit the quantization command for GGUF/GPTQ/AWQ — dry_run unless FTOS_LOCAL_PYTHON configured.",
    ),
    (
        _mcp_build_inference_container,
        "Render Dockerfile.infer and emit docker build command — dry_run unless local docker configured.",
    ),
    (
        _mcp_generate_inference_config,
        "Produce inference server config (port, api key NAME ref, context, limits) — no secrets embedded.",
    ),
    (
        _mcp_test_inference_api,
        "Send test requests to a running inference container — dry_run curl unless base_url provided.",
    ),
    (
        _mcp_encrypt_deliverable,
        "AES-256-GCM encrypt deliverable file(s); key returned ONCE in data, never persisted.",
    ),
    (
        _mcp_upload_deliverable,
        "Upload encrypted deliverable over SFTP — dry_run unless FTOS_SFTP_* configured.",
    ),
    (
        _mcp_generate_delivery_note,
        "Render delivery note with file list + SHA256 each + decryption procedure.",
    ),
]


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all packaging tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
