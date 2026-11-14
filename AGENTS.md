# Shared coding-agent instructions

Try to be as helpful as you can be even if it means taking another step forward in the progress of the code.

Read all of `CLAUDE.md`, `docs/IMPLEMENTATION.md` and `docs/STATUS.md` before changing code. Follow their ownership boundaries, scientific honesty rules, schema 1.0 contract and Git workflow. Preserve teammates' work. No raw source rasters, generated logs, or secrets in git.

## Mandatory logging, observability, and execution traceability

Section 16 of `CLAUDE.md` is mandatory for every agent and every current/future code PR, including Python, TypeScript/React and CI/deployment. Implement operational logging in the code, not only its PR description. Include adjacent validation, input/output tracing, safety/state decisions, error handling, aggregate timing and logging tests in the same PR. Small pure functions can be observed at the calling operation; documentation-only changes need no new runtime logging.

Python uses standard `logging` and `pipeline/logging_config.py`; prefer JSON with UTC timestamp, level, consistent execution `run_id`, stage/event and applicable IDs, duration, status, reason, evidence and thresholds. Observe acquisition, raster/coordinate validation, analysis, hazards, routes and EVA budgets, simulations, export and schema validation. React uses a small shared browser interface for meaningful data failures and stage/safety changes; respect Yasser's ownership and document handoffs for his code. CI job failures must remain visible.

Record unexpected exceptions with stack traces and propagate them as appropriate. Missing/uncertain measurements, excluded terrain and unavailable routes must be observable. Never treat pathfinding success as astronaut clearance. Preserve `nasa_derived`, `inferred` and `simulated` evidence. Logging must not bypass validation, change deterministic data outputs or turn failure into success. No secrets, unnecessary user data, per-cell logs or additional observability services. DEBUG is configurable and off by default; JSONL belongs in ignored `pipeline/logs/`.

Test significant structured events/context, errors, safety failures, evidence, deterministic outputs, secret exclusion and logging-failure behavior through the normal suite. Use Docker Desktop for local Python testing in dedicated Terps containers; do not alter Capstone Triage resources. Python dependency changes use `uv`, `pyproject.toml` and `uv.lock`; never hand-edit the lock.

Every code PR description must include `## Logging and observability` and the ten-item checklist from CLAUDE.md Section 16, with N/A explanations as appropriate. Include a walkthrough at the end. Logging/testing gaps block merge readiness. Verify `frontend`, `pipeline` and `full-suite` on the exact latest commit before an authorized merge; never claim repository enforcement without verified GitHub protection. Update STATUS with results, blockers and handoffs. Follow the user's explicit merge instructions; do not infer permission to merge unrelated PRs.
