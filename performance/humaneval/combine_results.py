#!/usr/bin/env python3
"""
Script to combine individual HumanEval results into a unified JSON file.
This allows you to check results while the benchmark is still running.
"""

import os
import json
from pathlib import Path

current_path = Path(__file__).parent
results_path = current_path / "individual_results"

def collect_all_results():
    """Collect all individual results into a single list."""
    if not results_path.exists():
        print("No individual results directory found. Run the benchmark first.")
        return []
    
    all_results = []
    missing_results = []
    
    for i in range(164):
        result_file = results_path / f"result_{i}.json"
        if result_file.exists():
            try:
                with open(result_file, 'r') as f:
                    result = json.load(f)
                    all_results.append(result)
            except json.JSONDecodeError as e:
                print(f"Error reading result_{i}.json: {e}")
                missing_results.append(i)
        else:
            missing_results.append(i)
    
    if missing_results:
        print(f"Missing results for {len(missing_results)} problems: {missing_results[:20]}{'...' if len(missing_results) > 20 else ''}")
    
    return all_results

def analyze_results(results):
    """Analyze the current results and print summary."""
    if not results:
        print("No results to analyze.")
        return
    
    total_problems = len(results)
    
    # Count successes and failures
    ref_success = sum(1 for r in results if r.get('reference', {}).get('success', False))
    mon_success = sum(1 for r in results if r.get('monitored', {}).get('success', False))
    
    # Count timeouts
    ref_timeout = sum(1 for r in results if r.get('reference', {}).get('timeout', False))
    mon_timeout = sum(1 for r in results if r.get('monitored', {}).get('timeout', False))
    
    # Count errors
    ref_errors = sum(1 for r in results if 'error' in r.get('reference', {}))
    mon_errors = sum(1 for r in results if 'error' in r.get('monitored', {}))
    file_errors = sum(1 for r in results if 'error' in r)
    
    # Calculate averages for successful runs
    successful_results = [r for r in results if 
                         r.get('reference', {}).get('success', False) and 
                         r.get('monitored', {}).get('success', False)]
    
    if successful_results:
        avg_ref_time = sum(r['reference']['wall_time'] for r in successful_results) / len(successful_results)
        avg_mon_time = sum(r['monitored']['wall_time'] for r in successful_results) / len(successful_results)
        avg_overhead = avg_mon_time / avg_ref_time if avg_ref_time > 0 else 0
        
        avg_db_size = sum(r['monitored'].get('db_size_bytes', 0) for r in successful_results) / len(successful_results)
        total_db_size = sum(r['monitored'].get('db_size_bytes', 0) for r in successful_results)
    else:
        avg_ref_time = avg_mon_time = avg_overhead = avg_db_size = total_db_size = 0
    
    print("=" * 60)
    print("CURRENT RESULTS SUMMARY")
    print("=" * 60)
    print(f"Total problems processed: {total_problems}/164 ({total_problems/164*100:.1f}%)")
    print(f"Remaining problems: {164 - total_problems}")
    print()
    
    print("SUCCESS RATES:")
    print(f"  Reference successful: {ref_success}/{total_problems} ({ref_success/total_problems*100:.1f}%)")
    print(f"  Monitored successful: {mon_success}/{total_problems} ({mon_success/total_problems*100:.1f}%)")
    print(f"  Both successful: {len(successful_results)}/{total_problems} ({len(successful_results)/total_problems*100:.1f}%)")
    print()
    
    print("TIMEOUTS:")
    print(f"  Reference timeouts: {ref_timeout}")
    print(f"  Monitored timeouts: {mon_timeout}")
    print()
    
    print("ERRORS:")
    print(f"  File errors: {file_errors}")
    print(f"  Reference errors: {ref_errors}")
    print(f"  Monitored errors: {mon_errors}")
    print()
    
    if successful_results:
        print("PERFORMANCE (successful runs only):")
        print(f"  Average reference time: {avg_ref_time:.4f}s")
        print(f"  Average monitored time: {avg_mon_time:.4f}s")
        print(f"  Average overhead: {avg_overhead:.2f}x")
        print(f"  Average database size: {avg_db_size:.0f} bytes")
        print(f"  Total database size: {total_db_size:.0f} bytes")
        print()
    
    # Show recent completions
    recent_results = sorted(results, key=lambda x: x['problem_index'])[-10:]
    recent_indexes = [r['problem_index'] for r in recent_results]
    print(f"Recent completions: {recent_indexes}")

def save_combined_results(results, filename="humaneval_performance_results.json"):
    """Save combined results to a JSON file."""
    if not results:
        print("No results to save.")
        return
    
    output_path = current_path / filename
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"Combined results saved to {output_path}")
    print(f"Total problems in file: {len(results)}")

def main():
    """Main function to combine results and show analysis."""
    print("Combining HumanEval individual results...")
    
    # Collect all results
    results = collect_all_results()
    
    if not results:
        print("No results found. Make sure the benchmark has been run.")
        return
    
    # Analyze current results
    analyze_results(results)
    
    # Save combined results
    save_combined_results(results)
    
    print("\nTo continue monitoring progress, run this script again.")
    print("To see detailed analysis, run 'python analyze_results.py' once you have enough results.")

if __name__ == "__main__":
    main() 