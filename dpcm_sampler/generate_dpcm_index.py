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
    - When ``sample_ids`` is provided, only entries whose catalog ``id`` matches
      are loaded — so a song ships just the drums it references rather than the
      whole 1923-sample catalog, which would overflow the 60-bank budget
      (#140). ``None`` packs everything, keyed by the catalog's own id.

      ``sample_ids`` accepts two shapes:
        - a set of catalog ints/strings (legacy shape): entries are keyed by
          their own catalog id, as before.
        - a dict ``{dense_id: catalog_id}`` (the shape
          ``get_dpcm_sample_ids_from_frames`` now returns, #200/D-14): a
          matching catalog entry is keyed by its **dense** id instead of its
          (potentially huge, up to 1922) catalog id, so the packer's
          positional lookup tables stay compact and line up with what the
          bytecode's dense-remapped ``note - 1`` actually indexes at runtime.

    Samples are added in ascending index-id order, matching the positional
    lookup tables the engine indexes by ``sample_id``. Returns
    ``(loaded, skipped)``.
    """
    loaded = 0
    skipped = 0
    catalog_to_dense = None
    if isinstance(sample_ids, dict):
        catalog_to_dense = {int(catalog_id): dense_id
                            for dense_id, catalog_id in sample_ids.items()}

    for sample in sorted(dpcm_index.values(), key=lambda s: int(s['id'])):
        sid = sample['id']
        sid_int = int(sid) if not isinstance(sid, int) else sid
        if catalog_to_dense is not None:
            if sid_int not in catalog_to_dense:
                continue
        elif sample_ids is not None and sid_int not in sample_ids:
            continue
        sample_path = resolve_dpcm_sample_path(sample['filename'], index_path)
        if sample_path is None:
            skipped += 1
            if verbose:
                print(f"  ⚠️ Warning: DPCM sample not found: {sample['filename']}")
            continue
        pack_id = catalog_to_dense[sid_int] if catalog_to_dense is not None else sid
        packer.add_sample(
            str(pack_id),
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
    """Extract the DPCM sample ids referenced in frame data.

    Frame DPCM entries encode ``note = dense_id + 1`` (0 is the rest/change
    sentinel), where ``dense_id`` is a song-local, compact 0..N-1 renumbering
    of the real dpcm_index.json catalog ids actually used -- assigned by
    ``NESEmulatorCore.process_all_tracks`` so a single byte never has to
    represent the full 0-1922 catalog range (a real song rarely references
    anywhere near 255 distinct drums, so this survives the byte ceiling
    instead of two different high catalog ids both clamping to note 255 and
    silently aliasing onto the same wrong sample, #200/D-14).

    ``frames['dpcm_sample_map']`` (dense_id -> catalog_id, string keys since
    it round-trips through JSON) is emitted alongside ``frames['dpcm']`` to
    carry that mapping to the export/pack stage. Its absence (frames.json
    from before this fix, or any other producer that never remapped ids)
    falls back to treating dense ids as catalog ids directly -- the
    pre-fix, unremapped behavior.

    Returns a ``dict[int, int]`` of ``{dense_id: catalog_id}`` for the
    samples this song references, which callers can pass to
    ``load_dpcm_index_into_packer(sample_ids=...)``.
    """
    sample_map = frames.get('dpcm_sample_map', {})
    ids = {}
    for frame_data in frames.get('dpcm', {}).values():
        note = frame_data.get('note', 0)
        if note and int(note) > 0:
            dense_id = int(note) - 1
            ids[dense_id] = int(sample_map.get(str(dense_id), dense_id))
    return ids


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python generate_dpcm_index.py dmc_folder output.json")
        sys.exit(1)

    generate_dpcm_index(sys.argv[1], sys.argv[2])
