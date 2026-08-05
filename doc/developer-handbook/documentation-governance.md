# Documentation governance

## Same-PR handbook maintenance rule

Update the relevant handbook chapter in the same PR when changing any documented public or structural surface. A pure internal refactor may omit a handbook update only when the PR explicitly explains why no documented behavior changed.

## Surfaces requiring same-PR review

- public imports;
- public classes, functions, protocols, enums, and constants;
- fields and defaults;
- validation and serialization;
- enum wire values and ID syntax;
- request, response, and SSE fields;
- endpoints;
- CLI flags;
- environment variables and configuration keys;
- package ownership and dependency direction;
- compatibility paths and migration state;
- runtime flows;
- installation or validation commands.

## Maintenance rules

Use the approved status vocabulary: Historical, Current, Transitional, Target / Accepted, Proposed, Deprecated. Never document speculative APIs as Current before implementation merges. Preserve one detailed source of truth and link to it instead of rewriting whole documents. Keep root README changes minimal.
