"""Parse fake API responses without needing credentials or the SDK."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from agent.repair import AIRepairAgent


@pytest.fixture
def repair_agent():
    agent = AIRepairAgent.__new__(AIRepairAgent)
    agent.client = Mock()
    agent.system_prompt = "Expert pytest engineer."
    return agent


@pytest.fixture
def diagnosis():
    return {"diagnosis_category": "Order Dependency",
            "diagnosis_description": "Shared state was polluted.", "evidence": {}}


def fake_response(text, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason,
                          content=[SimpleNamespace(type="text", text=text)])


def test_clean_code_block(repair_agent, diagnosis):
    code = "def test_clean():\n    assert True\n"
    repair_agent.client.messages.create.return_value = fake_response(f"```python\n{code}```")
    assert repair_agent.generate_fix(code, diagnosis, []) == code
    repair_agent.client.messages.create.assert_called_once()


@pytest.mark.parametrize("text", [
    "Here is the fix:\n```python\nx = 1\n```",
    "```python\nx = 1\n```\nThis fixes the state.",
    "Here is the fix:\n```python\nx = 1\n```\nDone.",
    "No code block in this response.",
    "```python\nx = 1\n```\n```python\ny = 2\n```",
])
def test_rejects_prose_or_missing_single_block(repair_agent, diagnosis, text):
    repair_agent.client.messages.create.return_value = fake_response(text)
    with pytest.raises(ValueError, match="exactly one Python code block and no prose"):
        repair_agent.generate_fix("x = 0", diagnosis, [])


@pytest.mark.parametrize("text,error", [
    ("```python\n\n```", "empty code block"),
    ("```python\ndef broken(:\n```", "invalid Python"),
])
def test_rejects_unusable_code(repair_agent, diagnosis, text, error):
    repair_agent.client.messages.create.return_value = fake_response(text)
    with pytest.raises(ValueError, match=error):
        repair_agent.generate_fix("x = 0", diagnosis, [])


def test_rejects_truncated_response(repair_agent, diagnosis):
    repair_agent.client.messages.create.return_value = fake_response("```python\nx = 1\n```", "max_tokens")
    with pytest.raises(ValueError, match="truncated"):
        repair_agent.generate_fix("x = 0", diagnosis, [])
