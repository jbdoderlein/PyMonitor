import json
import os
import resource
import signal
import subprocess
import time
from multiprocessing import Pool

current_path = os.path.dirname(os.path.abspath(__file__))
humaneval_data_path = os.path.join(current_path, "humaneval_data")
reference_path = os.path.join(humaneval_data_path, "reference")
monitoring_line_path = os.path.join(humaneval_data_path, "monitoring_line")
monitoring_function_path = os.path.join(humaneval_data_path, "monitoring_function")
results_path = os.path.join(current_path, "individual_results")

# Create results directory
os.makedirs(results_path, exist_ok=True)

# Default timeout in seconds (3 minutes)
DEFAULT_TIMEOUT = 180

def run_single_problem(problem_index, timeout=DEFAULT_TIMEOUT):
    """
    Run a single HumanEval problem, both reference and monitored versions.
    Returns a dictionary with performance metrics and saves result immediately.
    """
    result_file = os.path.join(results_path, f"result_{problem_index}.json")

    # Check if already completed
    if os.path.exists(result_file):
        with open(result_file) as f:

            data = json.load(f)
            if data['reference']['timeout'] or data['monitored_line']['timeout'] or data['monitored_function']['timeout']:
                print(f"Problem {problem_index} timed out, going to rerun...")
                os.remove(result_file)
            else:
                print(f"Problem {problem_index} already completed, skipping...")
                return data

    results = {
        'problem_index': problem_index,
        'reference': {},
        'monitored_line': {},
        'monitored_function': {},
        'timeout_limit': timeout
    }

    reference_file = os.path.join(reference_path, f"{problem_index}.py")
    monitoring_line_file = os.path.join(monitoring_line_path, f"{problem_index}.py")
    monitoring_function_file = os.path.join(monitoring_function_path, f"{problem_index}.py")

    # Check if files exist
    if not os.path.exists(reference_file):
        results['error'] = f"Reference file {reference_file} not found"
        save_individual_result(results, problem_index)
        return results

    if not os.path.exists(monitoring_line_file):
        results['error'] = f"Monitoring file {monitoring_line_file} not found"
        save_individual_result(results, problem_index)
        return results

    if not os.path.exists(monitoring_function_file):
        results['error'] = f"Monitoring file {monitoring_function_file} not found"
        save_individual_result(results, problem_index)
        return results

    print(f"Running problem {problem_index} (timeout: {timeout}s)...")

    # Run reference version
    try:
        results['reference'] = run_python_file(reference_file, reference_path, timeout)
    except Exception as e:
        results['reference']['error'] = str(e)

    # Run monitored version
    try:
        results['monitored_line'] = run_python_file(monitoring_line_file, monitoring_line_path, timeout)
        results['monitored_function'] = run_python_file(monitoring_function_file, monitoring_function_path, timeout)
    except Exception as e:
        results['monitored_line']['error'] = str(e)
        results['monitored_function']['error'] = str(e)

    # Save individual result immediately
    save_individual_result(results, problem_index)

    return results

def run_with_timeout(args):
    """Wrapper for multiprocessing with timeout."""
    problem_index, timeout = args
    return run_single_problem(problem_index, timeout)

def save_individual_result(result, problem_index):
    """Save individual result to a JSON file."""
    result_file = os.path.join(results_path, f"result_{problem_index}.json")
    with  open(result_file, 'w') as f:
        json.dump(result, f, indent=2)

def get_completed_problems():
    """Get list of already completed problems."""
    completed = []
    for i in range(164):
        result_file = os.path.join(results_path, f"result_{i}.json")
        if os.path.exists(result_file):
            completed.append(i)
    return completed

def get_remaining_problems():
    """Get list of problems that still need to be run."""
    completed = get_completed_problems()
    return [i for i in range(164) if i not in completed]


def get_timed_out_problems():
    """Get list of problems that timed out."""
    timed_out = []
    for i in range(164):
        result_file = os.path.join(results_path, f"result_{i}.json")
        if os.path.exists(result_file):
            with open(result_file) as f:
                result = json.load(f)
                # Check if either version timed out
                if (result.get('reference', {}).get('timeout', False) or
                    result.get('monitored_line', {}).get('timeout', False) or
                    result.get('monitored_function', {}).get('timeout', False)):
                    timed_out.append(i)
    return timed_out

