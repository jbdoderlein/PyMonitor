import sys
import inspect
import types
import jsonpickle

def binary_search(arr, key):
    """
    Simple binary search that assumes arr is sorted in ascending order.
    Returns True if key is found, otherwise False.
    """
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == key:
            return True
        elif arr[mid] < key:
            left = mid + 1
        else:
            right = mid - 1
    return False

