"""#425: the prompt-budget audit reads the worker log correctly or it is worse than grep.

The failure this guards against is specific and silent: the worker prints its cycle dict **followed by
two more dicts** on the same line, so a greedy regex produces invalid Python and every cycle silently
counts as zero. A tool that reports 0 cycles while the pipeline runs 12 a day would send the decision
the wrong way.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "ai26_prompt_budget_audit.py"

CYCLE = (
    "2026-11-10 13:12:22,804 INFO    laclaugpt_data_analysis.distributed_worker: "
    "AI26 worker cycle: {'completed': 8, 'duplicate': 1, 'retry': 2, 'dead-letter': 0, "
    "'quarantined': 0, 'idle': 0, 'seeded': 10, 'claims': 11} "
    "failure_classes={'JSONDecodeError': 2} failure_summary={'events': 1610}\n"
)

TRUNC = ("2026-11-10 13:05:00,000 WARNING laclaugpt_data_analysis.llm.structured_output: "
         "structured generation truncated (call 1, finish_reason=length, num_predict=4096)\n")

BUDGET = (
    "2026-11-10 13:09:46,353 WARNING laclaugpt_data_analysis.stages.shared: prompt_budget "
    "prompt budget: 48000 chars (reserved: 6000 answer + 2000 schema), used 39690 |   "
    "task: 701 chars, ~176 tokens, full |   current_source: 20000 chars, ~5000 tokens, "
    "truncated (exceeds its section cap) |   previous_analysis: 12000 chars, ~3000 tokens, "
    "truncated (exceeds its section cap) |   memory: 0 chars, ~0 tokens, omitted (no budget left "
    "after higher-priority sections) |   rag: 0 chars, ~0 tokens, omitted (no budget left after "
    "higher-priority sections)\n"
)


def run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    log = tmp_path / "analysis.log"
    log.write_text(CYCLE + TRUNC + BUDGET, encoding="utf-8")
    return subprocess.run([sys.executable, str(TOOL), "--log", str(log), *args],
                          capture_output=True, text=True, cwd=ROOT)


def test_cycles_are_counted_even_with_extra_dicts_on_the_line(tmp_path):
    """Regression: a greedy regex parsed `{cycle} failure_classes={...}` and reported 0 cycles."""
    result = run(tmp_path, "--json")
    assert result.returncode == 0, result.stderr
    (day,) = json.loads(result.stdout)
    assert day["cycles"] == 1
    assert day["completed"] == 8
    assert day["retry"] == 2


def test_truncations_are_counted_per_rung(tmp_path):
    result = run(tmp_path, "--json")
    (day,) = json.loads(result.stdout)
    assert day["truncations_by_rung"] == {"4096": 1}


def test_sections_dropped_for_budget_are_counted_by_name(tmp_path):
    result = run(tmp_path, "--json")
    (day,) = json.loads(result.stdout)
    assert day["omitted_by_section"] == {"memory": 1, "rag": 1}
    assert day["saturated_lines"] == 1


def test_capped_sections_are_distinguished_from_omitted_ones(tmp_path):
    result = run(tmp_path, "--json")
    (day,) = json.loads(result.stdout)
    assert day["capped_by_section"] == {"current_source": 1, "previous_analysis": 1}


def test_the_human_table_reports_the_ratios_that_decide_the_question(tmp_path):
    result = run(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "| 2026-11-10 | 1 | 8 | 2 | 0 | 1 | 0 | 0 | 1 | 1 | 1 | 1 |" in result.stdout
    assert "8.0 per cycle" in result.stdout
    assert "1 of 1 prompt builds (100.0%)" in result.stdout


def test_an_unreadable_log_is_an_error_not_an_empty_report(tmp_path):
    result = subprocess.run([sys.executable, str(TOOL), "--log", str(tmp_path / "missing.log")],
                             capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 2
    assert "cannot read log" in result.stderr


def test_a_log_without_the_patterns_says_so(tmp_path):
    log = tmp_path / "empty.log"
    log.write_text("nothing here\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(TOOL), "--log", str(log)],
                            capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0
    assert "no dated lines found" in result.stdout
