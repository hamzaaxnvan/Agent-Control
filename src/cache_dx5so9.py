def put(store, key, value, limit=128):
    if len(store) >= limit and key not in store:
        store.pop(next(iter(store)))
    store[key] = value
    return store
