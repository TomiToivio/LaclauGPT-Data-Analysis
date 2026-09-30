"""Issue #315 — the hand-written pipeline scaffold is a guarded contract.

The issue defines three roles: an agent builds the framework (step 1), Tomi
hand-writes the analysis logic (step 2), and agents afterwards "write the code for
requested tasks around these steps but **not change the steps themselves**"
(step 3). Step 3 only holds if the step surface is pinned by something executable.

These tests assert *structure*, never analysis behaviour, so they stay cheap and
readable and do not constrain Tomi's implementation:

* all seven step modules exist, in order, each in its own file;
* each exposes the documented callable with the documented parameter names, so a
  future agent cannot quietly rename, merge or re-purpose a step;
* the four auxiliary modules keep their documented public surface;
* the step bodies remain the agent-owned boundary: the framework is allowed to
  raise `NotImplementedError` while it is unimplemented, and nothing here requires
  it to stay that way.

The precedent is `tests/test_issue303_pipeline_structure.py`, which guards the
`src/laclaugpt_data_analysis/stages/` refactor the same way.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PIPELINE = REPO / "laclaugpt"

# Ordered because the sequence is the scientific method, not an implementation
# detail: preprocessing must precede framing, framing must precede summary, and
# DNA/SNA consume the Laclaudian analysis rather than replacing it.
STEPS = {
    "step_01_preprocess.py": ("preprocess", ("record",)),
    "step_02_frame.py": ("analyze_frames", ("record",)),
    "step_03_summary.py": ("summarize", ("record", "frames")),
    "step_04_postprocess.py": ("postprocess", ("record", "summary")),
    "step_05_laclau.py": ("analyze_laclau", ("record", "summary", "descriptive")),
    "step_06_dna.py": ("analyze_dna", ("record", "laclau")),
    "step_07_sna.py": ("analyze_sna", ("record", "dna")),
}

AUXILIARY = {
    "pipeline_models.py": (
        "MediaItem",
        "HumanPipelineRecord",
        "FrameObservation",
        "SummaryResult",
        "PostprocessResult",
        "LaclauResult",
        "DNAResult",
        "SNAResult",
        "AnalysisBundle",
    ),
    "pipeline_io.py": ("IncomingRecords", "OutgoingResults", "read_pending", "write_result"),
    "pipeline_prompts.py": ("load_project_system_prompt", "combine_prompts"),
    "pipeline_rdf.py": ("record_triples", "relation_triple"),
}


def _module_ast(filename: str) -> ast.Module:
    path = PIPELINE / filename
    assert path.is_file(), f"{filename} is missing from the readable pipeline"
    return ast.parse(path.read_text(encoding="utf-8"))


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}


def _import_laclaugpt_module(name: str):
    """Import a scaffold module.

    ``laclaugpt/`` is on pytest's ``pythonpath`` (see pyproject.toml) and has no
    ``__init__.py``, so these are top-level modules by design.
    """
    return importlib.import_module(name)


@pytest.mark.parametrize("filename", sorted(STEPS))
def test_step_module_exists_and_is_importable(filename: str) -> None:
    module = _import_laclaugpt_module(filename.removesuffix(".py"))
    assert module.__doc__, f"{filename} must document its purpose and legacy reference"


@pytest.mark.parametrize("filename,expected", sorted(STEPS.items()))
def test_step_exposes_its_documented_entry_point(filename: str, expected: tuple) -> None:
    """A step's callable name and parameter names are the contract agents must not move."""
    function_name, parameters = expected
    functions = _functions(_module_ast(filename))
    assert function_name in functions, (
        f"{filename} must expose {function_name}(); agents may add code around the "
        "steps but must not rename or remove them (issue #315 step 3)"
    )
    assert tuple(arg.arg for arg in functions[function_name].args.args) == parameters, (
        f"{filename}:{function_name} signature changed; the step's inputs are part of "
        "the contract"
    )


def test_all_seven_steps_are_separate_files_in_order() -> None:
    """Each scientific step owns its own module; none may be merged into another."""
    present = sorted(p.name for p in PIPELINE.glob("step_*.py"))
    assert present == sorted(STEPS), (
        "the seven steps must stay one-per-file so a researcher can read each stage "
        f"alone; found {present}"
    )


@pytest.mark.parametrize("filename,names", sorted(AUXILIARY.items()))
def test_auxiliary_module_exposes_its_public_surface(filename: str, names: tuple) -> None:
    module = _import_laclaugpt_module(filename.removesuffix(".py"))
    missing = [name for name in names if not hasattr(module, name)]
    assert not missing, f"{filename} no longer exposes {missing}"


def test_pipeline_map_documents_every_step() -> None:
    """The readable map is part of the deliverable, not decoration."""
    text = (PIPELINE / "HUMAN_PIPELINE.md").read_text(encoding="utf-8")
    for filename in STEPS:
        assert filename in text, f"HUMAN_PIPELINE.md does not name {filename}"


def test_steps_do_not_import_each_others_internals() -> None:
    """Steps communicate through pipeline_models contracts, not by reaching around them.

    Importing another step's module would let one stage re-implement or bypass
    another, which is exactly the collapse the readable layout exists to prevent.
    """
    offenders: list[str] = []
    for filename in STEPS:
        tree = _module_ast(filename)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if any(name.startswith(other.removesuffix(".py")) for other in STEPS):
                    offenders.append(f"{filename} imports {name}")
    assert not offenders, offenders
