def test_clamp():
    assert timeout(0) == 1
    assert timeout(9999) == 300
    assert timeout(30) == 30
