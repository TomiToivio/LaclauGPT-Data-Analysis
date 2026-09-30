"""Database helpers for the readable analysis steps.

Two directions, mirroring the step flow:

    incoming.py   read records that are ready for a step
    outgoing.py   write a step's result back

Both are thin. They exist so the step files do not each re-implement the same
MongoDB queries, and so there is one obvious place to change storage behaviour.

The existing ``laclaugpt_mongo.py`` remains the low-level Mongo helper and is used
by the current Phase 0 core; these functions are the step-level view over it.
"""
