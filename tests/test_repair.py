"""Check repair retries without making paid API calls."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent.repair import AIRepairAgent
from main import repair_test


class RepairTests(unittest.TestCase):
    def evidence(self, rate):
        return {"test_id": "test_demo.py::test_demo", "baseline_pass_rate": 100.0,
                "isolated_pass_rate": 100.0, "shuffled_pass_rate": rate,
                "full_suite_pass_rate": rate,
                "mode_results": {"suite": {"failure_traces": ["AssertionError: dirty state"]}}}

    def test_retry_uses_failure_feedback_and_keeps_patch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_demo.py"
            original = "STATE = {}\ndef test_demo():\n    assert True\n"
            path.write_text(original)
            agent = Mock()
            agent.generate_fix.side_effect = [original + "# first\n", original + "# second\n"]
            runner = Mock()
            def observe(n):
                if runner.run_perturbations.call_count == 2:
                    self.assertTrue(path.read_text().endswith("# first\n"))
                return self.evidence(100.0 if runner.run_perturbations.call_count == 3 else 0.0)
            runner.run_perturbations.side_effect = observe
            with patch("main.AIRepairAgent", return_value=agent), patch("main.TestRunner", return_value=runner):
                self.assertEqual(repair_test(str(path) + "::test_demo", 1), 0)
            feedback = agent.generate_fix.call_args_list[1].args[3]
            self.assertIn("AssertionError", str(feedback))
            self.assertEqual(agent.generate_fix.call_args_list[1].args[0], original)
            self.assertTrue(path.read_text().endswith("# second\n"))

    def test_exhausted_attempts_restore_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_demo.py"
            original = b"STATE = {}\r\ndef test_demo():\r\n    assert True\r\n"
            path.write_bytes(original)
            agent = Mock()
            agent.generate_fix.return_value = "def test_demo():\n    assert False\n"
            runner = Mock()
            runner.run_perturbations.return_value = self.evidence(0.0)
            with patch("main.AIRepairAgent", return_value=agent), patch("main.TestRunner", return_value=runner):
                self.assertEqual(repair_test(str(path) + "::test_demo", 1, 3), 1)
            self.assertEqual(agent.generate_fix.call_count, 3)
            self.assertEqual(path.read_bytes(), original)

    def test_stable_test_does_not_create_agent_or_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_demo.py"
            path.write_text("def test_demo():\n    assert True\n")
            with patch("main.TestRunner") as runner, patch("main.AIRepairAgent") as agent:
                runner.return_value.run_perturbations.return_value = self.evidence(100.0)
                self.assertEqual(repair_test(str(path), 1), 0)
                agent.assert_not_called()
            self.assertFalse(path.with_name(path.name + ".bak").exists())

    def test_code_extraction_rejects_malformed_responses(self):
        agent = AIRepairAgent.__new__(AIRepairAgent)
        agent.client = Mock()
        agent.system_prompt = "pytest engineer"
        diagnosis = {"diagnosis_category": "Order Dependency", "diagnosis_description": "dirty state"}
        for text in ["No code", "```python\ninvalid python !\n```", "```python\n\n```"]:
            agent.client.messages.create.return_value = SimpleNamespace(
                stop_reason="end_turn", content=[SimpleNamespace(type="text", text=text)])
            with self.assertRaises(ValueError):
                agent.generate_fix("STATE = {}", diagnosis, ["STATE"])
        agent.client.messages.create.return_value.content[0].text = "```python\nSTATE = {}\n```"
        self.assertEqual(agent.generate_fix("STATE = {}", diagnosis, ["STATE"]), "STATE = {}\n")
