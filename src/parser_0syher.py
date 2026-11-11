def parse(pairs):
    out = {}
    for k, v in pairs:
        if not k:
            raise ValueError('empty key')
        out[k] = v
    return out
