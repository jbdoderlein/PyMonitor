# PyMonitor Performance Testing

This directory contains scripts to measure and compare the performance impact of different monitoring configurations.

## Test Configurations

The tests compare three configurations:

1. **No Monitoring**: Baseline performance without any monitoring
2. **Direct Logging**: Monitoring with direct file writing (synchronous)
3. **Offload Logging**: Monitoring with background thread for logging (asynchronous)

## Running the Tests

### Option 1: Using cProfile (Recommended)

For detailed performance analysis, use the cProfile-based script:

```bash
python performance/profile_test.py
```

This script:
1. Uses Python's built-in cProfile module to analyze execution
2. Provides detailed breakdown of where time is spent
3. Shows exactly which parts of the monitoring code are consuming time
4. Generates both summary statistics and detailed profile reports

### Option 2: Using timeit

For simple timing measurements:

```bash
python performance/performance_test_isolated.py
```

## Output

### cProfile Output

The cProfile tests generate:

- `profile_no_monitoring.txt`: Detailed profile of execution without monitoring
- `profile_direct_logging.txt`: Detailed profile of direct logging mode
- `profile_offload_logging.txt`: Detailed profile of offload logging mode
- `profile_comparison.png`: Bar chart comparing execution times
- `profile_overhead.png`: Bar chart showing monitoring overhead
- `profile_results.json`: Summary of timing results

### timeit Output

The timeit tests generate:

- `performance_results.json`: Detailed results including statistical metrics
- `results_direct.jsonl` and `results_offload.jsonl`: Raw monitoring data
- `execution_times.png`: Average execution times with error bars
- `overhead_bar_chart.png`: Relative overhead with error propagation
- `execution_boxplot.png`: Distribution of execution times as boxplots

## Interpreting the Results

### cProfile Results

The profile text files show:
1. Which functions consume the most time
2. How many times each function was called
3. The cumulative time spent in each function
4. The time per call for each function

This helps identify exactly where the monitoring overhead comes from and which parts of the code might benefit from optimization.

### timeit Results

The timeit plots help visualize:
1. The average execution time and variability for each configuration
2. The relative overhead of each monitoring approach with error margins
3. The distribution of execution times to identify outliers and consistency

## Customizing the Tests

For the cProfile tests, you can modify:
- `iterations`: Number of times to run each test (default: 50)

For the timeit tests, you can modify:
- `repetitions`: Number of test repetitions (default: 30)
- `workload`: Workload size for the test function (default: 200)

Example:
```python
# For more intensive testing
results = run_performance_tests(repetitions=50, workload=300)