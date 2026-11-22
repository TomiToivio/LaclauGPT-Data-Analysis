"""#488 defect 2: the researcher CSV must be readable by a *default* csv.reader.

The bundle carried a 15.9 MB CSV whose source_text and evidence fields exceeded the stdlib field limit
(131,072 characters), so ``csv.reader(open(path))`` raised ``Error field larger than field limit`` unless the
caller raised the limit first. A researcher file that only opens if you know a Python incantation is not a
researcher file.

The chosen fix (owner decision: *split*) never drops a character: an over-long value is written as numbered
continuation columns ``<field>``, ``<field>__part2``, ``<field>__part3`` ... and ``read_csv`` rejoins them.
"""

from __future__ import annotations

import csv

from laclaugpt_data_analysis.canonical import (
    AnalysisSection,
    CanonicalRecord,
    ContentSection,
    SourceSection,
)
from laclaugpt_data_analysis.interchange import CSV_CELL_LIMIT, read_csv, write_csv

LONG_TEXT = "".join(f"segment-{i:06d} " for i in range(20_000))  # ~280k characters


def _record(text: str = LONG_TEXT) -> CanonicalRecord:
    return CanonicalRecord(
        source_url="https://example.test/a",
        source=SourceSection(source_type="web", platform="web"),
        content=ContentSection(title="A long article", text=text),
        analysis=AnalysisSection(),
    )


def test_a_default_csv_reader_can_read_the_written_file(tmp_path):
    path = tmp_path / "analysis_researchers.csv"
    write_csv(path, [_record()])

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))  # deliberately no field_size_limit change
    assert len(rows) == 2
    assert max(len(cell) for cell in rows[1]) <= CSV_CELL_LIMIT


def test_splitting_loses_no_text_and_rejoins_exactly(tmp_path):
    path = tmp_path / "analysis_researchers.csv"
    write_csv(path, [_record()])

    with path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert "content__part2" in header, header  # the whole content JSON is the over-long cell

    restored = read_csv(path)
    assert len(restored) == 1
    assert restored[0].content.text == LONG_TEXT


def test_a_short_value_is_not_split(tmp_path):
    path = tmp_path / "short.csv"
    write_csv(path, [_record("A short text")])

    with path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert not any("__part" in name for name in header)
    assert read_csv(path)[0].content.text == "A short text"
