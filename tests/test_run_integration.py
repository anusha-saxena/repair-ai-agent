from execution.run import TestRunner as Runner


def test_order_dependency_pass_rates(pollution_copy):
    evidence = Runner(f"{pollution_copy}::test_b_victim").run_perturbations(5)
    # These modes disable random ordering, giving exact expectations.
    assert evidence["isolated_pass_rate"] == 100.0
    assert evidence["full_suite_pass_rate"] == 0.0
    suite = evidence["mode_results"]["suite"]
    assert suite["failures"] == 5
    assert any("Another test left shared state" in trace for trace in suite["failure_traces"])
    # Five shuffled samples do not give a reliable statistical threshold.
    assert 0.0 <= evidence["shuffled_pass_rate"] <= 100.0
