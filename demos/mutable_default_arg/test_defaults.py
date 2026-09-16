def add_item(item, items=[]):
    items.append(item)
    return items


def test_a_previous_call():
    assert add_item("first") == ["first"]


def test_b_fresh_list():
    assert add_item("second") == ["second"]
