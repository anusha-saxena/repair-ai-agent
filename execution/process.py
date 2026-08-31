# invoke pytest on single test/test file 
import pytest
import sys
output_test_info = []

def pytest_runtest_logreport(report):
    if(report.when == "call"):
        stdout = ""
        stderr = ""
        for heading, content in report.sections:
            if "stdout" in heading:
                stdout = content
            elif "stderr" in heading:
                stderr = content
        output_test_info.append({"test_id": report.nodeid, "outcome": report.outcome, "duration": report.duration, "stdout": stdout.strip(), "stderr": stderr.strip()})

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    test_file = sys.argv[1]
    exit_code = pytest.main([test_file, "-q"], plugins=[sys.modules[__name__]])
    print(output_test_info)
    sys.exit(exit_code)

