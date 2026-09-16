import json
import sys

class FlakinessClassifier:
    def __init__(self, test_evidence):
        self.evidence = test_evidence
    def classify(self):
        # determine pass, failure, dependency,
        isolated = self.evidence.get("isolated_pass_rate", 0.0)
        suite = self.evidence.get("full_suite_pass_rate", 0.0)
        shuffled = self.evidence.get("shuffled_pass_rate", 0.0)
        category = "Unknown"
        description = ""
        if isolated == 100.0 and suite == 100.0 and shuffled == 100.0:
            category = "Deterministic Pass"
            description = "Test is completely stable and passes under all conditions."
        elif isolated == 0.0 and suite == 0.0:
            category = "Deterministic Failure"
            description = "Test is broken and fails consistently regardless of execution order."
        elif isolated == 100.0 and suite < 100.0:
            category = "Order Dependency"
            description = "Test passes perfectly in isolation but fails when run alongside other tests. This indicates it expects a clean state but another test is polluting it."
        elif 0.0 < isolated < 100.0:
            category = "Standalone Flakiness"
            description = "Test fails intermittently even when run completely alone. This usually points to timing issues, race conditions, or reliance on random/external data."
        # edge cases 
        else:
            category = "Complex Flakiness"
            description = "The failure pattern is inconsistent and requires deeper inspection."

        return {
            "test_id": self.evidence.get("test_id", "Unknown"),
            "diagnosis_category": category,
            "diagnosis_description": description,
            "evidence": self.evidence
        }

if __name__ == "__main__":
    sample_evidence = {
        "test_id": "tests/test_phase2_demo.py::test_b_victim",
        "baseline_pass_rate": 100.0,
        "shuffled_pass_rate": 50.0,
        "isolated_pass_rate": 100.0,
        "full_suite_pass_rate": 0.0
    }
    
    classifier = FlakinessClassifier(sample_evidence)
    diagnosis = classifier.classify()
    print(json.dumps(diagnosis, indent=2))