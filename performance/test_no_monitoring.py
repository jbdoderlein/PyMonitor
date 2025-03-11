"""
Test file for measuring performance without monitoring.
"""

def test_function(workload_size):
    """
    A test function with a workload that scales linearly with the input parameter.
    This function performs a simple computation that grows with workload_size.
    """
    result = 0
    for i in range(workload_size * 10000):
        result += i % 100
    return result

if __name__ == "__main__":
    for i in range(50):
        test_function(200)