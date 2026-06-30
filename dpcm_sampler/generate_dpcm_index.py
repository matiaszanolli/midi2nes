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


def used_dpcm_sample_ids(frames):
    """Sample ids the DPCM channel of ``frames`` actually triggers.

    DPCM frames encode the sample id as ``note = sample_id + 1`` (the engine
    recovers ``sample_id = note - 1`` to index the lookup tables — #9/#65), so the
    set a song references is exactly ``{note - 1 : note > 0}``. Used to pack only
    the drums a song needs instead of the whole catalog (#140).
    """
    dpcm = frames.get('dpcm', {}) if frames else {}
    return {
        fd['note'] - 1
        for fd in dpcm.values()
        if isinstance(fd, dict) and fd.get('note', 0) > 0
    }


def load_dpcm_index_into_packer(packer, dpcm_index, index_path, verbose=False, used_ids=None):
    """Resolve every entry in ``dpcm_index`` and add it to ``packer``.

    Shared by both DPCM packing call sites so the same robustness rules apply at
    each (#68 SIBLING):

    - Files are resolved against the ``dmc/`` root (#64); an entry whose file is
      missing is skipped with an optional warning.
    - Samples longer than the NES 4081-byte DMC limit are truncated rather than
      raising, so one oversized sample never aborts the whole pack (#68).
    - ``used_ids`` (a set of index ids): when given, only those samples are
      packed, so a song ships just the drums it references rather than the whole
      1923-sample catalog, which would overflow the 60-bank budget (#140). The
      packer keeps absolute ids, so the positional tables stay aligned. ``None``
      packs everything.

    Samples are added in ascending index-id order, matching the positional
    lookup tables the engine indexes by ``sample_id``. Returns
    ``(loaded, skipped)``.
    """
    loaded = 0
    skipped = 0
    for sample in sorted(dpcm_index.values(), key=lambda s: int(s['id'])):
        if used_ids is not None and int(sample['id']) not in used_ids:
            continue
        sample_path = resolve_dpcm_sample_path(sample['filename'], index_path)
        if sample_path is None:
            skipped += 1
            if verbose:
                print(f"  ⚠️ Warning: DPCM sample not found: {sample['filename']}")
            continue
        packer.add_sample(
            str(sample['id']),
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

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python generate_dpcm_index.py dmc_folder output.json")
        sys.exit(1)

    generate_dpcm_index(sys.argv[1], sys.argv[2])
