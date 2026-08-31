# invoke pytest on single test/test file
import pytest
import sys
import json
output_test_info = []

def pytest_runtest_logreport(report):
    if(report.when == "call"):
        stdout = ""
        stderr = ""
        failure_trace = ""
        # added exception / failure tracing
        exception_type = ""
        for heading, content in report.sections:
            if "stdout" in heading:
                stdout += content
            elif "stderr" in heading:
                stderr += content

        # accounting for assert test case and report.failed for traces
        if(report.failed):
            failure_trace = str(report.longrepr)
            if hasattr(report.longrepr, "reprcrash"):
                message = report.longrepr.reprcrash.message
                if message.startswith("assert "):
                    exception_type = "AssertionError"
                elif ":" in message:
                    exception_type = message.split(":")[0]
                else:
                    exception_type = message
        output_test_info.append({"test_id": report.nodeid, "outcome": report.outcome, "duration": report.duration, "stdout": stdout.strip(), "stderr": stderr.strip(), "failure_trace": failure_trace, "exception_type": exception_type})

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    test_file = sys.argv[1]
    exit_code = pytest.main([test_file, "-q"], plugins=[sys.modules[__name__]])
    print(json.dumps(output_test_info))
    sys.exit(exit_code)