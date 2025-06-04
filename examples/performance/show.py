#!/usr/bin/env python3
import json
import matplotlib.pyplot as plt
import os
import sys

def load_performance_data(filename):
    """Load performance data from JSON file."""
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            return data['times'], data.get('db_size', 0)
    except FileNotFoundError:
        print(f"Warning: {filename} not found")
        return None, None
    except json.JSONDecodeError:
        print(f"Error: Could not parse {filename}")
        return None, None

def plot_performance_data():
    """Plot performance data from all available JSON files."""
    
    # Define the performance files to check
    perf_files = [
        ('perf.json', 'Basic Performance', 'blue'),
        ('perf_function.json', 'Function-level Performance', 'red'),
        ('perf_line.json', 'Line-level Performance', 'green')
    ]
    
    # Create figure with subplots
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('Performance Analysis - Execution Time vs Index', fontsize=16, fontweight='bold')
    
    # Flatten axes for easier indexing
    axes_flat = axes.flatten()
    
    valid_data = []
    
    # Load and plot each dataset
    for i, (filename, label, color) in enumerate(perf_files):
        times, db_size = load_performance_data(filename)
        
        if times is not None:
            valid_data.append((times, label, color, db_size))
            
            # Plot individual dataset
            axes_flat[i].plot(range(len(times)), times, 'o-', color=color, markersize=3, linewidth=1.5, alpha=0.7)
            axes_flat[i].set_title(f'{label}\n(DB Size: {db_size/1024:.1f} KB)' if db_size else label)
            axes_flat[i].set_xlabel('Index')
            axes_flat[i].set_ylabel('Time (seconds)')
            axes_flat[i].grid(True, alpha=0.3)
            
            # Add statistics
            avg_time = sum(times) / len(times)
            max_time = max(times)
            min_time = min(times)
            axes_flat[i].text(0.02, 0.98, f'Avg: {avg_time:.2e}s\nMax: {max_time:.2e}s\nMin: {min_time:.2e}s', 
                             transform=axes_flat[i].transAxes, verticalalignment='top',
                             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    # Combined plot in the last subplot
    if valid_data:
        axes_flat[3].set_title('Combined Performance Comparison')
        axes_flat[3].set_xlabel('Index')
        axes_flat[3].set_ylabel('Time (seconds)')
        axes_flat[3].grid(True, alpha=0.3)
        
        for times, label, color, db_size in valid_data:
            axes_flat[3].plot(range(len(times)), times, 'o-', color=color, markersize=2, 
                             linewidth=1, alpha=0.7, label=label)
        
        axes_flat[3].legend()
        axes_flat[3].set_yscale('log')  # Log scale for better comparison
    else:
        axes_flat[3].text(0.5, 0.5, 'No valid data found', 
                         transform=axes_flat[3].transAxes, ha='center', va='center')
        axes_flat[3].set_title('No Data Available')
    
    # Hide unused subplots
    for i in range(len(valid_data), 3):
        axes_flat[i].set_visible(False)
    
    plt.tight_layout()
    plt.show()

def print_summary():
    """Print a summary of available performance data."""
    print("Performance Data Summary")
    print("=" * 40)
    
    perf_files = [
        ('perf.json', 'Basic Performance'),
        ('perf_function.json', 'Function-level Performance'),
        ('perf_line.json', 'Line-level Performance')
    ]
    
    for filename, description in perf_files:
        times, db_size = load_performance_data(filename)
        if times is not None:
            print(f"\n{description}:")
            print(f"  File: {filename}")
            print(f"  Data points: {len(times)}")
            print(f"  DB size: {db_size/1024:.1f} KB" if db_size else "  DB size: N/A")
            print(f"  Time range: {min(times):.2e}s - {max(times):.2e}s")
            print(f"  Average time: {sum(times)/len(times):.2e}s")
        else:
            print(f"\n{description}: No data available")

if __name__ == "__main__":
    print("Performance Visualization Tool")
    print("=" * 40)
    
    # Check if we should just print summary
    if len(sys.argv) > 1 and sys.argv[1] == '--summary':
        print_summary()
    else:
        print("Loading performance data and creating plots...")
        print_summary()
        print("\nGenerating plots...")
        plot_performance_data()
