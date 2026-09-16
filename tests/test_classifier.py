"""Cover every classifier branch using explicit evidence."""
import pytest
from analysis.classifier import FlakinessClassifier


@pytest.mark.parametrize("isolated,suite,shuffled,category", [
    (100.0, 100.0, 100.0, "Deterministic Pass"),
    (0.0, 0.0, 0.0, "Deterministic Failure"),
    (100.0, 0.0, 40.0, "Order Dependency"),
    (40.0, 40.0, 40.0, "Standalone Flakiness"),
    (100.0, 100.0, 40.0, "Complex Flakiness"),
    (0.0, 100.0, 60.0, "Complex Flakiness"),
])
def test_classifier_categories(isolated, suite, shuffled, category):
    evidence = {"test_id": "test_example.py::test_example",
                "baseline_pass_rate": isolated, "isolated_pass_rate": isolated,
                "full_suite_pass_rate": suite, "shuffled_pass_rate": shuffled}
    diagnosis = FlakinessClassifier(evidence).classify()
    assert diagnosis["diagnosis_category"] == category
    assert diagnosis["diagnosis_description"]
    assert diagnosis["test_id"] == evidence["test_id"]
    assert diagnosis["evidence"] == evidence
