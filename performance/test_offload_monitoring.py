"""
Test file for measuring performance with direct monitoring.
"""
import monitoringpy

@monitoringpy.pymonitor
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
    monitoringpy.init_monitoring(output_file="performance/results_offload.jsonl", logging_mode="offload", pyrapl_enabled=False)
    for i in range(1):
        test_function(200)
