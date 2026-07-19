"""Regression tests for dpcm_index.json filename resolution (issue #64).

The shipped index stores each ``filename`` relative to the scanned ``dmc/``
root (a bare name like ``Kick.dmc``). Consumers used to test
``Path(filename).exists()`` against the current working directory, which never
re-joined the ``dmc/`` root — so every entry failed to resolve and all DPCM
tables shipped empty (percussion silent). ``resolve_dpcm_sample_path`` re-joins
the root relative to the index file, independent of cwd.
"""
import os
import json
from unittest.mock import Mock

from dpcm_sampler.generate_dpcm_index import (
    resolve_dpcm_sample_path,
    generate_dpcm_index,
    load_dpcm_index_into_packer,
    DPCM_ROOT_DIRNAME,
)


def _make_index(tmp_path):
    """Create an index dir with a dmc/ root holding one bare-name sample."""
    dmc_dir = tmp_path / DPCM_ROOT_DIRNAME
    dmc_dir.mkdir()
    sample = dmc_dir / "Kick.dmc"
    sample.write_bytes(b"\x00" * 16)
    index_path = tmp_path / "dpcm_index.json"
    index_path.write_text(json.dumps({"Kick": {"id": 0, "filename": "Kick.dmc"}}))
    return index_path, sample


def test_bare_name_resolves_under_dmc_root(tmp_path):
    index_path, sample = _make_index(tmp_path)
    resolved = resolve_dpcm_sample_path("Kick.dmc", index_path)
    assert resolved is not None
    assert resolved.resolve() == sample.resolve()


def test_resolution_is_independent_of_cwd(tmp_path, monkeypatch):
    """Bare names must resolve even when run from an unrelated directory."""
    index_path, sample = _make_index(tmp_path)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    resolved = resolve_dpcm_sample_path("Kick.dmc", index_path)
    assert resolved is not None
    assert resolved.resolve() == sample.resolve()


def test_missing_sample_returns_none(tmp_path):
    index_path, _ = _make_index(tmp_path)
    assert resolve_dpcm_sample_path("DoesNotExist.dmc", index_path) is None


def test_absolute_path_is_honored(tmp_path):
    index_path, sample = _make_index(tmp_path)
    resolved = resolve_dpcm_sample_path(str(sample.resolve()), index_path)
    assert resolved is not None
    assert resolved.resolve() == sample.resolve()


