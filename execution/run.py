import subprocess
import sys
import json
class TestRunner:
    def __init__(self, test_file):
        self.target_test = test_file
        if "::" in test_file:
            self.file_path, self.test_name = test_file.split("::", 1)
        else:
            self.file_path = test_file
            self.test_name = None

    def run_mode(self, mode, n):
        passes = 0
        failures = 0
        durations = []
        failure_traces = []
        exception_types = []
        for _ in range(n):
            if mode == "baseline":
                cmd = [sys.executable, "execution/process.py", self.target_test, "-p", "no:randomly"]
            elif mode == "shuffled":
                cmd = [sys.executable, "execution/process.py", self.file_path]
            elif mode == "suite":
                cmd = [sys.executable, "execution/process.py", self.file_path, "-p", "no:randomly"]

            proc = subprocess.run(cmd, capture_output=True, text=True)
            lines = proc.stdout.strip().splitlines()
            if not lines:
                continue
            try:
                reports = json.loads(lines[-1])
            except json.JSONDecodeError:
                continue

            for item in reports:
                is_target = (
                    item["test_id"] == self.target_test
                    or item["test_id"].endswith(self.target_test)
                    or (self.test_name and item["test_id"].endswith(f"::{self.test_name}"))
                )

                if is_target:
                    durations.append(item["duration"])
                    if item["outcome"] == "passed":
                        passes += 1
                    else:
                        failures += 1
                        failure_traces.append(item.get("failure_trace", ""))
                        exception_types.append(item.get("exception_type", ""))

        total = passes + failures
        pass_rate = (passes / total) * 100 if total > 0 else 0
        
        return {
            "mode": mode,
            "runs": n,
            "passes": passes,
            "failures": failures,
            "pass_rate": round(pass_rate, 2),
            "durations": durations,
            "failure_traces": failure_traces,
            "exception_types": exception_types
        }

    def run_perturbations(self, n):
        baseline_res = self.run_mode("baseline", n)
        shuffled_res = self.run_mode("shuffled", n)
        suite_res = self.run_mode("suite", n)

        return {
            "test_id": self.target_test,
            "baseline_pass_rate": baseline_res["pass_rate"],
            "shuffled_pass_rate": shuffled_res["pass_rate"],
            "isolated_pass_rate": baseline_res["pass_rate"], 
            "full_suite_pass_rate": suite_res["pass_rate"]
        }

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    test_file = sys.argv[1]
    count = int(sys.argv[2])
    runner = TestRunner(test_file)
    summary = runner.run_perturbations(count)
    print(json.dumps(summary, indent=2))