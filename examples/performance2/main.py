#!/usr/bin/env python3
import decimal
import json
import time


def pi_decimal():
    """decimal"""
    D = decimal.Decimal
    lasts, t, s, n, na, d, da = D(0), D(3), D(3), D(1), D(0), D(0), D(24)
    while s != lasts:
        lasts = s
        n, na = n + na, na + 8
        d, da = d + da, da + 32
        t = (t * n) / d
        s += t
    return s


if __name__ == "__main__":
    times = []
    #for i in range(100):
    for prec in [9, 19]:
        decimal.getcontext().prec = prec
        for _ in range(200):
            t1 = time.time()
            _ = pi_decimal()
            t2 = time.time()
            times.append(t2 - t1)

    # export as json
    with open("perf.json", "w") as f:
        json.dump({"times": times, "db_size": 0}, f)
