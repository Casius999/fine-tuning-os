# tests/test_envelope.py
import dataclasses

import pytest

from fine_tuning_os.envelope import fail, ok


def test_ok_builds_success_result():
    r = ok({"x": 1}, executed=True)
    assert r.success is True
    assert r.data == {"x": 1}
    assert r.error is None
    assert r.meta == {"executed": True}


def test_fail_builds_error_result():
    r = fail("boom", dry_run=True)
    assert r.success is False
    assert r.data is None
    assert r.error == "boom"
    assert r.meta == {"dry_run": True}


def test_to_dict_roundtrips_all_fields():
    r = ok({"a": 2}, command="docker build .")
    assert r.to_dict() == {
        "success": True,
        "data": {"a": 2},
        "error": None,
        "meta": {"command": "docker build ."},
    }


def test_result_is_frozen():
    r = ok()
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.success = False  # type: ignore[misc]
