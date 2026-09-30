"""Pydantic models for the readable analysis steps.

The models are grouped by role, mirroring the step files:

    incoming.py    what a step receives (``IncomingRecord``)
    step1..step7   each step's output model

Each output model is deliberately small and obvious. It describes exactly the
fields the corresponding step writes, so a reader can compare the model against
the step file and see the contract in one place.

The canonical persisted record remains ``laclaugpt_data_analysis.canonical``;
these models are the readable step-level view and must stay mappable to it.
"""
