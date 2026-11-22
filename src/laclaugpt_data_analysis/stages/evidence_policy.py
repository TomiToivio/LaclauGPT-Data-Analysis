"""#458: a stored quote is a verbatim source span, or an explicit abstention.

D6 in ``docs/AI26_OPEN_DECISIONS.md`` approved option (a): require verbatim spans,
attempt **one** evidence-specific correction when :func:`locate_quote` fails, then
abstain. The measured problem was that 35.2 % of sampled citations are paraphrase and
43.6 % cannot be located in the source at all -- and nothing in the pipeline asked the
model for anything else.

What this module deliberately does not do:

* it never rewrites a quote, and never substitutes a paraphrase;
* it never drops a coded object because its evidence failed -- the object keeps its
  analysis and its evidence status;
* it never treats an abstention marker as a citation, so abstentions cannot inflate
  ``evidence_count``;
* it keeps ``exact`` on every stored item, so the before/after comparison in the issue
  is measured by the same numbers.

The re-prompt is injected as a callable rather than called from here, so the bounded
policy can be tested without a model and wired to whichever stage owns the LLM handle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .evidence import VERBATIM_ABSTENTION, evidence_status, is_abstention, locate_quote

MAX_CORRECTIONS = 1


@dataclass
class EvidenceVerification:
    """Outcome of applying the verbatim policy to one coded object's quotes."""

    accepted: list[str] = field(default_factory=list)
    unlocatable: list[str] = field(default_factory=list)
    abstained: bool = False
    corrections_attempted: int = 0
    corrections_resolved: int = 0
    corrections_failed: int = 0

    @property
    def status(self) -> str:
        """Machine-readable evidence status for the coded object."""
        if self.accepted:
            return "verified"
        return "abstained_unlocatable" if self.abstained or self.unlocatable else "no_evidence"

    def telemetry(self) -> dict[str, int | bool | str]:
        """Attributable per-run provenance: what was attempted and what it achieved."""
        return {
            "status": self.status,
            "accepted": len(self.accepted),
            "unlocatable": len(self.unlocatable),
            "abstained": self.abstained,
            "corrections_attempted": self.corrections_attempted,
            "corrections_resolved": self.corrections_resolved,
            "corrections_failed": self.corrections_failed,
        }


def verify_quotes(source_text: str, quotes: list[str]) -> tuple[list[str], list[str]]:
    """Split quotes into ``(locatable, unlocatable)``; abstentions go to neither."""
    locatable: list[str] = []
    unlocatable: list[str] = []
    for quote in quotes:
        text = quote.strip()
        if not text or is_abstention(text):
            continue
        if locate_quote(source_text, text)[0] is None:
            unlocatable.append(text)
        else:
            locatable.append(text)
    return locatable, unlocatable


def apply_verbatim_policy(
    source_text: str,
    quotes: list[str],
    *,
    reprompt: Callable[[list[str]], list[str] | None] | None = None,
) -> EvidenceVerification:
    """Verify quotes, allow at most one correction, then abstain.

    ``reprompt`` receives the quotes that failed to locate and returns replacements
    (or ``None`` when the correction itself failed). It is called **at most once**:
    the issue is explicit that recursive retries are not the point, and a model that
    needed three attempts to quote its own source is telling you something.
    """
    accepted, unlocatable = verify_quotes(source_text, quotes)
    outcome = EvidenceVerification(accepted=accepted, unlocatable=unlocatable)
    if not unlocatable:
        return outcome
    if reprompt is None or MAX_CORRECTIONS == 0:
        return outcome

    outcome.corrections_attempted = 1
    replacements = reprompt(unlocatable) or []
    fixed, still_bad = verify_quotes(source_text, replacements)
    outcome.accepted.extend(q for q in fixed if q not in outcome.accepted)
    outcome.corrections_resolved = len(fixed)
    outcome.corrections_failed = len(still_bad)
    outcome.unlocatable = still_bad
    # Nothing verifiable and the model did not abstain: record the abstention here, so
    # the caller has one machine-readable state rather than an empty list.
    outcome.abstained = not outcome.accepted and not still_bad
    return outcome

__all__ = [
    "VERBATIM_ABSTENTION",
    "EvidenceVerification",
    "MAX_CORRECTIONS",
    "apply_verbatim_policy",
    "evidence_status",
    "is_abstention",
    "verify_quotes",
]
