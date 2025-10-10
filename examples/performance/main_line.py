#!/usr/bin/env python3
import spacetimepy
import time
import json
import os

@spacetimepy.pymonitor(mode="line")
def simple_function(n):
    tmp = []
    for i in range(n):
        tmp.append(i + tmp[-1] if len(tmp) > 0 else 0)
    return sum(tmp)


if __name__ == "__main__":
    monitor = spacetimepy.init_monitoring(db_path="perf_line.db")
    spacetimepy.start_session("Perf Line")
    times = []
    for i in range(100):
        print(f"Iteration {i}")
        t1 = time.time()
        simple_function(i)
        t2 = time.time()
        times.append(t2 - t1)
    
    spacetimepy.end_session()
    monitor.export_db()
    # Db size
    db_size = os.path.getsize("perf_line.db")
    # export as json
    with open("perf_line.json", "w") as f:
        json.dump({"times": times, "db_size": db_size}, f)
    
    