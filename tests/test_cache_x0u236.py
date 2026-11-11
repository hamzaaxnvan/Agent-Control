def test_cap():
    s = {}
    for i in range(200):
        put(s, i, i)
    assert len(s) == 128
