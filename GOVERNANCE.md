# Governance

This document describes how the **fine-tuning-os** project is governed and how decisions are made.
(Default model: maintainer-led with lazy consensus. Adapt to a steering committee as the project grows.)

## Roles

### Users

Anyone who uses the project. Users contribute by filing issues, joining discussions, and helping
others. No special permissions.

### Contributors

Anyone who submits a pull request, issue, or documentation change. All contributions go through the
standard PR review process described in [CONTRIBUTING.md](./CONTRIBUTING.md).

### Maintainers

Trusted contributors with write access who review and merge PRs, triage issues, and shepherd
releases. Maintainers are listed in [CODEOWNERS](./.github/CODEOWNERS).

**Becoming a maintainer:** sustained, high-quality contributions over time. Existing maintainers
nominate a candidate; nomination passes by lazy consensus (no objections within 7 days) or a simple
majority vote of maintainers if objections are raised.

**Stepping down / inactivity:** maintainers inactive for 6+ months may be moved to emeritus status.

## Decision making

We use **lazy consensus**:

- Routine changes (bug fixes, docs, dependency bumps): one maintainer approval + green CI is enough
  to merge.
- Significant changes (new features, API/behavior changes, Zero-Data contract changes, new tool
  modules): open a PR and/or an **ADR** (see `docs/`). If no maintainer objects within **7 days**,
  it is approved.
- **Disagreements** that cannot be resolved by discussion are decided by a **simple majority vote**
  of maintainers. The lead maintainer breaks ties.

## Releases

Releases follow [SemVer](https://semver.org/) and are automated from Conventional Commits via
release-please (see [CHANGELOG.md](./CHANGELOG.md)). Any maintainer may approve and merge the
release PR.

## Changing this document

Amendments to GOVERNANCE.md follow the "significant change" process above (PR + 7-day lazy consensus
among maintainers).

## Code of Conduct

All participation is governed by the [Code of Conduct](./CODE_OF_CONDUCT.md).
