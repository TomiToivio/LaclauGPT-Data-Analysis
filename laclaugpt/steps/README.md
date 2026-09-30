# The LaclauGPT analysis steps

This directory holds the **seven analysis steps** of the LaclauGPT pipeline in the
order they run. It is the human-readable, human-written core: one file per step,
readable top to bottom, no framework between you and the research logic.

```text
incoming data
      │
  1. preprocess              extract frames, OCR, transcript, translation
      │
  2. frame_analysis          visual reading of images / video frames   (optional)
      │
  3. summary                 multimodal summary of the whole record
      │
  4. postprocess             structured fields from the summary
      │
  5. discourse               Laclaudian discourse analysis
      │
  6. dna                     Discourse Network Analysis
      │
  7. sna                     Social Network Analysis
      │
outgoing data
```

The legacy reference for steps 1–5 is
[`LaclauGPT-Multimodal-Analysis`](https://github.com/TomiToivio/LaclauGPT-Multimodal-Analysis)
(`puhti_preprocess.py`, `puhti_frame.py`, `puhti_summary.py`, `puhti_postprocess.py`,
`puhti_populism.py`). Steps 6 and 7 are new: the legacy pipeline has no network
layers.

---

## The rule that keeps this readable

There are three kinds of work here, and they have different owners:

| | Who | May change |
|---|---|---|
| **The steps** — `laclaugpt/steps/step*.py` and the `STEPS` registry | Tomi, by hand | Only Tomi, deliberately |
| **The scaffolding around the steps** — models, databases, prompts, RDF, the runner | Agents | Agents, freely |
| **Requested tasks around the steps** | Agents | Agents, freely — without editing the step files |

**Agents must not edit the step modules.** A step file defines the research
method: what is read, what is asked of the model, what is written back. Agents
add capabilities *around* that boundary — a new storage adapter, a new exporter,
a new prompt variant, a test, a bug fix in a helper — by changing the
scaffolding, not the step.

If a step itself appears wrong, report it and leave the file alone. The point of
this directory is that a researcher can read the method and trust that it has not
been quietly rewritten by an agent.

This mirrors the `TOMI-LOCKED` convention in `../AGENTS.md`, which applies to
anything marked as a human-controlled invariant.

---

## Each step has the same shape

Reading any step file, you should find the same sections in the same order:

| Section | What it tells you |
|---|---|
| **Purpose** | What this step is for, and what is out of scope for it |
| **Legacy reference** | Which legacy script it corresponds to (steps 1–5) |
| **Inputs** | Which record fields are read |
| **Outputs** | Which record fields are written |
| **Model** | Which prompt is used, and the Pydantic model the reply must satisfy |
| **Uncertainty** | How abstention and low confidence are recorded |
| **Provenance** | What is recorded so the result can be audited |
| **`run()`** | The single function that does the work |

Keeping the shape identical across steps is what makes the sequence legible from
the filenames alone: open `step1_preprocess.py`, read top to bottom, and you have
the whole first step without chasing anything.

---

## Running the steps

Each step is independently runnable. The runner is deliberately boring:

```bash
cd laclaugpt

python -m steps.run --project ai26 --step preprocess
python -m steps.run --project ai26 --step frame_analysis
python -m steps.run --project ai26 --step summary
python -m steps.run --project ai26 --step postprocess
python -m steps.run --project ai26 --step discourse
python -m steps.run --project ai26 --step dna
python -m steps.run --project ai26 --step sna

# or the whole chain in order
python -m steps.run --project ai26 --all
```

Every step must be safe to run repeatedly: a step that has nothing to do should
say so and exit 0 rather than reprocessing or erroring. Cron can then be boring,
which is a feature.

---

## What lives outside this directory

These support the steps but are not part of the method, so agents own them:

```text
laclaugpt/
├── steps/            the seven steps (this directory) — hand-written
├── models/           Pydantic models: incoming records and step outputs
├── db/               incoming/outgoing database helpers
├── projects/         per-project system prompts and configuration
├── rdf/              RDF export for the analysis layers
└── docs/             notes on the data flow
```

Start with `models/incoming.py` to see what arrives, and `db/outgoing.py` to see
what each step writes back.
