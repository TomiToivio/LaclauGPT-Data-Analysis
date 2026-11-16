"""Read-only, privacy-safe audit of AI26 canonical analysis output (issue #435, item 3).

The question this answers is not "did the stage run" but "is what it stored internally consistent":
are identities unique, does every quotation actually occur at the offsets it claims, do relations
point at evidence that exists, is a record marked complete while carrying no findings, and does a
plugin's current result agree with the latest run recorded for it.

**Privacy.** The report contains counts, check names and status values. It never prints a source URL,
a quotation, a transcript or a researcher note — by default not even a record identifier. Row-level
detail stays wherever the operator points it; publishing the summary is safe by construction.

Usage:

    python tools/ai26_output_audit.py --input export.jsonl
    python tools/ai26_output_audit.py --input records_dir --json audit.json
    python tools/ai26_output_audit.py --input export.jsonl --fail-on orphan_relation

Exit status is 0 when no check fails, 1 when a check specified by ``--fail-on`` fails (or, without
``--fail-on``, when any finding at all is present), 2 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

CHECKS = (
    "empty_identity",
    "duplicate_identity",
    "evidence_without_id",
    "quote_without_offsets",
    "offset_mismatch",
    "quote_not_in_text",
    "orphan_relation_evidence",
    "relation_without_evidence",
    "complete_without_findings",
    "complete_without_model_runs",
    "model_run_without_provenance",
    "plugin_result_disagrees_with_latest_run",
)

#: Analysis surface families a complete record is expected to have produced something in.
FINDING_FIELDS = (
    # Include the actual AI26 Phase 1 interpretive categories. An analysis with only
    # formations or imaginaries is not an empty analysis (issue #444).
    "formations", "signifiers", "nodal_points", "floating_signifiers",
    "empty_signifier_candidates", "discourses", "imaginaries",
    "entities", "themes", "topics", "relations", "equivalence_chains", "difference_chains",
    "antagonisms", "actor_entity_relations", "us", "them",
    "frontier", "affects", "sentiments", "stances", "classifications",
    "representations", "embeddings",
)

COMPLETE_STATUSES = {"complete", "completed", "done", "ok"}

#: Keys a model run must carry for the result to be attributable to a configuration.
PROVENANCE_KEYS = ("prompt_version", "config_revision")


def _load_records(inputs: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for path in inputs:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    yield payload


def _collect_inputs(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(path.glob("*.jsonl"))
    return [path]


def _analysis(record: Mapping[str, Any]) -> Mapping[str, Any]:
    analysis = record.get("analysis")
    return analysis if isinstance(analysis, Mapping) else {}


def _items(section: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = section.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _text(record: Mapping[str, Any]) -> str:
    content = record.get("content")
    return str(content.get("text") or "") if isinstance(content, Mapping) else ""


def audit_record(record: Mapping[str, Any]) -> dict[str, list[str]]:
    """Findings for one record, keyed by check name.

    Each entry carries a short detail string that names *where* the problem is (a field, an index)
    and never the content itself.
    """
    findings: dict[str, list[str]] = defaultdict(list)
    analysis = _analysis(record)

    evidence = _items(record, "evidence")
    evidence_ids = {str(item.get("evidence_id") or "") for item in evidence}
    evidence_ids.discard("")

    for index, item in enumerate(evidence):
        if not str(item.get("evidence_id") or "").strip():
            findings["evidence_without_id"].append(f"evidence[{index}]")
            continue
        quote = item.get("quote")
        start = item.get("start_offset")
        end = item.get("end_offset")
        if quote and (start is None or end is None):
            findings["quote_without_offsets"].append(str(item.get("evidence_id")))
            continue
        if quote and isinstance(start, int) and isinstance(end, int):
            text = _text(record)
            if not text:
                continue
            window = text[start:end]
            if window != str(quote):
                findings["offset_mismatch"].append(f"evidence[{index}] {start}:{end}")
                if str(quote) not in text:
                    findings["quote_not_in_text"].append(f"evidence[{index}]")

    relation_keys = ("relations", "antagonisms", "actor_entity_relations",
                     "equivalence_chains", "difference_chains")
    for key in relation_keys:
        for position, relation in enumerate(_items(analysis, key)):
            references = relation.get("evidence_ids")
            references = [str(value) for value in references] if isinstance(references, list) else []
            if not references:
                findings["relation_without_evidence"].append(f"{key}[{position}]")
                continue
            missing = [value for value in references if value not in evidence_ids]
            if missing:
                findings["orphan_relation_evidence"].append(
                    f"{key}[{position}] ({len(missing)} of {len(references)} reference unknown evidence)")

    status = str(analysis.get("status") or "").lower()
    if status in COMPLETE_STATUSES:
        if not any(_items(analysis, key) for key in FINDING_FIELDS):
            findings["complete_without_findings"].append(f"status={status}")
        runs = _items(analysis, "model_runs")
        if not runs:
            findings["complete_without_model_runs"].append(f"status={status}")
        else:
            missing = sum(1 for run in runs if not all(run.get(key) for key in PROVENANCE_KEYS))
            if missing:
                findings["model_run_without_provenance"].append(
                    f"{missing} of {len(runs)} model runs lack {', '.join(PROVENANCE_KEYS)}")

    stale = plugin_disagreement(record)
    if stale:
        findings["plugin_result_disagrees_with_latest_run"].append(stale)
    return dict(findings)


def plugin_disagreement(record: Mapping[str, Any]) -> str:
    """Does a plugin's current result match the most recent run recorded for it?

    A retry that returned nothing must not leave the earlier statements visible as the current
    result (upstream #410's rule). This is the read-only detector for that condition.
    """
    analysis = _analysis(record)
    results = analysis.get("plugin_results")
    intermediate = record.get("intermediate")
    stages = intermediate.get("stage_outputs") if isinstance(intermediate, Mapping) else None
    if not isinstance(results, Mapping) or not isinstance(stages, Mapping):
        return ""
    for name, current in results.items():
        history = stages.get(name)
        if not isinstance(history, list) or not history:
            continue
        latest = history[-1]
        if not isinstance(latest, Mapping) or not isinstance(current, Mapping):
            continue
        current_proposal = current.get("proposal") if isinstance(current.get("proposal"), Mapping) else current
        latest_proposal = latest.get("proposal") if isinstance(latest.get("proposal"), Mapping) else latest
        current_rows = current_proposal.get("statements") if isinstance(current_proposal, Mapping) else None
        latest_rows = latest_proposal.get("statements") if isinstance(latest_proposal, Mapping) else None
        if isinstance(current_rows, list) and isinstance(latest_rows, list):
            if len(current_rows) != len(latest_rows):
                return f"{name}: current {len(current_rows)} rows vs latest run {len(latest_rows)}"
    return ""


def audit_stream(records: Sequence[Mapping[str, Any]], *, sample_limit: int = 5) -> dict[str, Any]:
    """Aggregate findings over a record stream, including identity uniqueness.

    No identifier leaves this function: samples name fields and indices, never values.
    """
    statuses: Counter = Counter()
    per_check = {name: 0 for name in CHECKS}
    samples: dict[str, list[str]] = defaultdict(list)
    records_with_findings = 0
    identities: Counter = Counter()
    empty_identities = 0

    for record in records:
        status = str(_analysis(record).get("status") or "(none)")
        statuses[status] += 1
        identity = str(record.get("source_url") or "").strip()
        if identity:
            identities[identity] += 1
        else:
            empty_identities += 1

        findings = audit_record(record)
        if findings:
            records_with_findings += 1
        for name, details in findings.items():
            per_check[name] = per_check.get(name, 0) + len(details)
            if len(samples[name]) < sample_limit:
                samples[name].extend(details[: sample_limit - len(samples[name])])

    per_check["empty_identity"] = empty_identities
    duplicates = sum(count - 1 for count in identities.values() if count > 1)
    per_check["duplicate_identity"] = duplicates
    report = {
        "contract": "ai26-output-audit/1",
        "records": len(records),
        "records_with_findings": records_with_findings,
        "unique_identities": len(identities),
        "analysis_status": dict(sorted(statuses.items())),
        "checks": per_check,
        "samples": {name: values for name, values in sorted(samples.items()) if values},
    }
    report["failed_checks"] = sorted(name for name, count in per_check.items() if count)
    return report


def _summary_lines(report: Mapping[str, Any]) -> list[str]:
    lines = [
        "AI26 canonical output audit",
        f"  records: {report['records']}  with findings: {report['records_with_findings']}"
        f"  unique identities: {report.get('unique_identities', 0)}",
        "  analysis status: " + ", ".join(
            f"{name}={count}" for name, count in report.get("analysis_status", {}).items()),
        "",
    ]
    for name in CHECKS:
        count = report["checks"].get(name, 0)
        marker = "FAIL" if count else "ok  "
        lines.append(f"  {marker} {name}: {count}")
        for sample in report.get("samples", {}).get(name, []):
            lines.append(f"        - {sample}")
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, type=Path,
                        help="JSONL file of canonical records, or a directory of .jsonl files")
    parser.add_argument("--json", type=Path, default=None, help="write the report here")
    parser.add_argument("--sample-limit", type=int, default=5,
                        help="how many field-level examples to show per check (no content)")
    parser.add_argument("--fail-on", action="append", default=[],
                        help="exit 1 only when this check has findings (repeatable)")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"input not found: {args.input}", file=sys.stderr)
        return 2
    records = list(_load_records(_collect_inputs(args.input)))
    if not records:
        print("no records parsed from the input", file=sys.stderr)
        return 2

    report = audit_stream(records, sample_limit=args.sample_limit)
    print("\n".join(_summary_lines(report)))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    watched = args.fail_on or list(report["failed_checks"])
    failing = [name for name in watched if report["checks"].get(name, 0)]
    if failing:
        print("\nfailing checks: " + ", ".join(failing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
