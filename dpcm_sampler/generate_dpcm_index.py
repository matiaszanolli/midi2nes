import os
import json
from pathlib import Path

# Name of the sample root that `generate_dpcm_index` scans. Entries in
# dpcm_index.json store `filename` relative to this folder (e.g. a bare
# "Kick.dmc"), so consumers must re-join it against this root to locate the
# real file — see resolve_dpcm_sample_path below.
DPCM_ROOT_DIRNAME = "dmc"


def resolve_dpcm_sample_path(filename, index_path):
    """Resolve a dpcm_index.json `filename` entry to an existing file.

    Index entries are stored relative to the scanned ``dmc/`` root (see
    ``generate_dpcm_index``), so a bare name only resolves once re-joined with
    that root. Resolution order, first hit wins:

    1. an absolute path that exists (future-proofing for absolute indexes);
    2. the path as-is relative to the current working directory (back-compat);
    3. ``<index_dir>/dmc/<filename>`` — the shipped layout;
    4. ``<index_dir>/<filename>``.

    Returns a ``Path`` to an existing file, or ``None`` if nothing resolved.
    """
    index_dir = Path(index_path).resolve().parent
    candidates = [
        Path(filename),
        index_dir / DPCM_ROOT_DIRNAME / filename,
        index_dir / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_dpcm_index_into_packer(packer, dpcm_index, index_path, verbose=False,
                                sample_ids=None):
    """Resolve every entry in ``dpcm_index`` and add it to ``packer``.

    Shared by both DPCM packing call sites so the same robustness rules apply at
    each (#68 SIBLING):

    - Files are resolved against the ``dmc/`` root (#64); an entry whose file is
      missing is skipped with an optional warning.
    - Samples longer than the NES 4081-byte DMC limit are truncated rather than
      raising, so one oversized sample never aborts the whole pack (#68).
    - When ``sample_ids`` is provided (a set of ints or strings), only entries
      whose ``id`` matches are loaded. This prevents packing the entire 1923-entry
      shipped catalog for songs that only use a handful of samples (#140).

    Samples are added in ascending index-id order, matching the positional
    lookup tables the engine indexes by ``sample_id``. Returns
    ``(loaded, skipped)``.
    """
    loaded = 0
    skipped = 0
    for sample in sorted(dpcm_index.values(), key=lambda s: int(s['id'])):
        sid = sample['id']
        sid_int = int(sid) if not isinstance(sid, int) else sid
        if sample_ids is not None and sid_int not in sample_ids:
            continue
        sample_path = resolve_dpcm_sample_path(sample['filename'], index_path)
        if sample_path is None:
            skipped += 1
            if verbose:
                print(f"  ⚠️ Warning: DPCM sample not found: {sample['filename']}")
            continue
        packer.add_sample(
            str(sid),
            str(sample_path.absolute()).replace('\\', '/'),
            sample.get('pitch', 15),
            truncate=True,
        )
        loaded += 1
    return loaded, skipped


def generate_dpcm_index(dmc_folder, output_json):
    index = {}
    current_id = 0

    for root, _, files in os.walk(dmc_folder):
        for f in sorted(files):
            if f.lower().endswith('.dmc'):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, dmc_folder)
                name = os.path.splitext(os.path.basename(f))[0]

                index[name] = {
                    "id": current_id,
                    "filename": rel_path.replace("\\", "/")
                }
                current_id += 1

    with open(output_json, 'w') as f:
        json.dump(index, f, indent=2)

    print(f"Indexed {len(index)} DPCM samples → {output_json}")


def get_dpcm_sample_ids_from_frames(frames):
    """Extract the set of DPCM sample IDs referenced in frame data.

    Frame DPCM entries encode ``note = sample_id + 1`` (0 is the rest/change
    sentinel).  Returns a ``set[int]`` of the sample IDs actually used, which
    callers can pass to ``load_dpcm_index_into_packer(sample_ids=...)``.
    """
    ids = set()
    for frame_data in frames.get('dpcm', {}).values():
        note = frame_data.get('note', 0)
        if note and int(note) > 0:
            ids.add(int(note) - 1)
    return ids


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python generate_dpcm_index.py dmc_folder output.json")
        sys.exit(1)

    generate_dpcm_index(sys.argv[1], sys.argv[2])
