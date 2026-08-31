import random

def test_always_passes():
    assert 1 + 1 == 2

def test_always_fails():
    raise ValueError("Deliberate failure")

def test_flaky():
    assert random.random() > 0.5