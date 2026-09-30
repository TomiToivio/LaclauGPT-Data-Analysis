from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from laclaugpt_data_analysis.hungary26 import load_hungary26_workbook
from laclaugpt_data_analysis.hungary26_phase2 import run_phase2
from laclaugpt_data_analysis.xlsx_compat import is_strict_xlsx


def _make_strict_workbook(path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = path.with_name("transitional.xlsx")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "hungary2026_tiktok"
    sheet.append(["url", "username", "caption", "video_file"])
    sheet.append(["https://example.invalid/t/1", "actor", "Támogatom a javaslatot", "clip.mp4"])
    workbook.save(source)

    replacements = {
        b"http://schemas.openxmlformats.org/spreadsheetml/2006/main":
            b"http://purl.oclc.org/ooxml/spreadsheetml/main",
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships":
            b"http://purl.oclc.org/ooxml/officeDocument/relationships",
        b"http://schemas.openxmlformats.org/package/2006/relationships":
            b"http://purl.oclc.org/ooxml/package/relationships",
    }
    with zipfile.ZipFile(source, "r") as incoming, zipfile.ZipFile(
        path, "w", compression=zipfile.ZIP_DEFLATED
    ) as outgoing:
        for info in incoming.infolist():
            data = incoming.read(info.filename)
            if info.filename.endswith((".xml", ".rels")):
                for transitional, strict in replacements.items():
                    data = data.replace(transitional, strict)
                if info.filename == "xl/workbook.xml":
                    data = data.replace(b"<workbook ", b'<workbook conformance="strict" ', 1)
            outgoing.writestr(info, data)


def test_strict_ooxml_tiktok_is_not_silently_empty(tmp_path: Path) -> None:
    workbook = tmp_path / "hungary2026_tiktok.xlsx"
    _make_strict_workbook(workbook)
    assert is_strict_xlsx(workbook)

    records = load_hungary26_workbook(workbook, platform="tiktok")

    assert len(records) == 1
    assert records[0].author == "actor"
    assert records[0].caption == "Támogatom a javaslatot"
    assert records[0].media_ref == "clip.mp4"


def test_phase2_smoke_produces_dna_sna_rdf(tmp_path: Path) -> None:
    pytest.importorskip("networkx")
    pytest.importorskip("rdflib")

    row = {
        "document_id": "hu26-tiktok-1",
        "platform": "tiktok",
        "source_url": "https://example.invalid/t/1",
        "author": "Actor A",
        "author_fullname": "",
        "caption": "Támogatom a nyílt modelleket.",
        "workbook": "hungary2026_tiktok.xlsx",
        "sheet": "hungary2026_tiktok",
        "row_number": 2,
        "source_fingerprint": "abc",
        "vision_status": "ok",
        "vision_output": json.dumps({"observations": []}),
        "summary_status": "ok",
        "summary_output": json.dumps({"parsed": {"summary": "support statement"}}),
        "discourse_status": "ok",
        "discourse_output": json.dumps({"parsed": {"demands": ["open models"]}}),
    }

    def fake_ollama_chat(**kwargs):
        assert "prior_laclau_analysis" in kwargs["user"]
        return json.dumps(
            {
                "statements": [
                    {
                        "concept_label": "Open models should remain available",
                        "agreement": True,
                        "agreement_status": "coded",
                        "evidence_text": "Támogatom a nyílt modelleket.",
                        "confidence": 0.95,
                        "uncertainty_reason": None,
                    }
                ]
            }
        )

    db = tmp_path / "data" / "hungary26.sqlite3"
    result = run_phase2(
        rows=[row],
        private_root=tmp_path,
        db_path=db,
        model="gemma4:12b",
        codebook_version="test-codebook",
        ollama_chat=fake_ollama_chat,
    )

    assert result["dna_statements"] == 1
    assert result["rdf"]["valid"] is True
    assert Path(result["rdf_turtle"]).exists()
    assert (tmp_path / "data" / "dna_statements.csv").exists()
    assert (tmp_path / "data" / "dna_actor_concept.csv").exists()
    assert (tmp_path / "graphs" / "hungary26.ttl").exists()
    assert db.exists()