def test_shipped_index_resolves_against_repo():
    """The real shipped dpcm_index.json must fully resolve against dmc/."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_path = os.path.join(repo_root, "dpcm_index.json")
    if not os.path.exists(index_path):
        import pytest
        pytest.skip("dpcm_index.json not present")
    with open(index_path) as f:
        index = json.load(f)
    unresolved = [
        s["filename"]
        for s in index.values()
        if resolve_dpcm_sample_path(s["filename"], index_path) is None
    ]
    assert not unresolved, f"{len(unresolved)} index entries did not resolve, e.g. {unresolved[:3]}"


def test_shipped_index_covers_most_default_drum_roles():
    """Regression (#201/D-15): DEFAULT_MIDI_DRUM_MAPPING defines 40 distinct GM
    percussion role names, but the shipped dpcm_index.json only backed 8 of
    them (kick, snare, clap, ride, cowbell, cabasa, maracas, claves) -- the
    other 32 (toms, hi-hats, crash, china, congas, timbales, agogos, ...) fell
    through to the noise fallback purely for lack of a matching catalog entry,
    not a code bug. 18 more role names were aliased to existing, resolvable
    catalog entries whose filenames clearly matched (e.g. GH-HiTom -> tom_high,
    agogohi/agogolo -> agogo_hi/agogo_lo), each under a fresh id so as not to
    collide with the id the aliased entry already carries. The remaining 14
    (side_stick, tambourine, splash, vibraslap, whistle/guiro short-vs-long,
    woodblock hi/lo, cuica mute/open, triangle mute/open) have no
    unambiguous match in the catalog and are left on the noise fallback
    rather than guessed."""
    from dpcm_sampler.drum_engine import DEFAULT_MIDI_DRUM_MAPPING

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index_path = os.path.join(repo_root, "dpcm_index.json")
    if not os.path.exists(index_path):
        import pytest
        pytest.skip("dpcm_index.json not present")
    with open(index_path) as f:
        index = json.load(f)

    roles = set(DEFAULT_MIDI_DRUM_MAPPING.values())
    present = {r for r in roles if r in index}
    assert len(present) >= 26, (
        f"expected at least 26 of {len(roles)} role names present, got "
        f"{len(present)}: {sorted(present)}"
    )

    newly_added = {
        'tom_high', 'tom_mid', 'tom_low', 'hihat_closed', 'hihat_open',
        'hihat_pedal', 'crash', 'china', 'ride_bell', 'bongo_hi', 'bongo_lo',
        'conga_mute', 'conga_open', 'conga_lo', 'timbale_hi', 'timbale_lo',
        'agogo_hi', 'agogo_lo',
    }
    assert newly_added <= present
    for role in newly_added:
        assert resolve_dpcm_sample_path(index[role]['filename'], index_path) is not None, (
            f"{role} -> {index[role]['filename']} does not resolve to a real file"
        )
    # Each alias must carry its own id, not collide with the entry it aliases
    # (a shared id would corrupt the packer's positional lookup tables).
    all_ids = [v['id'] for v in index.values()]
    assert len(all_ids) == len(set(all_ids)), "dpcm_index.json has duplicate ids"


def test_generate_dpcm_index_walks_directory_with_sequential_ids(tmp_path):
    """Regression (#338/REG-19): the os.walk-based builder had no coverage --
    one JSON entry per .dmc file (recursively, non-.dmc files skipped), with
    sequential ids and a filename relative to the scanned root."""
    dmc_dir = tmp_path / "samples"
    dmc_dir.mkdir()
    (dmc_dir / "Kick.dmc").write_bytes(b"\x00" * 8)
    (dmc_dir / "Snare.dmc").write_bytes(b"\x00" * 8)
    (dmc_dir / "notes.txt").write_text("not a sample")  # non-.dmc, must be skipped
    sub = dmc_dir / "sub"
    sub.mkdir()
    (sub / "Tom.dmc").write_bytes(b"\x00" * 8)

    output_json = tmp_path / "out.json"
    generate_dpcm_index(str(dmc_dir), str(output_json))

    index = json.loads(output_json.read_text())
    assert set(index.keys()) == {"Kick", "Snare", "Tom"}
    ids = sorted(v["id"] for v in index.values())
    assert ids == [0, 1, 2]  # sequential, one per file
    assert index["Tom"]["filename"] == "sub/Tom.dmc"  # relative path, forward slashes
    assert index["Kick"]["filename"] == "Kick.dmc"


def test_load_dpcm_index_into_packer_skips_missing_sample(tmp_path):
    """Regression (#338/REG-19): a genuinely-missing sample must be skipped
    with a (loaded, skipped) count, not silently swallowed or raised -- this
    is the live packer path (main.py) that would otherwise drop a drum with
    no trace."""
    index_path = tmp_path / "dpcm_index.json"
    dpcm_index = {"Ghost": {"id": 0, "filename": "DoesNotExist.dmc"}}
    index_path.write_text(json.dumps(dpcm_index))

    packer = Mock()
    loaded, skipped = load_dpcm_index_into_packer(packer, dpcm_index, str(index_path))

    assert (loaded, skipped) == (0, 1)
    packer.add_sample.assert_not_called()


def test_load_dpcm_index_into_packer_loads_present_sample(tmp_path):
    """Sibling of the skip-branch test: a real sample loads normally, so
    (loaded, skipped) exercises both sides of the branch in one pack run."""
    dmc_dir = tmp_path / DPCM_ROOT_DIRNAME
    dmc_dir.mkdir()
    (dmc_dir / "Kick.dmc").write_bytes(b"\x00" * 16)
    index_path = tmp_path / "dpcm_index.json"
    dpcm_index = {
        "Kick": {"id": 0, "filename": "Kick.dmc"},
        "Ghost": {"id": 1, "filename": "DoesNotExist.dmc"},
    }
    index_path.write_text(json.dumps(dpcm_index))

    packer = Mock()
    loaded, skipped = load_dpcm_index_into_packer(packer, dpcm_index, str(index_path))

    assert (loaded, skipped) == (1, 1)
    packer.add_sample.assert_called_once()
