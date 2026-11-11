def test_retry():
    calls = []
    def boom():
        calls.append(1)
        raise ConnectionError()
    with pytest.raises(ConnectionError):
        fetch(boom)
    assert len(calls) == 2
