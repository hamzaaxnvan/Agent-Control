def test_drain():
    seen = []
    assert drain([1, 2], seen.append) == 0
    assert seen == [1, 2]
