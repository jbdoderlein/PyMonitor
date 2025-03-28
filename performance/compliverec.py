#!/usr/bin/env python3
"""
Basic example demonstrating custom object handling in PyMonitor.
"""

import monitoringpy
import random
import time
import matplotlib.pyplot as plt

@monitoringpy.pymonitor_line
def linear_function_line(arr):
    for i in range(len(arr)-1):
        arr[i] = arr[i]*arr[i+1]
    return arr

def measure_execution_time(size):
    # Initialize monitoring with in-memory database
    monitor = monitoringpy.init_monitoring(db_path=":memory:", pyrapl_enabled=False)
    
    # Create array and measure execution time
    arr = random.sample(range(1, size*10), size)
    start_time = time.time()
    linear_function_line(arr)
    end_time = time.time()
    
    # Get the number of snapshots from the database
    # The number of snapshots will be proportional to the array size
    # since we're recording each line execution
    session = monitor.session
    snapshot_count = session.query(monitoringpy.models.StackSnapshot).count()
    
    return end_time - start_time, snapshot_count

if __name__ == "__main__":
    # Test with different array sizes
    sizes = [i for i in range(1,200)]
    times = []
    snapshots = []
    
    for size in sizes:
        print(f"Testing with size {size}")
        execution_time, snapshot_count = measure_execution_time(size)
        times.append(execution_time)
        snapshots.append(snapshot_count)
    
    # Create the plot
    plt.figure(figsize=(10, 6))
    plt.plot(snapshots, times, 'bo-')
    plt.xlabel('Number of Stack Snapshots')
    plt.ylabel('Execution Time (seconds)')
    plt.title('Execution Time vs Number of Stack Snapshots')
    plt.grid(True)
    plt.ylim(bottom=0)  # Set y-axis to start at 0
    plt.show()
    
    # Print the raw data
    print("\nRaw data:")
    print("Snapshots | Time (seconds)")
    print("-" * 30)
    for snap, t in zip(snapshots, times):
        print(f"{snap:9d} | {t:.6f}")
    
    
    