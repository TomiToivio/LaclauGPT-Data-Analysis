"""Compatibility loader for ISO/IEC 29500 Strict XLSX workbooks.

openpyxl currently expects Transitional OOXML namespaces. Some researcher-authored
exports use Strict namespaces and otherwise look like ordinary XLSX packages. This
module normalizes only package XML namespaces in memory before handing the workbook
to openpyxl; the original source file is never modified.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Callable

STRICT_TO_TRANSITIONAL = {
    b"http://purl.oclc.org/ooxml/spreadsheetml/main":
        b"http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    b"http://purl.oclc.org/ooxml/officeDocument/relationships":
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    b"http://purl.oclc.org/ooxml/package/relationships":
        b"http://schemas.openxmlformats.org/package/2006/relationships",
    b"http://purl.oclc.org/ooxml/drawingml/main":
        b"http://schemas.openxmlformats.org/drawingml/2006/main",
    b"http://purl.oclc.org/ooxml/drawingml/spreadsheetDrawing":
        b"http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
}


def is_strict_xlsx(path: str | Path) -> bool:
    source = Path(path)
    with zipfile.ZipFile(source) as archive:
        workbook = archive.read("xl/workbook.xml")
    return b"purl.oclc.org/ooxml" in workbook or b'conformance="strict"' in workbook


def normalized_xlsx_bytes(path: str | Path) -> bytes:
    """Return a Transitional-namespace copy of a Strict package in memory."""
    source = Path(path)
    output = io.BytesIO()
    with zipfile.ZipFile(source, "r") as incoming, zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED
    ) as outgoing:
        for info in incoming.infolist():
            data = incoming.read(info.filename)
            if info.filename.endswith((".xml", ".rels")):
                for strict, transitional in STRICT_TO_TRANSITIONAL.items():
                    data = data.replace(strict, transitional)
                data = data.replace(b' conformance="strict"', b"")
            outgoing.writestr(info, data)
    return output.getvalue()


def load_openpyxl_compatible(
    path: str | Path,
    load_workbook: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    """Load Transitional XLSX normally and Strict XLSX through in-memory normalization."""
    source = Path(path)
    if not is_strict_xlsx(source):
        return load_workbook(source, **kwargs)
    return load_workbook(io.BytesIO(normalized_xlsx_bytes(source)), **kwargs)
