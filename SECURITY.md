# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| latest `main` / newest release | :white_check_mark: |
| older releases | :x: |

We provide security fixes for the most recent minor release. Please upgrade before reporting.

## Zero-Data security posture

fine-tuning-os is designed with a **Zero-Data** architecture:

- **No secrets on disk.** All credentials are read from environment variables at call time.
  No secret is ever written to files or returned in tool output values.
- **C1/C3 tools cannot open network sockets.** This is enforced and verified by the test suite
  on every CI run (`tests/test_zero_data.py`).
- **C2 dry-run is safe.** When an env var is absent, the tool returns the command string with
  env var *name* references only — never literal secret values.
- **Filesystem confinement.** Every write is anchored under `FTOS_WORKSPACE`. Path traversal
  outside the workspace root raises an explicit error.

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Please use **GitHub's private vulnerability reporting**:
[Report a vulnerability](https://github.com/Casius999/fine-tuning-os/security/advisories/new).

Alternatively, email **casius4126@gmail.com**. If you need encryption, request our PGP key in your
first message.

Please include:

- A description of the issue and its impact.
- Steps to reproduce or a proof of concept.
- Affected version(s) / commit SHA.
- Any suggested remediation.

## Our commitment

- **Acknowledgement** within **72 hours**.
- **Triage and severity assessment** within **7 days**.
- We will coordinate a fix and a [GitHub Security Advisory (GHSA)](https://github.com/Casius999/fine-tuning-os/security/advisories),
  request a CVE where appropriate, and credit you (unless you prefer to remain anonymous).
- Please allow **90 days** for coordinated disclosure before publicizing details.

## Scope

This policy covers the code in this repository. Vulnerabilities in third-party dependencies should
be reported upstream; we monitor them via Dependabot/Renovate, `dependency-review-action`, and
SBOM-based scanning (syft / grype / osv-scanner).
