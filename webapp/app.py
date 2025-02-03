import collections.abc
from datetime import datetime
import io
import json
from itertools import islice
from typing import Any
from flask import Flask, request, render_template_string, jsonify
import jsonpickle
from search import binary_search
import monitor
from collections import defaultdict
import os

app = Flask(__name__)
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.jsonl')

def read_executions():
    executions = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            for line in f:
                try:
                    executions.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
    return executions

executions : dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

def process_execution():
    all_executions = read_executions()
    # Group by execution_id
    waiting = {}
    for execution in all_executions:
        if execution.get('event_type') == "call":
            waiting[execution.get('execution_id')] = execution
        elif execution.get('event_type') == "return":
            if execution.get('execution_id') in waiting:
                caller = waiting[execution.get('execution_id')]
                executions[caller.get('file')][caller.get('function')].append({
                    "line": caller.get('line'),
                    "locals": caller.get('locals'),
                    "return": execution.get('return_value'),
                    "timestamp": execution.get('timestamp'),
                    "exec_time": (datetime.fromisoformat(execution.get('timestamp')) - datetime.fromisoformat(caller.get('timestamp'))).total_seconds(),
                })
        else:
            raise ValueError(f"Unknown event type: {execution.get('event_type')}")
        
process_execution()


@app.route('/', methods=['GET', 'POST'])
def index():
    if request is not None and isinstance(request, collections.abc.Iterable):
        print(jsonpickle.encode(request.__dict__))
    else:
        print("not iter", request)
    html_form = """
    <html>
      <body>
        <h2>Enter an ordered list (comma-separated) and a key to search :</h2>
        <form method="POST">
          <label for="arr">Ordered List (e.g. 1,2,3,4):</label><br>
          <input type="text" id="arr" name="arr" required><br><br>
          <label for="key">Key to Search:</label><br>
          <input type="text" id="key" name="key" required><br><br>
          <input type="submit" value="Search">
        </form>
      </body>
    </html>
    """

    if request.method == 'POST':
        # Retrieve data from the form
        arr_str = request.form.get('arr', '')
        key_str = request.form.get('key', '')

        # Convert arr_str into a list of integers
        try:
            arr = [int(x.strip()) for x in arr_str.split(',')]
        except ValueError:
            return "Invalid list input, please enter integers separated by commas."

        # Convert the key to integer
        try:
            key = int(key_str)
        except ValueError:
            return "Invalid key input, please enter a valid integer."

        # Call the binary search function
        found = binary_search(arr, key)

        # Display result
        html_result = f"""
        <html>
          <body>
            <h3>Array: {arr}</h3>
            <h3>Key: {key}</h3>
            <h3>Found? {found}</h3>
            <a href="/">Go Back</a>
          </body>
        </html>
        """
        return render_template_string(html_result)

    # If it's a GET request, just show the form
    return render_template_string(html_form)

@app.route('/api/functions', methods=['GET'])
def get_functions():
    file_path = request.args.get('filePath')
    if file_path in executions:
        functions = []
        for func_name, exec_list in executions[file_path].items():
            line_counts = {}
            for element in exec_list:
                line_counts[element['line']] = line_counts.get(element['line'], 0) + 1
            for line, count in line_counts.items():
                functions.append({"name": func_name, "line": line, "count": count})
        return jsonify(functions)
    return jsonify([])

@app.route('/api/executions', methods=['GET'])
def get_executions():
    file_path = request.args.get('filePath')
    function_name = request.args.get('functionName')
    line_number = request.args.get('line', type=int)
    
    filtered = []
    if file_path in executions:
        for func, exe_list in executions[file_path].items():
            if function_name and func != function_name:
                continue
            for element in exe_list:
                if line_number and element['line'] != line_number:
                    continue
                filtered.append({
                    "functionName": func,
                    "args": element['locals'],
                    "return": element['return'],
                    "line": element['line'],
                    "timestamp": element['timestamp'],
                    "exec_time": element['exec_time']
                })
    
    return jsonify(filtered)


if __name__ == "__main__":
    app.run(debug=True, port=5000)  # Explicit port for easier testing 