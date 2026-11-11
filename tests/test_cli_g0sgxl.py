def test_missing_path():
    with pytest.raises(SystemExit):
        resolve('/nope/nope')
