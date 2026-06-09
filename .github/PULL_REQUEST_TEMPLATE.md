<!-- PR title MUST follow Conventional Commits, e.g. "feat(tools): add new C1 tool" -->

## Description

<!-- What does this PR do and why? Which fine-tuning lifecycle step is affected? -->

## Linked issue

Closes #

## Type of change

- [ ] fix (non-breaking bug fix)
- [ ] feat (non-breaking new feature)
- [ ] BREAKING CHANGE (fix or feature that changes existing behavior or Zero-Data contract)
- [ ] docs / chore / refactor / test / ci / perf / build

## Zero-Data compliance (for new/modified tools)

- [ ] New tool class declared (C1 / C2 / C3)
- [ ] C1/C3 tools cannot open sockets (no gate() call needed; covered by test_zero_data.py)
- [ ] C2 tools return `executed=False, dry_run=True` when the required env var is absent
- [ ] No secrets returned in tool output values

## How was this tested?

<!-- Commands run, scenarios covered, new tests added. -->

## Checklist

- [ ] PR title follows Conventional Commits
- [ ] Tests added/updated and passing (`pytest`)
- [ ] Coverage held at >= 90% (`pytest --cov-fail-under=90`)
- [ ] Coverage aspiration >= 95%
- [ ] Lint and format checks pass locally (`ruff check .` and `black --check .`)
- [ ] Docs / CHANGELOG updated where relevant (or handled by release automation)
- [ ] No secrets, credentials, or PII committed
- [ ] Tool Catalogue in README.md updated if tools added/renamed
