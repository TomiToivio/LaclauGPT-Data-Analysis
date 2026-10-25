"""Behaviour of the cross-repository contract check (issue #382).

The check is the only automated statement that the three AI26 repositories agree on the record
contract, and it sits *outside* the test suite by design (it needs sibling checkouts, not a
fixture). These tests build three throwaway repositories instead, so the tool's own contract is
pinned: an emitted version every sibling must accept, a report that names the repository that is
wrong, and an exit code that separates "disagreement" from "unreadable input".
"""
from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_ai26_contracts as tool  # noqa: E402 - the tool lives outside the package

REQUIRED = ["schema_version", "source", "content"]


def _repo(root: Path, *, version=None, versions=None, required=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    block: dict = {"type": "string"}
    if version is not None:
        block["const"] = version
    if versions is not None:
        block["enum"] = versions
    schema = {
        "type": "object",
        "properties": {"schema_version": block},
        "required": list(REQUIRED if required is None else required),
    }
    path = root / "schemas" / "research-record.schema.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(schema), encoding="utf-8")
    return root


def _run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = tool.main(list(args))
    return code, out.getvalue(), err.getvalue()


def test_agreement_is_reported_as_ok(tmp_path: Path) -> None:
    analysis = _repo(tmp_path / "analysis", version="1.2.0")
    collection = _repo(tmp_path / "collection", version="1.2.0")
    visualization = _repo(tmp_path / "visualization", versions=["1.1.0", "1.2.0"])

    code, out, err = _run("--analysis", str(analysis), "--collection", str(collection),
                          "--visualization", str(visualization))

    assert code == 0, err
    assert "emitted by Data Analysis: 1.2.0" in out
    assert "OK:" in out


def test_a_sibling_that_does_not_accept_the_emitted_version_is_named(tmp_path: Path) -> None:
    analysis = _repo(tmp_path / "analysis", version="1.2.0")
    collection = _repo(tmp_path / "collection", version="1.1.0")
    visualization = _repo(tmp_path / "visualization", versions=["1.1.0", "1.2.0"])

    code, out, err = _run("--analysis", str(analysis), "--collection", str(collection),
                          "--visualization", str(visualization))

    assert code == 1, err
    assert "collection" in err and "1.1.0" in err and "1.2.0" in err
    assert "visualization" not in err.split("FAIL:", 1)[1].split("\n", 1)[0]


def test_a_sibling_with_other_required_fields_is_named_with_the_difference(tmp_path: Path) -> None:
    analysis = _repo(tmp_path / "analysis", version="1.2.0")
    collection = _repo(tmp_path / "collection", version="1.2.0", required=[*REQUIRED, "raw_capture"])
    visualization = _repo(tmp_path / "visualization", version="1.2.0")

    code, _, err = _run("--analysis", str(analysis), "--collection", str(collection),
                        "--visualization", str(visualization))

    assert code == 1
    assert "missing=[]" in err and "extra=['raw_capture']" in err


def test_an_enum_schema_is_read_rather_than_crashing(tmp_path: Path) -> None:
    """Data Visualization declares an enum; a `const`-only reader died on it on Laskin."""
    analysis = _repo(tmp_path / "analysis", version="1.2.0")
    collection = _repo(tmp_path / "collection", version="1.2.0")
    visualization = _repo(tmp_path / "visualization", versions=["1.1.0", "1.2.0"])

    code, out, _ = _run("--analysis", str(analysis), "--collection", str(collection),
                        "--visualization", str(visualization))

    assert code == 0
    assert "declared by enum" in out


def test_an_unreadable_schema_exits_two_and_names_the_file(tmp_path: Path) -> None:
    analysis = _repo(tmp_path / "analysis", version="1.2.0")
    collection = tmp_path / "collection"
    (collection / "schemas").mkdir(parents=True)
    (collection / "schemas" / "research-record.schema.json").write_text("{not json", encoding="utf-8")
    visualization = _repo(tmp_path / "visualization", version="1.2.0")

    code, _, err = _run("--analysis", str(analysis), "--collection", str(collection),
                        "--visualization", str(visualization))

    assert code == 2
    assert "research-record.schema.json" in err


def test_a_version_block_without_const_or_enum_exits_two(tmp_path: Path) -> None:
    analysis = _repo(tmp_path / "analysis", version="1.2.0")
    collection = _repo(tmp_path / "collection")  # no const, no enum
    visualization = _repo(tmp_path / "visualization", version="1.2.0")

    code, _, err = _run("--analysis", str(analysis), "--collection", str(collection),
                        "--visualization", str(visualization))

    assert code == 2
    assert "neither 'const' nor 'enum'" in err


def test_analysis_must_emit_exactly_one_version(tmp_path: Path) -> None:
    analysis = _repo(tmp_path / "analysis", versions=["1.1.0", "1.2.0"])
    collection = _repo(tmp_path / "collection", version="1.2.0")
    visualization = _repo(tmp_path / "visualization", version="1.2.0")

    code, _, err = _run("--analysis", str(analysis), "--collection", str(collection),
                        "--visualization", str(visualization))

    assert code == 2
    assert "must emit exactly one" in err


@pytest.mark.parametrize("version", ["1.2.0"])
def test_the_real_repository_emits_one_version(tmp_path: Path, version: str) -> None:
    """The analysis schema in this checkout really does pin a single emitted version."""
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "research-record.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["properties"]["schema_version"]["const"] == version
