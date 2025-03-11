#!/usr/bin/env python3
"""
PyMonitor Web Explorer

A web-based interface for exploring PyMonitor databases.
"""

import os
import sys
import argparse
import logging
import json
import datetime
from pathlib import Path
import webbrowser
import threading
import time

try:
    from flask import Flask, render_template, request, jsonify, abort, send_from_directory
    from flask_cors import CORS
except ImportError:
    print("Flask is required for the web explorer. Install it with: pip install flask flask-cors")
    sys.exit(1)

from .models import init_db
from .db_operations import DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__, 
            static_folder=os.path.join(os.path.dirname(__file__), 'static'),
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
CORS(app)

# Global variables
db_manager = None
db_path = None

# Create templates directory if it doesn't exist
template_dir = os.path.join(os.path.dirname(__file__), 'templates')
os.makedirs(template_dir, exist_ok=True)

# Create static directory if it doesn't exist
static_dir = os.path.join(os.path.dirname(__file__), 'static')
os.makedirs(static_dir, exist_ok=True)

# Create HTML template
index_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PyMonitor Database Explorer</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.3/font/bootstrap-icons.css">
    <style>
        body {
            padding-top: 20px;
        }
        .function-card {
            margin-bottom: 15px;
            cursor: pointer;
        }
        .function-card:hover {
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        .detail-card {
            margin-top: 20px;
        }
        pre {
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 5px;
        }
        .nav-tabs {
            margin-bottom: 15px;
        }
        .search-box {
            margin-bottom: 20px;
        }
        .loading {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100px;
        }
        .spinner-border {
            width: 3rem;
            height: 3rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="mb-4">
            <h1 class="display-4">PyMonitor Database Explorer</h1>
            <p class="lead">Exploring database: <span id="db-path" class="fw-bold"></span></p>
        </header>

        <div class="row">
            <div class="col-md-12">
                <div class="card search-box">
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-4">
                                <div class="input-group">
                                    <input type="text" id="search-input" class="form-control" placeholder="Search functions...">
                                    <button class="btn btn-outline-secondary" type="button" id="search-button">
                                        <i class="bi bi-search"></i>
                                    </button>
                                </div>
                            </div>
                            <div class="col-md-4">
                                <select id="file-filter" class="form-select">
                                    <option value="">All Files</option>
                                </select>
                            </div>
                            <div class="col-md-4">
                                <select id="function-filter" class="form-select">
                                    <option value="">All Functions</option>
                                </select>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-5">
                <h2>Function Calls</h2>
                <div id="function-list" class="list-group">
                    <div class="loading">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                    </div>
                </div>
            </div>
            <div class="col-md-7">
                <div id="function-details">
                    <div class="card">
                        <div class="card-body text-center">
                            <h3>Select a function call to view details</h3>
                            <p class="text-muted">Click on any function call from the list to view its details</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Set database path
            fetch('/api/db-info')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('db-path').textContent = data.db_path;
                });

            // Load function calls
            loadFunctionCalls();

            // Set up search
            document.getElementById('search-button').addEventListener('click', function() {
                loadFunctionCalls();
            });

            document.getElementById('search-input').addEventListener('keyup', function(event) {
                if (event.key === 'Enter') {
                    loadFunctionCalls();
                }
            });

            // Set up filters
            document.getElementById('file-filter').addEventListener('change', loadFunctionCalls);
            document.getElementById('function-filter').addEventListener('change', loadFunctionCalls);
        });

        function loadFunctionCalls() {
            const searchTerm = document.getElementById('search-input').value;
            const fileFilter = document.getElementById('file-filter').value;
            const functionFilter = document.getElementById('function-filter').value;
            
            const functionList = document.getElementById('function-list');
            functionList.innerHTML = `
                <div class="loading">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </div>
            `;

            fetch(`/api/function-calls?search=${searchTerm}&file=${fileFilter}&function=${functionFilter}`)
                .then(response => response.json())
                .then(data => {
                    // Update function list
                    functionList.innerHTML = '';
                    
                    if (data.function_calls.length === 0) {
                        functionList.innerHTML = `
                            <div class="card">
                                <div class="card-body text-center">
                                    <p class="text-muted">No function calls found</p>
                                </div>
                            </div>
                        `;
                        return;
                    }

                    // Populate file and function filters if they're empty
                    const fileFilter = document.getElementById('file-filter');
                    const functionFilter = document.getElementById('function-filter');
                    
                    if (fileFilter.options.length <= 1) {
                        const files = [...new Set(data.function_calls.map(call => call.file))];
                        files.sort().forEach(file => {
                            const option = document.createElement('option');
                            option.value = file;
                            option.textContent = file;
                            fileFilter.appendChild(option);
                        });
                    }
                    
                    if (functionFilter.options.length <= 1) {
                        const functions = [...new Set(data.function_calls.map(call => call.function))];
                        functions.sort().forEach(func => {
                            const option = document.createElement('option');
                            option.value = func;
                            option.textContent = func;
                            functionFilter.appendChild(option);
                        });
                    }

                    // Add function calls to the list
                    data.function_calls.forEach(call => {
                        const card = document.createElement('div');
                        card.className = 'card function-card';
                        card.innerHTML = `
                            <div class="card-body">
                                <h5 class="card-title">${call.function}</h5>
                                <h6 class="card-subtitle mb-2 text-muted">${call.file}:${call.line}</h6>
                                <p class="card-text">
                                    <small class="text-muted">
                                        ${new Date(call.start_time).toLocaleString()}
                                        ${call.end_time ? ` - ${new Date(call.end_time).toLocaleString()}` : ''}
                                    </small>
                                </p>
                            </div>
                        `;
                        card.addEventListener('click', () => loadFunctionDetails(call.id));
                        functionList.appendChild(card);
                    });
                })
                .catch(error => {
                    console.error('Error loading function calls:', error);
                    functionList.innerHTML = `
                        <div class="card">
                            <div class="card-body text-center">
                                <p class="text-danger">Error loading function calls</p>
                            </div>
                        </div>
                    `;
                });
        }

        function loadFunctionDetails(functionId) {
            const detailsContainer = document.getElementById('function-details');
            detailsContainer.innerHTML = `
                <div class="loading">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </div>
            `;

            fetch(`/api/function-call/${functionId}`)
                .then(response => response.json())
                .then(data => {
                    const call = data.function_call;
                    const details = data.details;
                    
                    let executionTime = '';
                    if (call.start_time && call.end_time) {
                        const start = new Date(call.start_time);
                        const end = new Date(call.end_time);
                        const diff = end - start;
                        executionTime = `${diff} ms`;
                    }

                    detailsContainer.innerHTML = `
                        <div class="card detail-card">
                            <div class="card-header">
                                <h3>${call.function}</h3>
                                <h6 class="text-muted">${call.file}:${call.line}</h6>
                            </div>
                            <div class="card-body">
                                <div class="row mb-3">
                                    <div class="col-md-6">
                                        <strong>Start Time:</strong> ${new Date(call.start_time).toLocaleString()}
                                    </div>
                                    <div class="col-md-6">
                                        <strong>End Time:</strong> ${call.end_time ? new Date(call.end_time).toLocaleString() : 'N/A'}
                                    </div>
                                </div>
                                <div class="row mb-3">
                                    <div class="col-md-6">
                                        <strong>Execution Time:</strong> ${executionTime || 'N/A'}
                                    </div>
                                    <div class="col-md-6">
                                        <strong>Event Type:</strong> ${call.event_type}
                                    </div>
                                </div>

                                <ul class="nav nav-tabs" id="detailTabs" role="tablist">
                                    <li class="nav-item" role="presentation">
                                        <button class="nav-link active" id="locals-tab" data-bs-toggle="tab" data-bs-target="#locals" type="button" role="tab">Locals</button>
                                    </li>
                                    <li class="nav-item" role="presentation">
                                        <button class="nav-link" id="globals-tab" data-bs-toggle="tab" data-bs-target="#globals" type="button" role="tab">Globals</button>
                                    </li>
                                    <li class="nav-item" role="presentation">
                                        <button class="nav-link" id="return-tab" data-bs-toggle="tab" data-bs-target="#return" type="button" role="tab">Return Value</button>
                                    </li>
                                    ${call.perf_label ? `
                                    <li class="nav-item" role="presentation">
                                        <button class="nav-link" id="perf-tab" data-bs-toggle="tab" data-bs-target="#perf" type="button" role="tab">Performance</button>
                                    </li>
                                    ` : ''}
                                </ul>
                                <div class="tab-content" id="detailTabsContent">
                                    <div class="tab-pane fade show active" id="locals" role="tabpanel">
                                        <pre>${formatObject(details.locals)}</pre>
                                    </div>
                                    <div class="tab-pane fade" id="globals" role="tabpanel">
                                        <pre>${formatObject(details.globals)}</pre>
                                    </div>
                                    <div class="tab-pane fade" id="return" role="tabpanel">
                                        <pre>${formatObject(details.return_value)}</pre>
                                    </div>
                                    ${call.perf_label ? `
                                    <div class="tab-pane fade" id="perf" role="tabpanel">
                                        <div class="card">
                                            <div class="card-body">
                                                <h5 class="card-title">${call.perf_label || 'Performance'}</h5>
                                                <div class="row">
                                                    <div class="col-md-6">
                                                        <strong>Package Energy:</strong> ${call.perf_pkg !== null ? call.perf_pkg + ' μJ' : 'N/A'}
                                                    </div>
                                                    <div class="col-md-6">
                                                        <strong>DRAM Energy:</strong> ${call.perf_dram !== null ? call.perf_dram + ' μJ' : 'N/A'}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    ` : ''}
                                </div>
                            </div>
                        </div>
                    `;
                })
                .catch(error => {
                    console.error('Error loading function details:', error);
                    detailsContainer.innerHTML = `
                        <div class="card">
                            <div class="card-body text-center">
                                <p class="text-danger">Error loading function details</p>
                            </div>
                        </div>
                    `;
                });
        }

        function formatObject(obj) {
            if (obj === null || obj === undefined) {
                return 'None';
            }
            return JSON.stringify(obj, null, 2);
        }
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# Write the HTML template to the templates directory
with open(os.path.join(template_dir, 'index.html'), 'w') as f:
    f.write(index_html)

# JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects and custom objects"""
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        elif hasattr(obj, '__dict__'):
            # For custom objects, convert to a dictionary of attributes
            result = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):  # Skip private attributes
                    try:
                        # Try to make the value JSON serializable
                        json.dumps({key: value}, cls=DateTimeEncoder)
                        result[key] = value
                    except (TypeError, OverflowError):
                        # If the value can't be serialized, use its string representation
                        result[key] = str(value)
            
            # Add the class name as a special attribute
            result['__class__'] = obj.__class__.__name__
            return result
        return str(obj)

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/db-info')
def db_info():
    """Return information about the database"""
    global db_path
    if not db_path:
        abort(500, description="Database path not set")
        
    return jsonify({
        'db_path': db_path
    })

@app.route('/api/function-calls')
def get_function_calls():
    """Return all function calls with optional filtering"""
    global db_manager
    if not db_manager:
        abort(500, description="Database manager not initialized")
        
    # Get query parameters
    search = request.args.get('search', '')
    file_filter = request.args.get('file', '')
    function_filter = request.args.get('function', '')
    
    # Get all function calls
    function_calls = db_manager.get_all_function_calls()
    
    # Filter function calls
    filtered_calls = []
    for call in function_calls:
        # Apply search filter
        if search and search.lower() not in call.function.lower() and search.lower() not in call.file.lower():
            continue
        
        # Apply file filter
        if file_filter and file_filter != call.file:
            continue
        
        # Apply function filter
        if function_filter and function_filter != call.function:
            continue
        
        filtered_calls.append(call)
    
    # Sort by start time (most recent first)
    filtered_calls.sort(key=lambda x: x.start_time, reverse=True)
    
    # Convert to list of dictionaries
    result = []
    for call in filtered_calls:
        result.append({
            'id': call.id,
            'event_type': call.event_type,
            'file': call.file,
            'function': call.function,
            'line': call.line,
            'start_time': call.start_time,
            'end_time': call.end_time,
            'perf_label': call.perf_label,
            'perf_pkg': call.perf_pkg,
            'perf_dram': call.perf_dram
        })
    
    # Use the DateTimeEncoder to handle custom objects
    return app.response_class(
        response=json.dumps({
            'function_calls': result
        }, cls=DateTimeEncoder),
        status=200,
        mimetype='application/json'
    )

