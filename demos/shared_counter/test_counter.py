COUNTER = 0


def increment():
    global COUNTER
    COUNTER += 1
    return COUNTER


def test_a_first_increment():
    assert increment() == 1


def test_b_first_increment():
    assert increment() == 1