def run_python_file(file_path, working_dir, timeout=DEFAULT_TIMEOUT):
    """
    Run a Python file with timeout and measure its performance.
    Returns a dictionary with timing and resource usage information.
    """
    # Get initial resource usage
    start_resources = resource.getrusage(resource.RUSAGE_CHILDREN)
    start_time = time.time()

    # Run the Python file with timeout
    try:
        process = subprocess.Popen(
            ['python', file_path],
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid  # Create new process group for cleanup
        )

        # Wait for process with timeout
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            # Kill the process group to clean up any child processes
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                stdout, stderr = process.communicate()
            timed_out = True

    except Exception as e:
        return {'error': f'Failed to run process: {str(e)}'}

    end_time = time.time()

    # Get final resource usage
    end_resources = resource.getrusage(resource.RUSAGE_CHILDREN)

    # Calculate differences
    wall_time = end_time - start_time
    user_time = end_resources.ru_utime - start_resources.ru_utime
    system_time = end_resources.ru_stime - start_resources.ru_stime
    max_memory = end_resources.ru_maxrss - start_resources.ru_maxrss

    try:
        internal_time = eval(stdout)
    except Exception as e:
        print("ERROR: ", e)
        internal_time = None

    if os.path.exists(str(file_path)[:-2] + "db"):
        db_size = os.path.getsize(str(file_path)[:-2] + "db")
    else:
        db_size = 0


    result = {
        'wall_time': wall_time,
        'user_time': user_time,
        'system_time': system_time,
        'max_memory_kb': max_memory,
        'return_code': process.returncode,
        'stdout': stdout,
        'stderr': stderr,
        'timeout': timed_out,
        'timeout_limit': timeout,
        'internal_time': internal_time,
        'db_size_bytes': db_size
    }

    # Set success based on return code and timeout
    if timed_out:
        result['success'] = False
        result['timeout_message'] = f"Process timed out after {timeout} seconds"
    else:
        result['success'] = process.returncode == 0

    return result

def run_all_problems_parallel(num_processes=os.cpu_count(), timeout=DEFAULT_TIMEOUT):
    """Run all problems in parallel using multiprocessing."""
    remaining = get_remaining_problems()
    completed = get_completed_problems()
    timed_out = get_timed_out_problems()

    print(f"Already completed: {len(completed)}/164 problems")
    print(f"Remaining to run: {len(remaining)} problems")
    print(f"Timed out: {len(timed_out)} problems")

    if not remaining and not timed_out:
        print("All problems already completed!")
        return
    todo = list(set(remaining).union(set(timed_out)))
    # Create argument tuples for multiprocessing
    args = [(i, timeout) for i in todo]

    with Pool(processes=num_processes) as pool:
        results = pool.map(run_with_timeout, args)

    # Count timeouts
    timeout_count = sum(1 for r in results if r.get('reference', {}).get('timeout', False) or r.get('monitored', {}).get('timeout', False))
    if timeout_count > 0:
        print(f"Warning: {timeout_count} problems timed out!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Run HumanEval performance benchmark')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT,
                        help=f'Timeout in seconds (default: {DEFAULT_TIMEOUT})')
    parser.add_argument('--processes', type=int, default=8,
                        help='Number of parallel processes (default: 8)')

    args = parser.parse_args()

    print("Starting HumanEval performance benchmark...")
    print(f"Reference path: {reference_path}")
    print(f"Monitoring line path: {monitoring_line_path}")
    print(f"Monitoring function path: {monitoring_function_path}")
    print(f"Results path: {results_path}")
    print(f"Timeout: {args.timeout} seconds")


    print(f"\nRunning remaining problems in parallel (timeout: {args.timeout}s, processes: {args.processes})...")
    run_all_problems_parallel(num_processes=args.processes, timeout=args.timeout)


    print("\nRun 'python combine_results.py' to combine all results into final JSON file.")
    print("Or use 'python utils.py combine' to combine results.")
