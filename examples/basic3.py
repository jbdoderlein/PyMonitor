#!/usr/bin/env python3
"""
Basic example demonstrating custom object handling in PyMonitor.
"""

import monitoringpy
import random

@monitoringpy.pymonitor_line
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

if __name__ == "__main__":
    # Initialize monitoring
    monitor = monitoringpy.init_monitoring(db_path="basic3.db", pyrapl_enabled=False)
    test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    binary_search_line(test_list, 5)
    

    
    
    