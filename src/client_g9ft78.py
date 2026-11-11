def fetch(fn, attempts=2):
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except ConnectionError as exc:
            last = exc
    raise last
