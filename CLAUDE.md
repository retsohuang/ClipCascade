<!-- SDD:START -->

# SDD Instructions

This project uses sdd for spec-driven development. Changes live in `sdd/changes/` and need no living specs: a change has spec.md and tasks.md. Lasting decisions go to `docs/adr/` and `GLOSSARY.md`.

## Use `/sdd-*` skills when:

- Audit a change's artifacts for consistency before implementing → `/sdd-analyze`
- Reproduce a bug and find its cause before choosing how to fix it → `/sdd-debug`
- Implementation is done: archive the change → `/sdd-finish`
- Grill a plan, test seams included, before proposing a change → `/sdd-grill-me`
- Tasks are ready to implement, or a half-implemented change should resume → `/sdd-implement`
- Update a change that already has implemented work → `/sdd-ingest`
- User wants to plan, propose or design a change, or to rewrite or tidy one that has no task done yet → `/sdd-plan`
- Save a settled discussion now and run /sdd-plan on it later → `/sdd-plan-later`
- Add, change or debug a stage in sdd/sdd.yaml → `/sdd-stages`

## Workflow

```
/sdd-debug? → /sdd-grill-me? → /sdd-plan → /sdd-implement ⇄ /sdd-ingest → /sdd-finish
```

- `/sdd-implement` builds one section of tasks.md at a time in a fresh subagent, then commits and reviews it.
- Requirements change mid-work? `/sdd-ingest`, then re-run `/sdd-implement`.

## Extra stages (sdd/sdd.yaml)

- `fork-release`: finish.after

<!-- SDD:END -->
