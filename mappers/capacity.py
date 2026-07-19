"""Music.asm ROM-size estimation and the mapper capacity pre-flight.

Extracted from ``main.py`` (#363/MAP-2026-07-19-3) so the same gate the CLI runs
is reusable by library entry points — notably ``NESProjectBuilder.prepare_project``
— rather than living only in the CLI layer. ``main.py`` re-exports these names,
so ``from main import estimate_segment_sizes`` (and the check helpers) still work.
"""

import math
import re
from pathlib import Path
from typing import Dict

from .base import BaseMapper


def estimate_segment_sizes(music_asm_path) -> Dict[str, int]:
    """ROM byte totals music.asm emits (.byte/.word/.incbin), keyed by the active
    `.segment "NAME"`.

    Per-segment rather than a single total because a banked mapper (MMC3)
    distributes data across distinct PRG regions, and the binding limit is the
    region each segment lands in, not the full PRG (#126, #127). ld65 remains the
    exact backstop. .res lives in RAM/ZP (not PRG ROM) and is ignored. A bounded
    `.incbin "f", 0, N` (a truncated DPCM sample, #68) counts N, not the file size.

    `.align N` rounds the *running offset within the current segment* up to the
    next multiple of N, mirroring ld65's actual behavior, rather than being
    ignored -- `DpcmPacker.generate_assembly` emits `.align 64` before every
    packed DPCM sample (#301/MAP-2026-07-06-2), and skipping it previously let
    a segment's estimated size fall up to 63 bytes/sample short of ld65's real
    total, the exact slack `DpcmPacker`'s own `aligned_size` bank-fit check
    already accounts for.
    """
    music_path = Path(music_asm_path)
    if not music_path.exists():
        return {}
    sizes = {}
    current = None
    base_dir = music_path.parent
    for raw in music_path.read_text().splitlines():
        line = raw.split(';', 1)[0].strip()  # drop comments
        low = line.lower()
        if low.startswith('.segment'):
            m = re.search(r'"([^"]+)"', line)
            if m:
                current = m.group(1)
            continue
        if low.startswith('.align'):
            m = re.search(r'\.align\s+(\d+)', line, re.IGNORECASE)
            if m and current is not None:
                boundary = int(m.group(1))
                if boundary > 0:
                    offset = sizes.get(current, 0)
                    sizes[current] = math.ceil(offset / boundary) * boundary
            continue
        n = 0
        if low.startswith('.byte'):
            n = len([t for t in line[5:].split(',') if t.strip()])
        elif low.startswith('.word'):
            n = 2 * len([t for t in line[5:].split(',') if t.strip()])
        elif low.startswith('.incbin'):
            bounded = re.search(r'"[^"]+"\s*,\s*\d+\s*,\s*(\d+)', line)
            if bounded:
                n = int(bounded.group(1))
            else:
                m = re.search(r'"([^"]+)"', line)
                if m:
                    p = Path(m.group(1))
                    if not p.is_absolute():
                        p = base_dir / p
                    if p.exists():
                        n = p.stat().st_size
        if n:
            sizes[current] = sizes.get(current, 0) + n
    return sizes


def estimate_music_data_size(music_asm_path) -> int:
    """Total ROM data bytes music.asm emits (sum across all segments)."""
    return sum(estimate_segment_sizes(music_asm_path).values())


def check_mapper_capacity(music_asm_path, mapper: BaseMapper) -> int:
    """Pre-flight capacity gate (#11, #126, #127): abort before linking if the
    emitted music data overflows any of the selected mapper's PRG regions.

    Sizes each music.asm segment against the region the mapper's linker config
    loads it into (a banked mapper has several binding regions, not one 510 KB
    ceiling), so an oversized song fails with a clear budget message instead of a
    raw ld65 region overflow. Raises ValueError listing every overflow. Returns
    the total data size for logging.
    """
    segment_sizes = estimate_segment_sizes(music_asm_path)
    errors = mapper.validate_segment_sizes(segment_sizes)
    if errors:
        detail = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(
            f"Music data does not fit the {mapper.name} PRG layout:\n{detail}\n"
            f"Shorten the song or DPCM samples, or select a larger mapper."
        )
    return sum(segment_sizes.values())
