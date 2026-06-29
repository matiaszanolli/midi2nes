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

from dpcm_sampler.generate_dpcm_index import (
    resolve_dpcm_sample_path,
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
