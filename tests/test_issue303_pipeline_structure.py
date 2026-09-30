"""Issue #303 — the readable pipeline structure itself is a guarded contract.

The refactor's whole point is that a researcher can find each scientific step.
That is only true if the steps stay separate: the failure mode is a future change
collapsing stages back into one orchestration blob, or a stage quietly losing its
documentation. These tests make the structure explicit so it cannot rot.

They assert *structure*, not behaviour, so they stay cheap and readable:

* each scientific step lives in its own module;
* the runner sequences them and does not hide them behind a generic abstraction;
* the compatibility facade re-exports the historic import surface, with object
  identity preserved (two `PipelineContext` classes would not compare equal);
* every stage module documents its purpose, inputs and outputs.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src" / "laclaugpt_data_analysis"
STAGES = SRC / "stages"

# The scientific steps the issue requires to be individually inspectable, and the
# stage function each module must expose.
STAGE_MODULES = {
    "preprocess.py": "preprocess_record",
    "frame.py": "analyze_frames",
    "summary.py": "summarize_record",
    "laclau.py": "discourse_analysis",
    "postprocess.py": "postprocess_record",
    "graph.py": "build_discourse_graph",
}

# Names external code imports from the old monolith path. The facade must keep
# serving all of them so 90 call sites do not break.
FACADE_EXPORTS = {
    "PipelineContext",
    "DiscourseProposal",
    "DiscursiveElement",
    "DiscursiveRelation",
    "EventCandidate",
    "FrameProposal",
    "GraphSink",
    "Preprocessor",
    "SummaryProposal",
    "VectorSink",
    "analyze_frames",
    "build_discourse_graph",
    "discourse_analysis",
    "postprocess_record",
    "preprocess_record",
    "prompt_ids_for_stage",
    "run_canonical_pipeline",
    "summarize_record",
    "MultimodalFrameProposal",
    "MultimodalSummaryProposal",
    "_append_stage",
    "_effective_stage_set",
    "_evidence_ids",
    "_relation_chains",
    "_validate_project_analysis_config",
}


def _module_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_each_scientific_step_is_its_own_module() -> None:
    """A researcher must be able to locate each stage by filename alone."""
    for filename, func in STAGE_MODULES.items():
        path = STAGES / filename
        assert path.exists(), f"{filename} must exist as its own stage module"
        assert func in _module_functions(path), (
            f"{filename} must define {func}; the stage's implementation belongs here, "
            "not in the orchestration layer"
        )


def test_runner_sequences_the_stages_in_order() -> None:
    """The runner must call each stage, in pipeline order, visibly."""
    tree = ast.parse((STAGES / "runner.py").read_text(encoding="utf-8"))
    runner = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "run_canonical_pipeline"
        ),
        None,
    )
    assert runner is not None, "stages/runner.py must define run_canonical_pipeline"

    # Collect call sites INSIDE the runner body, in source order. Scanning the
    # whole file would pick up the import statements instead of the execution.
    calls: list[tuple[int, str]] = []
    for node in ast.walk(runner):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name:
                calls.append((node.lineno, name))
    calls.sort()

    order = [
        "preprocess_record",
        "build_modality_plan",
        "analyze_frames",
        "summarize_record",
        "discourse_analysis",
        "postprocess_record",
        "build_discourse_graph",
    ]
    seen = [name for _, name in calls]
    positions = []
    for name in order:
        assert name in seen, f"runner must sequence {name}"
        positions.append(seen.index(name))
    assert positions == sorted(positions), (
        "the runner must execute the stages in pipeline order: " + " -> ".join(order)
    )


def test_runner_is_thin() -> None:
    """The orchestration must not swallow the science.

    A readable runner sequences; it does not implement. If this file grows past a
    generous bound, the science has been pulled back out of its stage modules.
    """
    lines = (STAGES / "runner.py").read_text(encoding="utf-8").splitlines()
    assert len(lines) < 260, (
        f"stages/runner.py is {len(lines)} lines; it should be thin orchestration "
        "(sequencing, routing, error handling), with the research logic in the stage modules"
    )


def test_facade_preserves_the_historic_import_surface() -> None:
    """Every name external callers import must still resolve from the old path."""
    facade = SRC / "canonical_pipeline.py"
    source = facade.read_text(encoding="utf-8")
    tree = ast.parse(source)
    exported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            exported.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Assign):
            exported.update(t.id for t in node.targets if isinstance(t, ast.Name))

    missing = sorted(FACADE_EXPORTS - exported)
    assert not missing, (
        "the compatibility facade no longer re-exports names external code imports: "
        f"{missing}. Add them to canonical_pipeline.py."
    )


def test_facade_shares_object_identity_with_the_stages() -> None:
    """The facade must re-export, not redefine: identity preserved, no second class.

    Two classes named `PipelineContext` would not compare equal, silently breaking
    any caller that passes a context across the boundary.
    """
    import laclaugpt_data_analysis.canonical_pipeline as facade
    import laclaugpt_data_analysis.stages as stages

    assert facade.PipelineContext is stages.PipelineContext
    assert facade.DiscourseProposal is stages.DiscourseProposal
    assert facade.run_canonical_pipeline is stages.run_canonical_pipeline
    assert facade.build_discourse_graph is stages.build_discourse_graph


def test_every_stage_documents_itself_for_a_researcher() -> None:
    """Each stage must explain purpose, inputs and outputs — not just exist."""
    for filename in STAGE_MODULES:
        text = (STAGES / filename).read_text(encoding="utf-8")
        assert text.lstrip().startswith('"""'), f"{filename} needs a module docstring"
        lowered = text.lower()
        for expectation in ("inputs", "outputs"):
            assert expectation in lowered[:4000], (
                f"{filename} must document its {expectation} so a researcher can follow "
                "the data through the stage"
            )


def test_no_science_left_in_the_facade() -> None:
    """The facade is a facade: it must not re-implement a stage."""
    source = (SRC / "canonical_pipeline.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert not defined, (
        f"canonical_pipeline.py defines {sorted(defined)}; the pipeline lives in "
        "stages/ and this module only re-exports it"
    )
