"""Issue #341: media applicability is a decision, not a silence.

Stage 2 (frame) and stage 3 (video) are optional-media stages. The issue requires
that a text-only record records them as explicit ``not_applicable`` -- not a
silent skip, not an error -- that media-bearing records still route through them,
that "no media declared" stays distinguishable from "media declared but not
materialised", and that stage 4 is never blocked behind them.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REGISTRY = json.loads(
    (Path(__file__).resolve().parents[1]
     / "src" / "laclaugpt_data_analysis" / "stages" / "registry.json").read_text()
)


def _stage(reading_order: int) -> dict:
    for stage in REGISTRY["canonical_stages"]:
        if reading_order in stage.get("reading_order", []):
            return stage
    raise AssertionError(f"no stage declares reading order {reading_order}")


class StageThreeIsDeclaredTests(unittest.TestCase):
    def test_video_stage_exists_and_is_machine_readable(self) -> None:
        video = _stage(3)
        self.assertEqual(video["id"], "video")
        self.assertTrue(video["requires_media"])
        self.assertTrue(video["conditional"])

    def test_video_has_no_module_yet_but_says_so(self) -> None:
        self.assertIsNone(_stage(3)["module"])
        self.assertIn("note", _stage(3))

    def test_stage_four_does_not_depend_on_media(self) -> None:
        summary = _stage(4)
        self.assertFalse(summary["requires_media"])
        self.assertFalse(summary["conditional"])


class DryRunStatesTheDecisionTests(unittest.TestCase):
    """#362's dry-run must report applicability, not disclaim knowledge of it."""

    def _payload(self, number: int) -> dict:
        # Use the documented CLI surface (issue #341) rather than a private helper.
        import os
        import subprocess
        import sys

        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(
            [str(Path(__file__).resolve().parents[1] / "src"),
             env.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        completed = subprocess.run(
            [sys.executable, "-m", "laclaugpt_data_analysis.ai26", "step",
             str(number), "--project", "ai26", "--machine", "laskin",
             "--limit", "1", "--dry-run", "--json"],
            capture_output=True, text=True, env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-400:])
        return json.loads(completed.stdout)

    def test_frame_step_reports_conditional_on_media(self) -> None:
        payload = self._payload(2)
        stage = payload["stages"][0]
        self.assertTrue(stage["requires_media"])
        self.assertTrue(stage["media_applicability"].startswith("conditional_on_media"))

    def test_video_step_is_reported_as_module_less(self) -> None:
        payload = self._payload(3)
        stage = payload["stages"][0]
        self.assertFalse(stage["has_module"])
        self.assertTrue(stage["requires_media"])

    def test_dry_run_still_executes_nothing(self) -> None:
        payload = self._payload(2)
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["executed"])
        self.assertEqual(payload["claimed_tasks"], 0)


if __name__ == "__main__":
    unittest.main()