@app.route('/api/function-call/<function_id>')
def get_function_call(function_id):
    """Return details for a specific function call"""
    global db_manager
    if not db_manager:
        abort(500, description="Database manager not initialized")
        
    function_calls = db_manager.get_all_function_calls()
    
    # Find the function call
    function_call = None
    for call in function_calls:
        if call.id == function_id:
            function_call = call
            break
    
    if not function_call:
        abort(404)
    
    # Get the function call data
    details = db_manager.get_function_call_data(function_id)
    
    # Convert function call to dictionary
    call_dict = {
        'id': function_call.id,
        'event_type': function_call.event_type,
        'file': function_call.file,
        'function': function_call.function,
        'line': function_call.line,
        'start_time': function_call.start_time,
        'end_time': function_call.end_time,
        'perf_label': function_call.perf_label,
        'perf_pkg': function_call.perf_pkg,
        'perf_dram': function_call.perf_dram
    }
    
    # Use the DateTimeEncoder to handle custom objects
    return app.response_class(
        response=json.dumps({
            'function_call': call_dict,
            'details': details
        }, cls=DateTimeEncoder),
        status=200,
        mimetype='application/json'
    )

def open_browser(url):
    """Open the browser after a short delay"""
    time.sleep(1.5)
    webbrowser.open(url)

