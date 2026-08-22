"""Shared helpers for reading fields off the pipeline's event dicts.

Event dicts flow through this codebase from several producers with slightly
different shapes: real parsed events (tracker/parser_fast.py) carry
``volume``; hand-built/legacy/synthetic events (tests, some internal
construction) carry ``velocity``. Every consumer used to defensively read
both with a hand-rolled fallback, and the idiom had already drifted on two
axes -- key precedence (``velocity``-first in most of ``nes/``/
``dpcm_sampler/``/``arranger/``, ``volume``-first in ``tracker/``) and
missing-key default (0 almost everywhere, 100 at two sites) -- with nothing
pinning the two conventions in sync (#460/TD-40).
"""


def event_velocity(event, default=0):
    """Read an event's loudness, checking ``velocity`` before ``volume``.

    ``velocity`` takes precedence when an event carries both keys with
    different values -- matching this codebase's largest single cluster of
    the idiom (``nes/emulator_core.py``, 9 of the 15 sites this helper
    consolidates). In practice a real producer only ever emits one of the
    two keys, so precedence only matters for a hand-built/malformed event
    carrying both; this consolidation exists to make that non-divergent
    across call sites, not to optimize a hot path either key order would
    already handle identically.

    ``default`` is returned when neither key is present. Most call sites
    want 0 (treat a loudness-less event as silent/note-off, the safer
    failure mode on malformed input) -- pass a different value only where
    that's deliberately wrong for the call site's own semantics (e.g. a
    pattern-similarity scorer that wants an "average" loudness rather than
    "silent" for a genuinely missing value, so a missing-both edge case
    doesn't skew the comparison toward maximal dissimilarity).
    """
    return event.get('velocity', event.get('volume', default))
