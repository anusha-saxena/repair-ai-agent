SHARED_STATE = {"polluted": False}

def test_a_polluter():
    SHARED_STATE["polluted"] = True
    assert True

def test_b_victim():
    assert SHARED_STATE["polluted"] is False, "State was polluted by another test!"

def test_c_cleaner():
    SHARED_STATE["polluted"] = False
    assert True