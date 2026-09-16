SHARED_STATE = {}


def test_a_polluter():
    SHARED_STATE["polluted"] = True
    assert SHARED_STATE["polluted"] is True


def test_b_victim():
    assert SHARED_STATE == {}, "Another test left shared state behind!"
