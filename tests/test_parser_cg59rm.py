def test_empty_key():
    with pytest.raises(ValueError):
        parse([('', 1)])
