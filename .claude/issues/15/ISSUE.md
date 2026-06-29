# F-06: Step-by-step path has no prepare/compile/validate parity; run_prepare exits 0 on failure

**Severity:** MEDIUM · **Domain:** pipeline

(a) run_prepare prints success only inside `if prepare_project(...)` with no else, and
prepare_project raises uncaught — failures surface as a traceback or silent exit 0.
(b) No compile/validate subcommand, so step-by-step ROMs never hit the validation gate.

## Suggested Fix
Add try/except + else: sys.exit(1) to run_prepare; add a `compile` subcommand that compiles
+ validates a prepared project.
