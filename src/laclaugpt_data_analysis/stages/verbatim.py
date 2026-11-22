"""Verify AI26 textual citations and allow one evidence-only repair per stage."""
from __future__ import annotations

import json

from pydantic import BaseModel

from ..llm.base import ChatRequest
from ..llm.structured_output import build_structured_prompt, parse_structured
from .evidence import locate_quote
from .proposals import DiscourseProposal

VERSION = "ai26-verbatim-v1"


class Corrections(BaseModel):
    replacements: dict[str, str]


def contiguous(source, quote):
    start, end = locate_quote(source, quote)
    if start is None:
        return ""
    span = source[start:end]
    if " ".join(span.split()).casefold() == " ".join(quote.split()).casefold():
        return span
    return ""


def verify_proposal(record, proposal, *, provider, model, user_prompt, allow_cloud_fallback):
    source = record.content.text or ""
    targets = []
    if isinstance(proposal, DiscourseProposal):
        for field in type(proposal).model_fields:
            items = getattr(proposal, field)
            if isinstance(items, list):
                for index, item in enumerate(items):
                    if hasattr(item, "evidence"):
                        targets.append((f"{field}.{index}", item, "evidence"))
    else:
        targets.extend((f"evidence.{i}", item, "exact_text") for i, item in enumerate(proposal.evidence)
                       if item.exact_text)
        targets.extend((f"event_candidates.{i}", item, "evidence")
                       for i, item in enumerate(proposal.event_candidates))

    pending = {}
    verified = {}
    for path, item, field in targets:
        values = [item.exact_text] if field == "exact_text" else item.evidence
        verified[path] = []
        for index, value in enumerate(values):
            span = contiguous(source, value)
            if span:
                verified[path].append(span)
            else:
                pending[f"{path}.{index}"] = value

    report = {"version": VERSION, "attempts": 0, "unlocatable": len(pending),
              "corrected": 0, "abstentions": []}
    replacements = {}
    if pending and source.strip():
        batch = {key: value[:300] for key, value in list(pending.items())[:24]}
        prompt = user_prompt + "\nRepair only these citations. Copy a contiguous source span for each key or return an empty string.\n" + json.dumps(batch, ensure_ascii=False)
        report["attempts"] = 1
        try:
            response = provider.chat(ChatRequest(
                model=model, system="Correct source quotations only.",
                user=build_structured_prompt(prompt, Corrections),
                options={"temperature": 0, "num_predict": 2048},
                schema=Corrections.model_json_schema(), allow_cloud_fallback=allow_cloud_fallback,
            ))
            report["model_run"] = response.provenance.to_dict()
            if not response.truncated:
                replacements = parse_structured(response.content, Corrections).replacements
        except Exception as exc:
            report["correction_error"] = type(exc).__name__
        replacements = {key: value for key, value in replacements.items() if key in batch}
    for key in pending:
        path = key.rsplit(".", 1)[0]
        span = contiguous(source, replacements.get(key, ""))
        if span:
            verified[path].append(span)
            report["corrected"] += 1
        else:
            report["abstentions"].append({"citation": key, "reason": "no verbatim evidence found"})
    for path, item, field in targets:
        if field == "exact_text":
            item.exact_text = next(iter(verified[path]), "")
        else:
            item.evidence = verified[path]
    if report["abstentions"]:
        notes = proposal.abstentions if isinstance(proposal, DiscourseProposal) else proposal.limitations
        notes.extend(f"{entry['citation']}: no verbatim evidence found" for entry in report["abstentions"])
    return report