def run_explorer(db_file, host='127.0.0.1', port=5000, debug=False, open_browser_flag=True):
    """Run the web explorer"""
    global db_manager, db_path
    
    # Ensure we have an absolute path
    db_path = os.path.abspath(db_file)
    
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        sys.exit(1)
    
    # Initialize the database
    try:
        Session = init_db(db_path)
        db_manager = DatabaseManager(Session)
        logger.info(f"Successfully connected to database: {db_path}")
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        sys.exit(1)
    
    # Open browser automatically if requested
    if open_browser_flag:
        url = f"http://{host}:{port}/"
        threading.Thread(target=open_browser, args=(url,)).start()
    
    # Run the Flask app
    logger.info(f"Starting web explorer at http://{host}:{port}/")
    app.run(host=host, port=port, debug=debug)

def main():
    """Command-line entry point"""
    parser = argparse.ArgumentParser(description="PyMonitor Web Explorer")
    parser.add_argument("db_path", help="Path to the database file to explore")
    parser.add_argument("--host", default="127.0.0.1", help="Host to run the server on (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the server on (default: 5000)")
    parser.add_argument("--no-browser", action="store_true", help="Don't open the browser automatically")
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    
    args = parser.parse_args()
    
    run_explorer(
        args.db_path, 
        host=args.host, 
        port=args.port, 
        debug=args.debug, 
        open_browser_flag=not args.no_browser
    )

if __name__ == "__main__":
    main()

# Module entry point
def __main__():
    """Entry point for running as a module"""
    main() 