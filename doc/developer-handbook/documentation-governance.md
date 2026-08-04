# Documentation governance

[Back to handbook](README.md). The mandatory Agent rule is in
[`AGENTS.md`](../../AGENTS.md).

## One authority, synchronized changes

Use the root README for introduction, the package RFC for accepted ownership,
this handbook for developer navigation/API reference, component READMEs for
operation, environment docs for deployment, architecture docs for maintained
decisions, research notes for unresolved investigation, and blog posts for
history. Link to detailed authority instead of copying it. An Issue remains the
authority for accepted but unimplemented work until maintained documentation is
updated; an unmerged PR is never Current.

A PR must update the affected handbook chapter in the same PR when it changes a
public API; fields/defaults/validation/wire values; configuration/environment/
CLI/endpoints; ownership/dependencies; compatibility/migration status; runtime
flows; or installation/validation commands. Internal-only changes may omit an
update only with an explicit PR explanation. Avoid unrelated rewrites and keep
root README discovery changes minimal.

## Maintaining evidence

Inspect the owning source and focused tests. Prefer relative links to them.
State `Historical`, `Current`, `Transitional`, `Target / Accepted`, `In review`,
`Proposed`, or `Deprecated` precisely. Never infer ID formats from sample strings
or describe a model as production wiring. Validate all local links, public
`__all__` coverage, explicit package-map coverage, absent targets' status, and
wheel exclusion with [`test_developer_handbook.py`](../../test/test_developer_handbook.py).

When adding a canonical module with a non-empty explicit `__all__`, add it to the
API catalog. When changing the explicit package list, update the package map.
When moving an authority, repair inbound links without creating competing prose.
