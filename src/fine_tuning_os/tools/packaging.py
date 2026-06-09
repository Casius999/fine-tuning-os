# SPDX-License-Identifier: Apache-2.0
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
import subprocess
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


def _run_subprocess(
    command: str,
    *,
    timeout: int,
    use_list: list[str] | None = None,
) -> tuple[str, str, int]:
    """Run a subprocess and return (stdout, stderr, returncode).

    Raises subprocess.TimeoutExpired or OSError on failure.
    """
    if use_list is not None:
        result = subprocess.run(
            use_list,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    else:
        result = subprocess.run(
            command,
            shell=True,  # noqa: S602
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return result.stdout, result.stderr, result.returncode


def _execute_or_dry(
    *,
    cmd: str,
    gate_kind: str,
    timeout: int,
    dry_extra: dict[str, Any],
    live_extra_fn: Any,
    use_list: list[str] | None = None,
    python_bin_replace: bool = False,
) -> dict[str, Any]:
    """Shared C2 gate/subprocess/dry-run pattern.

    Checks the gate; if configured, runs the command and returns the live result.
    Otherwise returns dry_run ok with dry_extra.

    live_extra_fn(stdout, stderr, returncode) -> dict[str, Any]  (live data fields)
    """
    configured, meta = gate(gate_kind)
    if not configured:
        return ok({"command": cmd, **dry_extra}, executed=False, dry_run=True).to_dict()

    cfg = _get_target_config(gate_kind)
    run_cmd = cmd
    run_list = use_list
    if python_bin_replace and cfg:
        python_bin = cfg.get("FTOS_LOCAL_PYTHON", "python3")  # type: ignore[union-attr]
        run_cmd = cmd.replace("python3 ", f"{python_bin} ", 1)
        if run_list:
            run_list = [python_bin if x == "python3" else x for x in run_list]

    try:
        stdout, stderr, returncode = _run_subprocess(run_cmd, timeout=timeout, use_list=run_list)
        sanitized_out, n = sanitize_text(stdout + stderr)
        live_data = live_extra_fn(sanitized_out, n, returncode)
        return ok({"command": cmd, **live_data}, **meta).to_dict()
    except (subprocess.TimeoutExpired, OSError) as exc:
        return fail(str(exc)).to_dict()


def _try_pdf_packaging(dest: Path) -> dict[str, Any]:
    """Attempt PDF; return dict entries to merge into result_data (pdf_path or pdf_skipped)."""
    try:
        pdf_dest = dest.with_suffix(".pdf")
        markdown_file_to_pdf(dest, pdf_dest)
        return {"pdf_path": str(pdf_dest)}
    except ImportError:
        return {"pdf_skipped": "weasyprint not installed"}
    except Exception as exc:  # noqa: BLE001
        return {"pdf_skipped": str(exc)}


def _build_merge_cmd(base_model: str, adapter_path: str, output_path: str) -> str:
    """Build the LoRA merge python3 inline command string."""
    return (
        f'python3 -c "from peft import PeftModel; '
        f"from transformers import AutoModelForCausalLM, AutoTokenizer; import torch; "
        f"model = AutoModelForCausalLM.from_pretrained('{base_model}', torch_dtype=torch.float16); "
        f"model = PeftModel.from_pretrained(model, '{adapter_path}').merge_and_unload(); "
        f"model.save_pretrained('{output_path}'); "
        f"AutoTokenizer.from_pretrained('{base_model}').save_pretrained('{output_path}')\""
    )


def merge_lora_weights(
    base_model: str,
    adapter_path: str,
    output_path: str,
    local_python: bool = False,
) -> dict[str, Any]:
    """Emit the LoRA merge command (base + adapter -> merged 16-bit)."""
    cmd = _build_merge_cmd(base_model, adapter_path, output_path)
    dry_extra = {
        "base_model": base_model,
        "adapter_path": adapter_path,
        "output_path": output_path,
        "note": "Run this command in your Python environment with peft+transformers installed",
    }
    if local_python:
        return _execute_or_dry(
            cmd=cmd,
            gate_kind="local_python",
            timeout=600,
            dry_extra=dry_extra,
            live_extra_fn=lambda out, n, rc: {
                "output": out,
                "masked_count": n,
                "returncode": rc,
                "output_path": output_path,
            },
            python_bin_replace=True,
        )
    return ok({"command": cmd, **dry_extra}, executed=False, dry_run=True).to_dict()


_VALID_QUANT_FORMATS = frozenset(["gguf", "gptq", "awq"])


def _build_quantize_cmd(model_path: str, fmt: str, bits: int, out: str) -> str:
    """Build the quantization command string for the given format."""
    if fmt == "gguf":
        return (
            f"python3 llama.cpp/convert-hf-to-gguf.py {model_path} "
            f"--outfile {out}.gguf --outtype q{bits}_0"
        )
    if fmt == "gptq":
        return (
            f'python3 -c "from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig; '
            f"from transformers import AutoTokenizer; config = BaseQuantizeConfig(bits={bits}, group_size=128); "
            f"model = AutoGPTQForCausalLM.from_pretrained('{model_path}', config); "
            f"tokenizer = AutoTokenizer.from_pretrained('{model_path}'); "
            f"model.quantize([]); model.save_quantized('{out}')\""
        )
    # awq
    return (
        f'python3 -c "from awq import AutoAWQForCausalLM; '
        f"from transformers import AutoTokenizer; "
        f"model = AutoAWQForCausalLM.from_pretrained('{model_path}'); "
        f"tokenizer = AutoTokenizer.from_pretrained('{model_path}'); "
        f"quant_config = {{'zero_point': True, 'q_group_size': 128, 'w_bit': {bits}}}; "
        f"model.quantize(tokenizer, quant_config=quant_config); model.save_quantized('{out}')\""
    )


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
    cmd = _build_quantize_cmd(model_path, fmt, bits, out)

    if local_python:
        return _execute_or_dry(
            cmd=cmd,
            gate_kind="local_python",
            timeout=1800,
            dry_extra={
                "model_path": model_path,
                "format": fmt,
                "bits": bits,
                "output_path": out,
            },
            live_extra_fn=lambda o, n, rc: {
                "output": o,
                "masked_count": n,
                "returncode": rc,
                "output_path": out,
            },
            python_bin_replace=True,
        )

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


_VALID_ENGINES = frozenset(["vllm", "sglang", "generic"])


def _write_dockerfile(
    model_path: str,
    engine: str,
    store: Store | None,
    project_id: str | None,
) -> tuple[Path, str] | dict[str, Any]:
    """Render and write the Dockerfile; return (dockerfile_path, content) or fail dict."""
    try:
        dockerfile_content = render_template(
            "docker/Dockerfile.infer.j2",
            engine=engine,
            model_path=model_path,
        )
    except Exception as exc:  # noqa: BLE001
        return fail(f"template error: {exc}").to_dict()

    if not project_id:
        return fail(
            "project_id is required for build_inference_container; "
            "writing to a relative path is not allowed (filesystem confinement)"
        ).to_dict()

    s = _get_store(store)
    try:
        dest_dir = s.project_dir(project_id) / "docker"
    except ValueError as exc:
        return fail(str(exc)).to_dict()

    dockerfile_path = dest_dir / "Dockerfile.infer"

    try:
        write_text_atomic(dockerfile_path, dockerfile_content)
    except OSError as exc:
        return fail(f"write error: {exc}").to_dict()

    return dockerfile_path, dockerfile_content


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

    write_result = _write_dockerfile(model_path, eng, store, project_id)
    if isinstance(write_result, dict):
        return write_result
    dockerfile_path, dockerfile_content = write_result

    image_tag = f"ftos-infer-{project_id or 'model'}:latest"
    cmd = f"docker build -t {image_tag} -f {dockerfile_path} ."

    docker_available = shutil.which("docker") is not None
    local_configured, meta = gate("local_python")
    live = docker_available and local_configured

    if not live:
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

    return _run_docker_build(cmd, dockerfile_path, image_tag, meta)


def _run_docker_build(
    cmd: str,
    dockerfile_path: Path,
    image_tag: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    """Execute docker build and return ok/fail dict."""
    try:
        stdout, stderr, returncode = _run_subprocess(
            cmd,
            timeout=600,
            use_list=["docker", "build", "-t", image_tag, "-f", str(dockerfile_path), "."],
        )
        sanitized_out, n = sanitize_text(stdout + stderr)
        return ok(
            {
                "command": cmd,
                "dockerfile_path": str(dockerfile_path),
                "image_tag": image_tag,
                "output": sanitized_out,
                "masked_count": n,
                "returncode": returncode,
            },
            **meta,
        ).to_dict()
    except (subprocess.TimeoutExpired, OSError) as exc:
        return fail(str(exc)).to_dict()


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


def _build_curl_cmds(
    prompts: list[str],
    base_url: str | None,
    model: str,
    max_tokens: int,
    api_key_env: str,
) -> list[str]:
    """Build example curl commands for up to 3 prompts."""
    curl_cmds = []
    base = base_url or "$INFERENCE_BASE_URL"
    for prompt in prompts[:3]:
        sp = prompt.replace('"', '\\"')
        body = f'{{"model": "{model}", "messages": [{{"role": "user", "content": "{sp}"}}], "max_tokens": {max_tokens}}}'
        curl_cmds.append(
            f"curl -X POST {base}/v1/chat/completions"
            f' -H "Authorization: Bearer ${api_key_env}"'
            f' -H "Content-Type: application/json"'
            f" -d '{body}'"
        )
    return curl_cmds


def _call_inference_endpoint(
    prompts: list[str],
    base_url: str,
    model: str,
    max_tokens: int,
    api_key_env: str,
) -> list[dict[str, Any]]:
    """Send live requests to the inference endpoint; return results list."""
    import os  # noqa: PLC0415

    api_key = os.environ.get(api_key_env, "")
    results: list[dict[str, Any]] = []
    for prompt in prompts:
        results.append(
            _call_single_prompt(prompt, base_url, model, max_tokens, api_key, len(results))
        )
    return results


def _call_single_prompt(
    prompt: str,
    base_url: str,
    model: str,
    max_tokens: int,
    api_key: str,
    index: int,
) -> dict[str, Any]:
    """Send a single prompt to the inference endpoint and return the result entry."""
    import httpx  # noqa: PLC0415

    try:
        sanitized_prompt, _ = sanitize_text(prompt)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": sanitized_prompt}],
            "max_tokens": max_tokens,
        }
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        resp = httpx.post(
            f"{base_url}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        sanitized_content, n_masked = sanitize_text(resp.text)
        return {
            "prompt_index": index,
            "status_code": resp.status_code,
            "response": sanitized_content,
            "masked_count": n_masked,
            "ok": True,
        }
    except Exception as exc:  # noqa: BLE001
        sanitized_err, _ = sanitize_text(str(exc))
        return {"prompt_index": index, "error": sanitized_err, "ok": False}


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

    curl_cmds = _build_curl_cmds(prompts, base_url, model, max_tokens, api_key_env)

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

    try:
        import httpx  # noqa: PLC0415, F401
    except ImportError:
        return fail("httpx is required for live API testing; install it first").to_dict()

    results = _call_inference_endpoint(prompts, base_url, model, max_tokens, api_key_env)
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


def _archive_paths(input_paths: list[Path], out_dir: Path) -> Path:
    """Archive multiple paths into a tar.gz; return archive path."""
    archive_path = out_dir / "deliverables.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tf:
        for p in input_paths:
            tf.add(p, arcname=p.name)
    return archive_path


def encrypt_deliverable(
    paths: list[str],
    output_dir: str | None = None,
) -> dict[str, Any]:
    """AES-256-GCM encrypt deliverable file(s).

    Key returned ONCE in data (hex), NEVER persisted. Multiple paths are
    archived into a single .tar.gz before encryption.
    """
    if not paths:
        return fail("paths list must not be empty").to_dict()
    input_paths = [Path(p) for p in paths]
    for p in input_paths:
        if not p.exists():
            return fail(f"file not found: {p}").to_dict()
    out_dir = Path(output_dir) if output_dir else input_paths[0].parent
    archive_path: Path | None = None
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        if len(input_paths) > 1:
            archive_path = _archive_paths(input_paths, out_dir)
            src_path: Path = archive_path
        else:
            src_path = input_paths[0]
        key = generate_key()
        key_hex = key.hex()
        enc_path = out_dir / (src_path.name + ".enc")
        encrypt_file(src_path, enc_path, key)
        enc_sha256 = sha256_file(enc_path)
        if archive_path is not None:
            archive_path.unlink(missing_ok=True)
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


def _sftp_put(host: str, user: str, key_path: str, src: Path, remote_dest: str) -> None:
    """Open a paramiko SFTP session and upload src to remote_dest.

    Raises paramiko.SSHException or OSError; always closes transport.
    """
    transport = paramiko.Transport((host, 22))
    transport.banner_timeout = 30
    transport.auth_timeout = 30
    try:
        transport.connect(
            username=user,
            pkey=paramiko.RSAKey.from_private_key_file(key_path),
        )
        sftp = paramiko.SFTPClient.from_transport(transport)  # type: ignore[arg-type]
        try:
            sftp.put(str(src), remote_dest)
        finally:
            sftp.close()
    finally:
        transport.close()


def upload_deliverable(
    path: str,
    destination: str = ".",
) -> dict[str, Any]:
    """Upload encrypted deliverable over SFTP (paramiko) if configured.

    dry_run: emits sftp command with $FTOS_SFTP_* NAME placeholders.
    live: uses paramiko (values never surfaced in output).
    """
    src = Path(path)
    fname = src.name
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
    try:
        _sftp_put(
            cfg["FTOS_SFTP_HOST"],  # type: ignore[index]
            cfg["FTOS_SFTP_USER"],  # type: ignore[index]
            cfg["FTOS_SFTP_KEY"],  # type: ignore[index]
            src,
            remote_dest,
        )
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


def _enrich_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add sha256 and name to each file entry if missing."""
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
    return enriched


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

    enriched = _enrich_files(files)
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

    result_data.update(_try_pdf_packaging(dest))
    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrappers without `store` kwarg
# ---------------------------------------------------------------------------


# fmt: off
def _mcp_merge_lora_weights(base_model: str, adapter_path: str, output_path: str, local_python: bool = False) -> dict[str, Any]:
    return merge_lora_weights(base_model=base_model, adapter_path=adapter_path, output_path=output_path, local_python=local_python)


def _mcp_quantize_model(model_path: str, format: str = "gguf", bits: int = 4, output_path: str | None = None, local_python: bool = False) -> dict[str, Any]:
    return quantize_model(model_path=model_path, format=format, bits=bits, output_path=output_path, local_python=local_python)


def _mcp_build_inference_container(model_path: str, engine: str = "vllm", project_id: str | None = None) -> dict[str, Any]:
    return build_inference_container(model_path=model_path, engine=engine, project_id=project_id)


def _mcp_generate_inference_config(port: int = 8000, context_length: int = 4096, max_concurrent: int = 4, engine: str = "vllm", api_key_env_name: str = "API_KEY", extra_params: dict[str, Any] | None = None, project_id: str | None = None) -> dict[str, Any]:
    return generate_inference_config(port=port, context_length=context_length, max_concurrent=max_concurrent, engine=engine, api_key_env_name=api_key_env_name, extra_params=extra_params, project_id=project_id)


def _mcp_test_inference_api(prompts: list[str], base_url: str | None = None, model: str = "ftos-model", max_tokens: int = 64, api_key_env: str = "API_KEY") -> dict[str, Any]:
    return test_inference_api(prompts=prompts, base_url=base_url, model=model, max_tokens=max_tokens, api_key_env=api_key_env)


def _mcp_encrypt_deliverable(paths: list[str], output_dir: str | None = None) -> dict[str, Any]:
    return encrypt_deliverable(paths=paths, output_dir=output_dir)


def _mcp_upload_deliverable(path: str, destination: str = ".") -> dict[str, Any]:
    return upload_deliverable(path=path, destination=destination)


def _mcp_generate_delivery_note(project_id: str, files: list[dict[str, Any]], prestataire_nom: str = "[PRESTATAIRE]", client_nom: str = "[CLIENT]") -> dict[str, Any]:
    return generate_delivery_note(project_id=project_id, files=files, prestataire_nom=prestataire_nom, client_nom=client_nom)
# fmt: on


# fmt: off
_MCP_TOOLS = [
    (_mcp_merge_lora_weights,        "Emit the LoRA merge command (base + adapter → merged 16-bit) — dry_run unless FTOS_LOCAL_PYTHON configured."),
    (_mcp_quantize_model,            "Emit the quantization command for GGUF/GPTQ/AWQ — dry_run unless FTOS_LOCAL_PYTHON configured."),
    (_mcp_build_inference_container, "Render Dockerfile.infer and emit docker build command — dry_run unless local docker configured."),
    (_mcp_generate_inference_config, "Produce inference server config (port, api key NAME ref, context, limits) — no secrets embedded."),
    (_mcp_test_inference_api,        "Send test requests to a running inference container — dry_run curl unless base_url provided."),
    (_mcp_encrypt_deliverable,       "AES-256-GCM encrypt deliverable file(s); key returned ONCE in data, never persisted."),
    (_mcp_upload_deliverable,        "Upload encrypted deliverable over SFTP — dry_run unless FTOS_SFTP_* configured."),
    (_mcp_generate_delivery_note,    "Render delivery note with file list + SHA256 each + decryption procedure."),
]
# fmt: on


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all packaging tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
