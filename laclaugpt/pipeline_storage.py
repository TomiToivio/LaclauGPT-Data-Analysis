"""Incoming/outgoing database boundary for the human-written pipeline.

Agent-owned support code around the seven human-owned (locked) step modules
(issue #315
step 3). The issue asks for "the auxiliary files for incoming and outgoing
databases"; this is the concrete local implementation of the protocols in
``pipeline_io.py``. The steps never touch it directly, and it never touches a
step: it decides which records a step is *offered* and where a result is written.

Two design notes that matter later:

* The eligibility rule lives in one place. A step should not decide for itself
  whether it has already run, because then the run order stops being auditable.
* A ``skipped`` or ``abstained`` step is a result, not an error. Only ``failed``
  makes a record retryable, and a failure blocks the *later* steps for that
  record so a network layer can never be built on a summary that failed.

The database is runtime data and belongs under ``data/`` (AGENTS.md), which is
git-ignored. Nothing here creates operational files outside that tree.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pipeline_context import STEP_NAMES, StepOutcome, StepStatus

# One table per side. The incoming side is what a collector or an adapter filled;
# the outgoing side is one namespaced block per step per record, which is what
# makes the run order readable back.
SCHEMA = """
CREATE TABLE IF NOT EXISTS incoming_records (
    source_url TEXT PRIMARY KEY,
    project    TEXT NOT NULL,
    record     TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outgoing_steps (
    source_url TEXT NOT NULL,
    step       TEXT NOT NULL,
    status     TEXT NOT NULL,
    output     TEXT,
    error      TEXT,
    notes      TEXT,
    model      TEXT,
    prompt     TEXT,
    review_status TEXT NOT NULL DEFAULT 'provisional',
    at         TEXT NOT NULL,
    PRIMARY KEY (source_url, step)
);

CREATE TABLE IF NOT EXISTS outgoing_bundles (
    source_url TEXT PRIMARY KEY,
    project    TEXT NOT NULL,
    bundle     TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS outgoing_steps_by_step ON outgoing_steps (step, status);
"""


def _connect(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) a pipeline database under the runtime data tree."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


class SQLiteIncoming:
    """Read records that still need analysis.

    Implements the ``IncomingRecords`` protocol in ``pipeline_io.py``.

    Eligibility is decided by the *outgoing* database (a step's recorded status),
    so the reader is given its path rather than guessing: by default it is the
    ``pipeline_outgoing.sqlite3`` sitting next to the incoming database.
    """

    def __init__(self, path: Path | str, outgoing_path: Path | str | None = None) -> None:
        self.path = Path(path)
        self.outgoing_path = (
            Path(outgoing_path) if outgoing_path is not None else self.path.with_name(
                "pipeline_outgoing.sqlite3"
            )
        )
        self.connection = _connect(self.path)

    def add(self, record: Any) -> None:
        """Store one record (a ``HumanPipelineRecord`` or an equivalent dict)."""
        if hasattr(record, "model_dump"):
            payload = record.model_dump(mode="json")
            project = payload.get("project", "")
            source_url = payload["source_url"]
        else:
            payload = dict(record)
            source_url = payload["source_url"]
            project = payload.get("project", "")
        self.connection.execute(
            "INSERT INTO incoming_records (source_url, project, record) VALUES (?, ?, ?) "
            "ON CONFLICT(source_url) DO UPDATE SET record=excluded.record, project=excluded.project",
            (source_url, project, json.dumps(payload)),
        )
        self.connection.commit()

    def document(self, source_url: str) -> dict[str, Any]:
        """Read one record back as a plain dict."""
        row = self.connection.execute(
            "SELECT record FROM incoming_records WHERE source_url = ?", (source_url,)
        ).fetchone()
        return json.loads(row["record"]) if row else {}

    def pending(
        self, project: str, limit: int | None = None, *, retry_errors: bool = False
    ) -> Iterable[Any]:
        """Yield records of ``project`` that still need a step to run."""
        from pipeline_models import HumanPipelineRecord

        query = "SELECT record FROM incoming_records WHERE project = ? ORDER BY source_url"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        for row in self.connection.execute(query, (project,)):
            document = json.loads(row["record"])
            if self.needs_work(document, project, retry_errors=retry_errors):
                yield HumanPipelineRecord.model_validate(document)

    def needs_work(
        self, document: dict[str, Any], project: str, *, retry_errors: bool = False
    ) -> bool:
        """Whether any step of this document is still eligible.

        Uses the outgoing database's rule so ``--limit`` counts records the run
        will actually process rather than every stored row.
        """
        outgoing = SQLiteOutgoing(self.outgoing_path)
        try:
            return any(
                outgoing.is_eligible(
                    document, step, project=project, retry_errors=retry_errors
                )
                for step in STEP_NAMES
            )
        finally:
            outgoing.close()

    def close(self) -> None:
        self.connection.close()


class SQLiteOutgoing:
    """Write step outcomes and finished bundles; decide what is still eligible.

    Implements the ``OutgoingResults`` protocol in ``pipeline_io.py``.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.connection = _connect(self.path)

    # -- writing -----------------------------------------------------------

    def save_outcome(self, source_url: str, item: StepOutcome) -> None:
        """Record one step's attempt on one record."""
        self.connection.execute(
            "INSERT INTO outgoing_steps "
            "(source_url, step, status, output, error, notes, model, prompt, review_status, at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_url, step) DO UPDATE SET "
            "status=excluded.status, output=excluded.output, error=excluded.error, "
            "notes=excluded.notes, model=excluded.model, prompt=excluded.prompt, "
            "review_status=excluded.review_status, at=excluded.at",
            (
                source_url,
                item.step,
                item.status,
                json.dumps(item.output) if item.output is not None else None,
                item.error,
                json.dumps(item.notes),
                item.model,
                item.prompt,
                item.review_status,
                item.at,
            ),
        )
        self.connection.commit()

    def save(self, bundle: Any) -> None:
        """Persist one validated result bundle without changing source_url identity."""
        if hasattr(bundle, "model_dump"):
            payload = bundle.model_dump(mode="json")
        else:
            payload = dict(bundle)
        record = payload.get("record") or {}
        source_url = record.get("source_url", "")
        project = record.get("project", "")
        self.connection.execute(
            "INSERT INTO outgoing_bundles (source_url, project, bundle) VALUES (?, ?, ?) "
            "ON CONFLICT(source_url) DO UPDATE SET bundle=excluded.bundle, "
            "project=excluded.project",
            (source_url, project, json.dumps(payload)),
        )
        self.connection.commit()

    # -- reading -----------------------------------------------------------

    def status_of(self, source_url: str, step: str) -> str | None:
        """The last recorded status of ``step`` for one record."""
        row = self.connection.execute(
            "SELECT status FROM outgoing_steps WHERE source_url = ? AND step = ?",
            (source_url, step),
        ).fetchone()
        return row["status"] if row else None

    def outcome(self, source_url: str, step: str) -> dict[str, Any] | None:
        """Read one step's block back, for a later step or for a reviewer."""
        row = self.connection.execute(
            "SELECT * FROM outgoing_steps WHERE source_url = ? AND step = ?",
            (source_url, step),
        ).fetchone()
        if not row:
            return None
        return {
            "step": row["step"],
            "status": row["status"],
            "output": json.loads(row["output"]) if row["output"] else None,
            "error": row["error"],
            "notes": json.loads(row["notes"] or "[]"),
            "model": row["model"],
            "prompt": row["prompt"],
            "review_status": row["review_status"],
            "at": row["at"],
        }

    def earlier_failed(self, source_url: str, step: str) -> bool:
        """Whether a step earlier in the run order failed for this record."""
        target = STEP_NAMES.index(step)
        for earlier in STEP_NAMES[:target]:
            if self.status_of(source_url, earlier) == StepStatus.FAILED:
                return True
        return False

    def is_eligible(
        self,
        document: dict[str, Any],
        step: str,
        *,
        project: str = "",
        retry_errors: bool = False,
    ) -> bool:
        """Whether this record should be processed by ``step`` now.

        1. a step that already ran is not re-run, unless a retry is requested;
        2. a failed step is retried only when explicitly asked for;
        3. a record whose earlier step failed stops there rather than running
           later steps on missing evidence;
        4. a media step on a record with no media is not applicable, not an error.
        """
        source_url = document.get("source_url", "")
        status = self.status_of(source_url, step)

        if status == StepStatus.RAN and not retry_errors:
            return False
        if status == StepStatus.SKIPPED and not retry_errors:
            # Nothing changed for a skip; re-running frame analysis on a
            # text-only record is wasted work, not progress.
            return False
        if status == StepStatus.ABSTAINED and not retry_errors:
            return False
        if status == StepStatus.FAILED and not retry_errors:
            return False
        if status is None and not retry_errors and self.earlier_failed(source_url, step):
            # Nothing upstream supports this step yet. A deliberate retry lifts
            # the block: re-run the failed step, and the chain continues from there.
            return False

        if step == "frame" and not document.get("media"):
            return False
        return True

    def close(self) -> None:
        self.connection.close()
