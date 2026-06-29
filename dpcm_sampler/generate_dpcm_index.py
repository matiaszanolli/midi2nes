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
