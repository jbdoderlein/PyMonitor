"""
Performance test script that uses cProfile to analyze the performance impact of monitoring.
This provides more detailed information about where time is spent during execution.
"""
import os
import cProfile
import pstats
import io
import matplotlib.pyplot as plt
import numpy as np
import subprocess
import json

def run_profile_test(test_module, test_name, iterations=10):
    """Run a profile test on the specified module and function"""
    print(f"Profiling {test_name}...")
    
    # Create a profile object
    profiler = cProfile.Profile()
    
    # Import the test module
    module = __import__(f"performance.{test_module}", fromlist=['run_test'])
    
    # Profile the function execution
    profiler.enable()
    for _ in range(iterations):
        module.run_test()
    profiler.disable()
    
    # Create a StringIO object to capture the stats output
    s = io.StringIO()
    
    # Sort the stats by cumulative time
    ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
    
    # Print the stats to the StringIO object
    ps.print_stats()
    
    # Get the stats as a string
    stats_str = s.getvalue()
    
    # Save the stats to a file
    with open(f"performance/profile_{test_name}.txt", "w") as f:
        f.write(stats_str)
    
    print(f"Profile saved to performance/profile_{test_name}.txt")
    
    # Extract the total time
    total_time = profiler.getstats()[0].totaltime / iterations
    
    return {
        "total_time": total_time,
        "stats": stats_str
    }

def compare_results(results):
    """Compare the results of the different tests"""
    baseline_time = results["no_monitoring"]["total_time"]
    
    for name, result in results.items():
        if name == "no_monitoring":
            continue
        
        overhead = ((result["total_time"] - baseline_time) / baseline_time) * 100
        print(f"{name} overhead: {overhead:.2f}%")
        
    return results

def plot_results(results, output_file="performance/profile_comparison.png"):
    """Plot the results of the different tests"""
    plt.figure(figsize=(10, 6))
    
    # Extract the times
    names = list(results.keys())
    times = [results[name]["total_time"] for name in names]
    
    # Create the bar chart
    bars = plt.bar(names, times, color=['#66c2a5', '#fc8d62', '#8da0cb'])
    
    # Add the values on top of the bars
    for i, bar in enumerate(bars):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.001,
                f"{times[i]:.6f}s", ha='center', fontsize=10)
    
    # Add labels and title
    plt.xlabel("Monitoring Mode", fontsize=12)
    plt.ylabel("Execution Time (seconds)", fontsize=12)
    plt.title("Execution Time by Monitoring Mode (cProfile)", fontsize=14)
    
    # Add grid
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Save the plot
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Plot saved to {output_file}")

def plot_overhead(results, output_file="performance/profile_overhead.png"):
    """Plot the overhead of the different monitoring modes"""
    plt.figure(figsize=(10, 6))
    
    # Calculate the overhead
    baseline_time = results["no_monitoring"]["total_time"]
    names = [name for name in results.keys() if name != "no_monitoring"]
    overheads = [((results[name]["total_time"] - baseline_time) / baseline_time) * 100 
                for name in names]
    
    # Create the bar chart
    bars = plt.bar(names, overheads, color=['#fc8d62', '#8da0cb'])
    
    # Add the values on top of the bars
    for i, bar in enumerate(bars):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                f"{overheads[i]:.1f}%", ha='center', fontsize=10)
    
    # Add labels and title
    plt.xlabel("Monitoring Mode", fontsize=12)
    plt.ylabel("Overhead (%)", fontsize=12)
    plt.title("Monitoring Overhead Relative to No Monitoring (cProfile)", fontsize=14)
    
    # Add grid
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Save the plot
    plt.tight_layout()
    plt.savefig(output_file)
    print(f"Overhead plot saved to {output_file}")

def main():
    # Create the performance directory if it doesn't exist
    os.makedirs("performance", exist_ok=True)
    
    # Number of iterations for each test
    iterations = 50
    
    # Run the profile tests
    results = {
        "no_monitoring": run_profile_test("test_no_monitoring", "no_monitoring", iterations),
        "direct_logging": run_profile_test("test_direct_monitoring", "direct_logging", iterations),
        "offload_logging": run_profile_test("test_offload_monitoring", "offload_logging", iterations)
    }
    
    # Compare the results
    compare_results(results)
    
    # Plot the results
    plot_results(results)
    plot_overhead(results)
    
    # Save the results to a JSON file
    with open("performance/profile_results.json", "w") as f:
        # We can't directly serialize the stats string in a pretty way, so we'll just save the times
        json_results = {name: {"total_time": result["total_time"]} for name, result in results.items()}
        json.dump(json_results, f, indent=2)
    
    print("\nProfile analysis complete!")
    print("Generated files:")
    print("- performance/profile_no_monitoring.txt")
    print("- performance/profile_direct_logging.txt")
    print("- performance/profile_offload_logging.txt")
    print("- performance/profile_comparison.png")
    print("- performance/profile_overhead.png")
    print("- performance/profile_results.json")

if __name__ == "__main__":
    main() 