#!/usr/bin/env python3
"""Offline AI26 research-record contract check against sibling repositories.

Non-destructive: reads public JSON schemas only; needs no credentials or services.

Exit 0 means the version Data Analysis **emits** is accepted by every sibling's schema and the
three top-level required-field sets agree. It does not mean that Mongo routing, field semantics or
an end-to-end deployment was tested.

Why the version is read as a *set* of accepted versions
-------------------------------------------------------

A schema may pin one version (``const``) or declare the versions it accepts (``enum``). Data
Visualization does the latter on purpose: it accepts both 1.1.0 and 1.2.0 while Data Analysis emits
1.2.0 and Data Collection still declares 1.1.0. Reading only ``const`` made this tool die with
``cannot read/parse schema: 'const'`` on the live Laskin deployment, which named neither the
repository nor the disagreement — the same representation-mismatch class as upstream #298. It now
reports, per repository, what is emitted, what is accepted, and which repository is wrong.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA_RELATIVE = Path("schemas") / "research-record.schema.json"


class SchemaError(RuntimeError):
    """A schema that cannot be read or does not declare a usable version."""


def _version_block(schema: dict, *, name: str) -> dict:
    try:
        block = schema["properties"]["schema_version"]
    except (KeyError, TypeError) as exc:
        raise SchemaError(f"{name}: no properties.schema_version in {SCHEMA_RELATIVE}") from exc
    if not isinstance(block, dict):
        raise SchemaError(f"{name}: properties.schema_version is not an object")
    return block


def accepted_versions(schema: dict, *, name: str) -> tuple[set[str], str]:
    """The versions this schema accepts, and which of ``const``/``enum`` declared them."""
    block = _version_block(schema, name=name)
    if "const" in block:
        return {str(block["const"])}, "const"
    if "enum" in block:
        values = block["enum"]
        if not isinstance(values, list) or not values:
            raise SchemaError(f"{name}: properties.schema_version.enum is empty or not a list")
        return {str(value) for value in values}, "enum"
    raise SchemaError(
        f"{name}: properties.schema_version declares neither 'const' nor 'enum'"
    )


def contract(root: Path) -> dict:
    """Read one repository's record contract: the accepted versions and the required fields."""
    path = Path(root) / SCHEMA_RELATIVE
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SchemaError(f"{path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    name = Path(root).name
    versions, declared_by = accepted_versions(schema, name=name)
    required = schema.get("required")
    if not isinstance(required, list) or not required:
        raise SchemaError(f"{name}: the schema declares no top-level 'required' list")
    return {
        "name": name,
        "path": path,
        "versions": versions,
        "declared_by": declared_by,
        "required": frozenset(str(field) for field in required),
    }


def check(analysis: Path, collection: Path, visualization: Path) -> int:
    roots = {"analysis": analysis, "collection": collection, "visualization": visualization}
    try:
        results = {role: contract(root) for role, root in roots.items()}
    except SchemaError as error:
        print(f"FAIL: cannot read a schema: {error}", file=sys.stderr)
        return 2

    emitted = results["analysis"]
    if len(emitted["versions"]) != 1:
        print(
            "FAIL: Data Analysis must emit exactly one schema_version, but accepts "
            f"{sorted(emitted['versions'])}",
            file=sys.stderr,
        )
        return 2
    emitting = next(iter(emitted["versions"]))

    for role in ("analysis", "collection", "visualization"):
        item = results[role]
        print(
            f"{role}: {item['name']} schema_version "
            f"{sorted(item['versions'])} (declared by {item['declared_by']}), "
            f"required={','.join(sorted(item['required']))}"
        )
    print(f"emitted by Data Analysis: {emitting}")

    failures: list[str] = []
    for role in ("collection", "visualization"):
        item = results[role]
        if emitting not in item["versions"]:
            failures.append(
                f"{item['name']} accepts {sorted(item['versions'])} but Data Analysis emits "
                f"{emitting}: the sibling schema must accept the emitted version"
            )
    reference_fields = emitted["required"]
    for role in ("collection", "visualization"):
        item = results[role]
        if item["required"] != reference_fields:
            missing = sorted(reference_fields - item["required"])
            extra = sorted(item["required"] - reference_fields)
            failures.append(
                f"{item['name']} top-level required fields differ from Data Analysis: "
                f"missing={missing} extra={extra}"
            )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("OK: every sibling accepts the emitted schema_version and declares the same required fields")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--visualization", type=Path, required=True)
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)
    if args.json:
        # The human-readable report goes to stdout; --json is for a caller that wants the map.
        roots = {
            "analysis": args.analysis,
            "collection": args.collection,
            "visualization": args.visualization,
        }
        try:
            payload = {
                role: {
                    **{k: v for k, v in contract(root).items() if k != "required"},
                    "versions": sorted(contract(root)["versions"]),
                    "required": sorted(contract(root)["required"]),
                }
                for role, root in roots.items()
            }
        except SchemaError as error:
            print(json.dumps({"ok": False, "error": str(error)}))
            return 2
        status = check(args.analysis, args.collection, args.visualization)
        print(json.dumps({"ok": status == 0, "repositories": payload, "exit": status}, default=str))
        return status
    return check(args.analysis, args.collection, args.visualization)


if __name__ == "__main__":
    raise SystemExit(main())
