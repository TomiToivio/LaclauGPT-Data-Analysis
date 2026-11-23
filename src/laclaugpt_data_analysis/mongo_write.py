"""One boundary rule for MongoDB writes: ``_id`` is immutable and must never be sent.

MongoDB refuses an update that mentions ``_id`` in ``$set`` or that replaces a document
with a different ``_id`` (``WriteError`` code 66). The failure discards the write — and in
this pipeline the write is often a finished analysis, so the model's work is thrown away
and the task is retried.

It happened twice, in two different write paths (#515 in ``MongoStore.write``, #552 in
``MongoTaskStore.write_result``, where pymongo had added ``_id`` to the caller's dict while
encoding a failed insert). Fixing each instance left the class open, so this module owns the
rule and every Mongo writer calls it: a row that came back from a read, or a dict that
pymongo has already touched, cannot carry ``_id`` into an update.

``_id`` in a *nested* field is data, not identity (for example a source's own native id),
and is preserved.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ["without_immutable_id"]


def without_immutable_id(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``document`` with the top-level ``_id`` removed.

    A shallow copy is deliberate: only the top-level key is MongoDB's identity, and copying
    nested structures would silently detach large payloads from their owner for no gain.
    """
    return {key: value for key, value in dict(document).items() if key != "_id"}
