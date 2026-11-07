def resolve(path):
    if not path or not os.path.exists(path):
        raise SystemExit(2)
    return path
