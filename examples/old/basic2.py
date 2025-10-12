#!/usr/bin/env python3
"""
Basic example demonstrating custom object handling in SpaceTimePy.
"""

import spacetimepy
import random
import time
import matplotlib.pyplot as plt

@spacetimepy.pymonitor_line
def binary_search_line(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

@spacetimepy.pymonitor
def binary_search_fct(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1


def binary_search(arr, target):
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

if __name__ == "__main__":
    # Initialize monitoring
    monitor = spacetimepy.init_monitoring(db_path="basic2.db", pyrapl_enabled=False)
    times={
        "binary_search_fct": [],
        "binary_search_line": [],
        "binary_search": []
    }
    for i in range(1,10):
        list_size = i*100
        arr = random.sample(range(1, list_size*10), list_size)
        arr.sort()
        target = random.randint(1, list_size*10)
        start_time = time.time()
        binary_search_fct(arr, target)
        end_time = time.time()
        times["binary_search_fct"].append(end_time - start_time)
        start_time = time.time()
        binary_search_line(arr, target)
        end_time = time.time()
        times["binary_search_line"].append(end_time - start_time)
        start_time = time.time()
        binary_search(arr, target)
        end_time = time.time()
        times["binary_search"].append(end_time - start_time)
    print(times)
    plt.plot(times["binary_search_fct"], label="binary_search_fct")
    plt.plot(times["binary_search_line"], label="binary_search_line")
    plt.plot(times["binary_search"], label="binary_search")
    plt.legend()
    plt.show()
    
    
    