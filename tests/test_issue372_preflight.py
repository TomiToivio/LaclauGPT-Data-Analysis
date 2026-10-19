"""#372: a missing runtime dependency must fail fast and name itself.

Ported from the Multimodal pipeline's STEP PREFLIGHT ERROR contract (#292/#293,
adapted -- no EP24 imports, no new dependencies). The destination already
reported endpoint reachability; what it could not say was which interpreter was
missing which module, which is the difference between "the model server is down"
and "this venv was never installed into".
"""

from __future__ import annotations

import builtins
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from laclaugpt_data_analysis import preflight


class DependencyNamingTests(unittest.TestCase):
    def test_healthy_interpreter_names_no_problem(self) -> None:
        self.assertEqual(preflight._dependency_problems(), [])

    def test_missing_dependency_names_module_interpreter_and_remedy(self) -> None:
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "pymongo":
                raise ImportError("no module named pymongo")
            return real_import(name, *args, **kwargs)

        with mock.patch.object(builtins, "__import__", fake_import):
            problems = preflight._dependency_problems("/opt/venv/bin/python")
        self.assertEqual(len(problems), 1)
        message = problems[0]
        self.assertIn("PREFLIGHT ERROR: pymongo", message)
        self.assertIn("/opt/venv/bin/python", message)
        self.assertIn("install the runtime requirements", message)
        self.assertNotIn("Traceback", message)

    def test_check_is_local_only(self) -> None:
        """No sockets, no store, no model call: an import probe cannot fail fast if
        it first waits on a network."""
        with mock.patch("socket.socket", side_effect=AssertionError("network used")):
            self.assertEqual(preflight._dependency_problems(), [])


class StrictModeTests(unittest.TestCase):
    def test_strict_prints_named_error_and_exits_two(self) -> None:
        report = {"status": "invalid", "problems": ["PREFLIGHT ERROR: redis unavailable in /usr/bin/python - x"]}
        err = io.StringIO()
        with mock.patch.object(preflight, "preflight_report", return_value=report), \
             redirect_stderr(err):
            code = preflight.main(["--strict"])
        self.assertEqual(code, 2)
        self.assertIn("PREFLIGHT ERROR: redis", err.getvalue())
        self.assertNotIn("{", err.getvalue(), "strict mode must not dump JSON at the operator")

    def test_non_strict_keeps_the_json_report(self) -> None:
        report = {"status": "ok", "checks": {}}
        out = io.StringIO()
        with mock.patch.object(preflight, "preflight_report", return_value=report), \
             redirect_stdout(out):
            code = preflight.main([])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "ok")

    def test_strict_success_is_silent_on_stderr(self) -> None:
        report = {"status": "ok", "checks": {}}
        err = io.StringIO()
        with mock.patch.object(preflight, "preflight_report", return_value=report), \
             redirect_stderr(err), redirect_stdout(io.StringIO()):
            self.assertEqual(preflight.main(["--strict"]), 0)
        self.assertEqual(err.getvalue(), "")

    def test_credentials_never_reach_the_output(self) -> None:
        report = {"status": "ok", "llm_endpoint": preflight.sanitize_url("http://u:secret@host:11434")}
        out = io.StringIO()
        with mock.patch.object(preflight, "preflight_report", return_value=report), \
             redirect_stdout(out):
            preflight.main([])
        self.assertNotIn("secret", out.getvalue())


if __name__ == "__main__":
    unittest.main()
