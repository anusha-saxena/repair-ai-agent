import subprocess
import sys
import json

def run_n_times(test_file, n):
    passes = 0
    failures = 0
    durations = []
    failure_traces = []
    output_info = []
    exception_types = []
    # run n times
    for i in range(n):
        # execute process.py
        proc = subprocess.run([sys.executable, "execution/process.py", test_file], capture_output=True, text=True)
        lines = proc.stdout.strip().splitlines()
        if(len(lines) == 0):
            continue
        # note: probably flesh out the parsing more later incase pytest outputs warnings/other random things
        last_line = lines[-1]
        reports = json.loads(last_line)

        for item in reports:
            durations.append(item["duration"])
            if(item["outcome"] == "passed"):
                passes += 1
            else:
                failures += 1
                failure_traces.append(item["failure_trace"])
                exception_types.append(item["exception_type"])
    if(passes + failures != 0):
        pass_rate = (passes / (passes+failures)) * 100
    else:
        pass_rate = 0
    output_info.append({"test_id": test_file, "runs": n, "passes": passes, "failures": failures, "pass_rate": pass_rate, "durations": durations, "failure_traces": failure_traces, "exception_types": exception_types})
    return output_info

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(1)
    test_file = sys.argv[1]
    count = int(sys.argv[2])
    summary = run_n_times(test_file, count)
    print(json.dumps(summary, indent=2))
