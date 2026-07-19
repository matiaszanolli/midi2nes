"""Repo-hygiene guards for dead-code removal and doc cruft.

- #203/NH-28: nes/mmc3_init.asm was fully dead (never assembled into any
  generated project — the live reset/NMI/IRQ/APU-init is inline in
  NESProjectBuilder). Pin its removal so it can't silently reappear.
- #229/TD-19: a checked-in audit report leaked trailing </content>/</invoke>
  tool-call markup. Guard that no audit doc ends with such a bare tag line.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def test_dead_mmc3_init_asm_is_removed():
    # Regression (#203/NH-28): the dead alternate reset/NMI/APU-init file must
    # stay deleted. The live init is the inline template in
    # nes/project_builder.py:_generate_main_asm. The only surviving mention of
    # the name is the defensive `.replace(...)` strip that neutralizes a stale
    # include of this (now non-existent) file.
    assert not (REPO_ROOT / "nes" / "mmc3_init.asm").exists(), \
        "nes/mmc3_init.asm was removed as dead code (#203); do not re-add it"


# Bare closing tags that indicate leaked tool-call/harness serialization.
_LEAKED_MARKUP = {"</content>", "</invoke>", "</invoke>", "</function_calls>"}


def test_audit_docs_have_no_leaked_tool_call_markup():
    # Regression (#229/TD-19): match a *bare full-line* tag only, not prose that
    # mentions the tag inside backticks — the 2026-07-03 report legitimately
    # documents this very finding and must not trip the guard.
    offenders = []
    for md in (REPO_ROOT / "docs" / "audits").glob("*.md"):
        for i, line in enumerate(md.read_text(errors="ignore").splitlines(), 1):
            if line.strip() in _LEAKED_MARKUP:
                offenders.append(f"{md.name}:{i}: {line.strip()}")
    assert not offenders, "Leaked tool-call markup in audit docs:\n" + "\n".join(offenders)
