def drain(q, handle):
    while q:
        handle(q.pop(0))
    return len(q)
