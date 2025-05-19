#!/usr/bin/env python3
"""
Basic example demonstrating PyMonitor.
"""
import monitoringpy


@monitoringpy.pymonitor(mode="line")
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
    monitoringpy.init_monitoring(db_path="main.db")
    with monitoringpy.session_context(name="main"):
        binary_search([1, 2, 3, 4, 5], 3)
        binary_search([1, 2, 3, 4, 5], 6)
        binary_search([1, 2, 3, 4, 5], 0)
    