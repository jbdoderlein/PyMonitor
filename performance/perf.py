#!/usr/bin/env python3
"""
Basic example demonstrating custom object handling in SpaceTimePy.
"""

import spacetimepy
import random
import time
import matplotlib.pyplot as plt

@spacetimepy.pymonitor_line
def linear_function_line(arr):
    for i in range(len(arr)-1):
        arr[i] = arr[i]*arr[i+1]
    return arr

@spacetimepy.pymonitor
def linear_function_mnt(arr):
    for i in range(len(arr)-1):
        arr[i] = arr[i]*arr[i+1]
    return arr


def linear_function(arr):
    for i in range(len(arr)-1):
        arr[i] = arr[i]*arr[i+1]
    return arr

if __name__ == "__main__":
    # Initialize monitoring
    monitor = spacetimepy.init_monitoring(db_path=":memory:", pyrapl_enabled=False)
    times={
        "linear_function": [],
        "linear_function_mnt": [],
        "linear_function_line": [],
    }
    for i in range(1,10):
        print(i)
        list_size = i*10
        arr = random.sample(range(1, list_size*10), list_size)
        start_time = time.time()
        linear_function(arr)
        end_time = time.time()
        times["linear_function"].append(end_time - start_time)
        start_time = time.time()
        linear_function_mnt(arr)
        end_time = time.time()
        times["linear_function_mnt"].append(end_time - start_time)
        start_time = time.time()
        linear_function_line(arr)
        end_time = time.time()
        times["linear_function_line"].append(end_time - start_time)
    print(times)
    plt.plot(times["linear_function"], label="linear_function")
    plt.plot(times["linear_function_mnt"], label="linear_function_mnt")
    plt.plot(times["linear_function_line"], label="linear_function_line")
    plt.legend()
    plt.show()
    
    
    