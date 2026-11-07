def timeout(value, low=1, high=300):
    return max(low, min(high, int(value)))
