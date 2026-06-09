# Phase 7 — Packaging & Delivery

> Tools 39-46 | Class: C2 (39, 40, 41, 43, 45) + C1 (42, 44, 46)
> Back: [SKILL.md](../SKILL.md)

---

## Purpose

Package the fine-tuned model for production deployment: merge LoRA adapter,
quantize, build inference container, encrypt the deliverable, upload, and
issue a formal delivery note with SHA256 hashes. This phase produces the
primary contractual deliverable.

**Execution boundary:** merge and quantize operations (tools 39, 40) run in the
client enclave or via unsloth-server — Fine-Tuning OS emits the commands.
Encryption (tool 44) is C1 (local, no network) — runs on whatever path the
operator has access to (merged model that has been transferred out after client
authorization, or the AES-encrypted archive the client sends back).

---

## Inputs

- Checkpoint path (from Phase 4)
- Base model path (cached in Phase 1)
- Target deployment format (GGUF/AWQ/EXL2/GPTQ/16-bit)
- Inference engine preference (SGLang/vLLM/TGI/llama.cpp)
- Delivery channel (SFTP/cloud/secure transfer)

## Outputs

- Merged model (16-bit or quantized)
- `docker/Dockerfile.infer` + inference config
- AES-256-GCM encrypted archive (`*.enc`)
- `deliverables/delivery_note.pdf` + SHA256
- Upload confirmation or dry_run command

---

## Tool Sequence

### Step 1 — Merge LoRA weights (C2)

```
merge_lora_weights(
    base="/models/qwen3-7b",
    adapter="/checkpoints/step-500",
    out="/models/qwen3-7b-acme-merged"
)
# → {command: "python -c 'from unsloth import FastLanguageModel; ...'", dry_run: true}
# or {executed: true, output_path: "/models/qwen3-7b-acme-merged"} via unsloth-server
```

Routes to unsloth-server (`merge_lora` tool) if available, else emits the merge
command for client execution.

### Step 2 — Quantize (C2)

Choose format per target (see [sota-may-2026.md](sota-may-2026.md) §14.3):

```
quantize_model(
    model_path="/models/qwen3-7b-acme-merged",
    format="gguf",          # or "awq", "gptq", "exl2", "fp8"
    bits=4                  # Q4_K_M for GGUF
)
# → {command: "llama.cpp convert-hf-to-gguf.py ...", dry_run: true}
# or via unsloth-server save_gguf / quantize_awq
```

**Format selection guide:**

| Target | Format | Command routed to |
|--------|--------|------------------|
| Ollama / LM Studio / CPU | GGUF Q4_K_M | llama.cpp |
| vLLM / SGLang multi-user | AWQ | AutoAWQ |
| NVIDIA single-user max throughput | EXL2 | ExLlamaV2 |
| vLLM fallback | GPTQ + Marlin | AutoGPTQ |

### Step 3 — Build inference container (C2)

```
build_inference_container(
    model_path="/models/qwen3-7b-acme-merged-q4",
    engine="vllm"           # or "sglang", "llama.cpp", "tgi"
)
# → {dockerfile: "...", command: "docker build -t acme-infer:v1 ...", dry_run: true}
```

The generated `Dockerfile.infer` exposes an **OpenAI-compatible API** endpoint.
Run `audit_dockerfile_security` on the infer Dockerfile as well.

### Step 4 — Generate inference config (C1)

```
generate_inference_config(
    port=8000,
    api_key="${CLIENT_API_KEY}",
    max_tokens=2048,
    context_len=4096,
    engine="vllm"
)
# → {config_path: ".../config/inference.yaml"}
```

### Step 5 — Test inference API (C2)

```
test_inference_api(
    base_url="http://localhost:8000",
    prompts=["Hello, what can you do?", "Summarize: synthetic_instruction_0001"]
)
# → {results: [{prompt: "...", response: "...", latency_ms: 142}], dry_run: false}
# or {command: "curl -X POST http://localhost:8000/v1/completions ...", dry_run: true}
```

Use only non-sensitive synthetic prompts for API testing.

### Step 6 — Encrypt deliverable (C1)

```
encrypt_deliverable(paths=[
    ".../deliverables/acme-ft-merged-q4.gguf",
    ".../reports/security_report.pdf",
    ".../reports/performance_report.pdf"
])
# → {
#     archive: ".../deliverables/acme-ft-v1.enc",
#     key: "aes256gcm:base64:...",   # shown ONCE, store securely
#     sha256: "a3f8..."
# }
```

**Key management:**
- The AES-256-GCM key is displayed **once** at generation time
- Store it in the operator's password manager / HSM
- Never log it, never embed it in reports
- Send to client via separate secure channel (encrypted email, secure file share)
- The `delivery_note.pdf` includes the SHA256 but **not** the key

### Step 7 — Upload deliverable (C2)

```
upload_deliverable(
    path=".../deliverables/acme-ft-v1.enc",
    destination="sftp://client.sftp.example.com/deliveries/"
)
# → {command: "sftp client.sftp.example.com ...", dry_run: true}
# or {executed: true, remote_path: "sftp://...", sha256_verified: true}
```

Requires `FTOS_SFTP_HOST`, `FTOS_SFTP_USER`, `FTOS_SFTP_KEY`.

### Step 8 — Generate delivery note (C1)

```
generate_delivery_note(
    project_id="acme-ft-001",
    files=[
        {"name": "acme-ft-v1.enc", "sha256": "a3f8...", "size_mb": 4200},
        {"name": "security_report.pdf", "sha256": "b7c2..."},
        {"name": "performance_report.pdf", "sha256": "d1e4..."}
    ]
)
# → {note_md: ".../deliverables/delivery_note.md", note_pdf: ".../deliverables/delivery_note.pdf"}
```

The delivery note includes:
- File list with SHA256 hashes
- AES-256-GCM decryption procedure (without the key)
- Delivery date and version
- Signature line

---

## Go/No-Go Gate

- [ ] Merged model exists (or command provided for client execution)
- [ ] Quantized deliverable produced in target format
- [ ] Inference API responds to test prompts
- [ ] Encrypted archive SHA256 matches source
- [ ] Delivery note generated (MD + PDF)
- [ ] AES key stored securely (not in any project file)
- [ ] Upload confirmed (or command provided to client)

---

## Decryption Procedure (for delivery note)

```bash
# Recipient decrypts the deliverable:
openssl enc -d -aes-256-gcm -in acme-ft-v1.enc -out acme-ft-v1.tar.gz \
  -pass pass:"<AES_KEY_PROVIDED_SEPARATELY>"
tar -xzf acme-ft-v1.tar.gz
# Verify: sha256sum acme-ft-v1.gguf
# Compare to SHA256 in delivery note
```

---

## Common Pitfalls

| Pitfall | Detection | Fix |
|---------|-----------|-----|
| Merge outputs large float16 model | Disk full | Ensure 2× model size free before merge |
| GGUF conversion fails | `quantize_model` error | Check llama.cpp version compatibility |
| Inference API timeout | `test_inference_api` latency > 5s | Reduce context, check GPU availability |
| Key lost | Decryption impossible | Always store in password manager before delivery |
| SFTP auth fails | `upload_deliverable` error | Check `FTOS_SFTP_*` env vars |
