import os
import json
from pathlib import Path

# Paths
current_path = Path(__file__).parent
results_path = current_path / "individual_results"

def check_progress():
    """Check and display current progress."""
    if not results_path.exists():
        print("No results directory found. Run the benchmark first.")
        return
    
    completed = []
    errors = []
    timeouts = []
    
    for i in range(164):
        result_file = results_path / f"result_{i}.json"
        if result_file.exists():
            completed.append(i)
            
            # Check for errors and timeouts
            with open(result_file, 'r') as f:
                result = json.load(f)
                if 'error' in result:
                    errors.append((i, result['error']))
                
                # Check for timeouts
                if (result.get('reference', {}).get('timeout', False) or 
                    result.get('monitored', {}).get('timeout', False)):
                    timeouts.append(i)
    
    remaining = [i for i in range(164) if i not in completed]
    
    print(f"=== PROGRESS STATUS ===")
    print(f"Completed: {len(completed)}/164 problems ({len(completed)/164*100:.1f}%)")
    print(f"Remaining: {len(remaining)} problems")
    print(f"Errors: {len(errors)} problems")
    print(f"Timeouts: {len(timeouts)} problems")
    
    if remaining:
        print(f"\nRemaining problems: {remaining[:20]}{'...' if len(remaining) > 20 else ''}")
    
    if timeouts:
        print(f"\nTimed out problems: {timeouts[:20]}{'...' if len(timeouts) > 20 else ''}")
    
    if errors:
        print(f"\nProblems with errors:")
        for prob_idx, error in errors[:10]:
            print(f"  Problem {prob_idx}: {error[:80]}{'...' if len(error) > 80 else ''}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")

def combine_results():
    """Manually combine all individual results into final JSON."""
    if not results_path.exists():
        print("No results directory found.")
        return
    
    all_results = []
    missing_results = []
    
    for i in range(164):
        result_file = results_path / f"result_{i}.json"
        if result_file.exists():
            with open(result_file, 'r') as f:
                result = json.load(f)
                all_results.append(result)
        else:
            missing_results.append(i)
    
    if missing_results:
        print(f"Warning: Missing results for problems: {missing_results}")
    
    # Save combined results
    output_path = current_path / "humaneval_performance_results.json"
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"Combined {len(all_results)} results into {output_path}")
    
    # Print summary
    successful_ref = sum(1 for r in all_results if r.get('reference', {}).get('success', False))
    successful_mon = sum(1 for r in all_results if r.get('monitored', {}).get('success', False))
    
    print(f"\nSummary:")
    print(f"Reference versions successful: {successful_ref}/{len(all_results)}")
    print(f"Monitored versions successful: {successful_mon}/{len(all_results)}")

def clean_individual_results():
    """Clean up individual result files."""
    import shutil
    if results_path.exists():
        shutil.rmtree(results_path)
        print("Individual result files cleaned up.")
    else:
        print("No individual results directory found.")

def show_detailed_errors():
    """Show detailed error information."""
    if not results_path.exists():
        print("No results directory found.")
        return
    
    ref_errors = []
    mon_errors = []
    file_errors = []
    
    for i in range(164):
        result_file = results_path / f"result_{i}.json"
        if result_file.exists():
            with open(result_file, 'r') as f:
                result = json.load(f)
                
                if 'error' in result:
                    file_errors.append((i, result['error']))
                
                if 'error' in result.get('reference', {}):
                    ref_errors.append((i, result['reference']['error']))
                
                if 'error' in result.get('monitored', {}):
                    mon_errors.append((i, result['monitored']['error']))
    
    print(f"=== DETAILED ERROR ANALYSIS ===")
    print(f"File errors: {len(file_errors)}")
    print(f"Reference errors: {len(ref_errors)}")
    print(f"Monitored errors: {len(mon_errors)}")
    
    if file_errors:
        print(f"\nFile Errors:")
        for prob_idx, error in file_errors:
            print(f"  Problem {prob_idx}: {error}")
    
    if ref_errors:
        print(f"\nReference Errors:")
        for prob_idx, error in ref_errors[:5]:
            print(f"  Problem {prob_idx}: {error}")
        if len(ref_errors) > 5:
            print(f"  ... and {len(ref_errors) - 5} more")
    
    if mon_errors:
        print(f"\nMonitored Errors:")
        for prob_idx, error in mon_errors[:5]:
            print(f"  Problem {prob_idx}: {error}")
        if len(mon_errors) > 5:
            print(f"  ... and {len(mon_errors) - 5} more")

def restart_failed_problems():
    """Remove result files for failed problems so they can be re-run."""
    if not results_path.exists():
        print("No results directory found.")
        return
    
    failed_problems = []
    
    for i in range(164):
        result_file = results_path / f"result_{i}.json"
        if result_file.exists():
            with open(result_file, 'r') as f:
                result = json.load(f)
                
                # Check if either version failed or has errors
                ref_failed = not result.get('reference', {}).get('success', False)
                mon_failed = not result.get('monitored', {}).get('success', False)
                has_errors = ('error' in result or 
                             'error' in result.get('reference', {}) or 
                             'error' in result.get('monitored', {}))
                
                if ref_failed or mon_failed or has_errors:
                    failed_problems.append(i)
                    result_file.unlink()
    
    print(f"Removed {len(failed_problems)} failed problem results: {failed_problems}")
    print("These problems will be re-run on next execution.")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python utils.py <command>")
        print("Commands:")
        print("  progress     - Show current progress")
        print("  combine      - Combine individual results into final JSON")
        print("  clean        - Clean up individual result files")
        print("  errors       - Show detailed error information")
        print("  restart      - Restart failed problems")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "progress":
        check_progress()
    elif command == "combine":
        combine_results()
    elif command == "clean":
        clean_individual_results()
    elif command == "errors":
        show_detailed_errors()
    elif command == "restart":
        restart_failed_problems()
    else:
        print(f"Unknown command: {command}")
        sys.exit(1) 