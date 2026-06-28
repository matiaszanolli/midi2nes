# M-9: compile_rom broad except Exception prints then returns False — masks tracebacks without verbose

**Severity:** LOW · **Domain:** mappers · **Source:** AUDIT_MAPPERS_2026-06-28.md

## Description
`compile_rom` catches `CompilationError`, `ValidationError`, and a catch-all `except Exception`, printing `[ERROR] …` and returning `False`. It surfaces the message (clears the HIGH floor), but the catch-all swallows the stack trace with no verbose traceback at this layer. An unexpected exception loses its origin.

## Evidence
```
compiler.py:173-175  except Exception as e: print(f"[ERROR] Compilation failed: {e}"); return False
```

## Impact
Harder debugging of unexpected compiler failures; not a correctness bug.

## Related
M-4.

## Suggested Fix
In the catch-all, print `traceback.format_exc()` when `verbose`.
