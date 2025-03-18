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
from .reanimator import Reanimator  # Import the reanimator

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
reanimator = None  # Add reanimator instance

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
        /* Add styles for collapsible objects */
        .collapsible {
            cursor: pointer;
            padding: 2px 5px;
            background-color: #f1f1f1;
            border-radius: 3px;
            display: inline-block;
            margin: 2px 0;
        }
        .collapsible:hover {
            background-color: #e9e9e9;
        }
        .collapsible-content {
            display: none;
            padding-left: 20px;
            overflow: hidden;
        }
        .object-type {
            color: #6c757d;
            font-size: 0.9em;
        }
        .object-key {
            color: #0d6efd;
            font-weight: bold;
        }
        .object-value {
            color: #198754;
        }
        .primitive-value {
            color: #333;
        }
        .string-value {
            color: #664d03;
        }
        .null-value {
            color: #6c757d;
            font-style: italic;
        }
        .top-level-container {
            background-color: #f8f9fa;
            border-radius: 5px;
            padding: 10px;
        }
        .reanimation-note {
            background-color: #cff4fc;
            color: #055160;
            padding: 5px 10px;
            border-radius: 4px;
            margin: 5px 0;
            font-size: 0.9em;
            border-left: 4px solid #0dcaf0;
        }
        .raw-data-note {
            background-color: #fff3cd;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 10px;
            font-family: monospace;
        }
        .raw-data-note pre {
            margin: 5px 0 0 0;
            background-color: #fffbf0;
            padding: 8px;
            border-radius: 3px;
            border-left: 3px solid #ffc107;
            max-height: 200px;
            overflow-y: auto;
        }
        .api-hint {
            font-family: monospace;
            background-color: #f8f9fa;
            padding: 2px 4px;
            border-radius: 3px;
            font-size: 0.9em;
        }
        /* Add styles for the debug modal and nested list display */
        .json-display {
            background-color: #f8f9fa;
            padding: 10px;
            border-radius: 4px;
            white-space: pre-wrap;
            max-height: 500px;
            overflow-y: auto;
        }
        
        .reanimation-note {
            background-color: #e2f0ff;
            padding: 10px;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        
        .api-hint {
            font-family: monospace;
            background-color: #f8f9fa;
            padding: 2px 4px;
            border-radius: 2px;
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

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
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
                        card.dataset.functionId = call.id;
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
            
            // Store the function ID in a data attribute for later use
            detailsContainer.dataset.functionId = functionId;
            
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
                                        <div id="locals-content" class="mt-3">
                                            ${formatObjectPretty(details.locals, 'locals', true)}
                                        </div>
                                    </div>
                                    <div class="tab-pane fade" id="globals" role="tabpanel">
                                        <div id="globals-content" class="mt-3">
                                            ${formatObjectPretty(details.globals, 'globals', true)}
                                        </div>
                                    </div>
                                    <div class="tab-pane fade" id="return" role="tabpanel">
                                        <div id="return-content" class="mt-3">
                                            ${formatObjectPretty(details.return_value, 'return', true)}
                                        </div>
                                    </div>
                                    ${call.perf_label ? `
                                    <div class="tab-pane fade" id="perf" role="tabpanel">
                                        <div class="card mt-3">
                                            <div class="card-body">
                                                <h5 class="card-title">${call.perf_label || 'Performance'}</h5>
                                                <div class="row">
                                                    <div class="col-md-6">
                                                        <strong>Package Energy:</strong> ${call.perf_pkg !== null ? call.perf_pkg + ' μJ' : 'N/A'}
                                                    </div>
                                                    <div class="col-md-6">
                                                        <strong>DRAM Energy:</strong> ${call.perf_dram !== null ? call.perf_dram + ' seconds' : 'N/A'}
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
                    
                    // Restore the function ID in the data attribute (it was overwritten by innerHTML)
                    detailsContainer.dataset.functionId = functionId;
                    
                    // Set up collapsible sections after rendering
                    setupCollapsibles();
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

        function formatObjectPretty(obj, prefix = '', isTopLevel = false) {
            if (obj === null || obj === undefined) {
                return '<span class="null-value">null</span>';
            }
            
            // Handle nested list structures
            if (obj && typeof obj === 'object' && obj._nested_list) {
                const note = obj._nested_structure || "Nested list structure";
                
                // Extract the function ID properly - we need to get the actual function ID
                // The prefix format is typically 'functionId_variableName'
                // For tabs like 'locals', 'globals', etc., we need to get the actual function ID from the URL
                let functionId;
                
                // Get the function ID from the URL if we're in a function details view
                const urlParams = new URLSearchParams(window.location.search);
                const pathParts = window.location.pathname.split('/');
                const urlFunctionId = pathParts[pathParts.length - 1] || '';
                
                // If we have a function ID in the URL, use that
                if (urlFunctionId && urlFunctionId !== '') {
                    functionId = urlFunctionId;
                } else {
                    // Otherwise, try to extract it from the prefix
                    functionId = prefix.split('_')[0];
                    // Remove any trailing text with spaces
                    functionId = functionId.split(' ')[0];
                }
                
                // Extract the variable name
                const varName = prefix.includes('_') ? prefix.split('_')[1] : 'ncl'; // Default to 'ncl' if not specified
                
                console.log(`Creating debug button for function "${functionId}", variable "${varName}"`);
                
                // Only create the debug button if we have a valid function ID (not 'locals', 'globals', etc.)
                let debugButton = '';
                if (functionId && !['locals', 'globals', 'return'].includes(functionId)) {
                    debugButton = `<button class="btn btn-sm btn-info mt-1" onclick="debugNestedStructure('${functionId}', '${varName}')">Debug Structure</button>`;
                } else {
                    // Get the current function ID from the URL or the page
                    const currentFunctionId = getCurrentFunctionId();
                    if (currentFunctionId) {
                        debugButton = `<button class="btn btn-sm btn-info mt-1" onclick="debugNestedStructure('${currentFunctionId}', '${varName}')">Debug Structure</button>`;
                    } else {
                        debugButton = `<span class="text-muted">(Debug not available - no function ID)</span>`;
                    }
                }
                
                // Try to display the raw nested list structure directly
                let rawDataDisplay = '';
                if (obj.items && Object.keys(obj.items).length > 0) {
                    try {
                        // Create a more accurate representation of the nested list structure
                        const nestedListData = [];
                        // Sort keys numerically to maintain order
                        const sortedKeys = Object.keys(obj.items).sort((a, b) => parseInt(a) - parseInt(b));
                        
                        for (const key of sortedKeys) {
                            const item = obj.items[key];
                            if (item && item.type === 'list') {
                                // This is a nested list
                                const innerList = [];
                                
                                // If the inner list has items, try to extract them
                                if (item.items && Object.keys(item.items).length > 0) {
                                    const innerSortedKeys = Object.keys(item.items).sort((a, b) => parseInt(a) - parseInt(b));
                                    for (const innerKey of innerSortedKeys) {
                                        const innerItem = item.items[innerKey];
                                        if (innerItem && typeof innerItem !== 'object') {
                                            // This is a primitive value
                                            innerList.push(innerItem);
                                        } else if (innerItem && innerItem.value !== undefined) {
                                            // This is an object with a value property
                                            innerList.push(innerItem.value);
                                        }
                                    }
                                }
                                
                                nestedListData.push(innerList.length > 0 ? innerList : []);
                            }
                        }
                        
                        // Create a more descriptive display of the raw data
                        if (nestedListData.length > 0) {
                            const displayData = JSON.stringify(nestedListData, null, 2);
                            rawDataDisplay = `<div class="raw-data-note">Raw data from database: <pre>${displayData}</pre></div>`;
                        }
                    } catch (e) {
                        console.error('Error formatting nested list:', e);
                        rawDataDisplay = `<div class="raw-data-note">Error formatting nested list: ${e.message}</div>`;
                    }
                }
                
                const noteHtml = `<div class="reanimation-note">${note}<br>${debugButton}</div>${rawDataDisplay}`;
                
                // Remove the special properties before formatting the rest
                const objCopy = {...obj};
                delete objCopy._nested_list;
                delete objCopy._nested_structure;
                delete objCopy._can_display_directly;
                delete objCopy._display_note;
                
                return noteHtml + formatObjectPretty(objCopy, prefix, isTopLevel);
            }
            
            // Handle reanimation notes
            if (obj && typeof obj === 'object' && obj._needs_reanimation) {
                const note = obj._reanimation_note || "This object requires reanimation for full details";
                const apiHint = `<span class="api-hint">reanimator.reanimate_objects('${prefix.split('_')[0]}')</span>`;
                const noteHtml = `<div class="reanimation-note">${note}<br>Use: ${apiHint}</div>`;
                
                // Remove the note properties before formatting the rest
                const objCopy = {...obj};
                delete objCopy._needs_reanimation;
                delete objCopy._reanimation_note;
                
                return noteHtml + formatObjectPretty(objCopy, prefix, isTopLevel);
            }
            
            // Handle primitive values with type information
            if (obj && typeof obj === 'object' && obj.type && obj.value !== undefined) {
                return `<span class="primitive-value">${obj.value}</span> <span class="object-type">(${obj.type})</span>`;
            }
            
            // Handle primitive types directly
            if (typeof obj === 'number') {
                return `<span class="primitive-value">${obj}</span>`;
            }
            
            if (typeof obj === 'boolean') {
                return `<span class="primitive-value">${obj}</span>`;
            }
            
            if (typeof obj === 'string') {
                // Check if it's a JSON string that we can parse
                if (obj.startsWith('{') || obj.startsWith('[')) {
                    try {
                        const parsed = JSON.parse(obj);
                        return formatObjectPretty(parsed, prefix);
                    } catch (e) {
                        // Not valid JSON, treat as regular string
                        return `<span class="string-value">"${escapeHtml(obj)}"</span>`;
                    }
                }
                return `<span class="string-value">"${escapeHtml(obj)}"</span>`;
            }
            
            if (typeof obj !== 'object') {
                return `<span class="primitive-value">${obj}</span>`;
            }
            
            if (Array.isArray(obj)) {
                if (obj.length === 0) {
                    return '[]';
                }
                
                const uniqueId = prefix + '_array_' + Math.random().toString(36).substr(2, 9);
                let result = `<div class="collapsible" onclick="toggleCollapsible('${uniqueId}')">Array(${obj.length})</div>`;
                result += `<div id="${uniqueId}" class="collapsible-content">`;
                
                for (let i = 0; i < obj.length; i++) {
                    result += `<div>[${i}]: ${formatObjectPretty(obj[i], uniqueId + '_' + i)}</div>`;
                }
                
                result += '</div>';
                return result;
            }
            
            const keys = Object.keys(obj);
            if (keys.length === 0) {
                return '{}';
            }
            
            // Special handling for raw data
            if (obj._raw_data) {
                // Add a note that this is raw data
                return `<div class="raw-data-note">Raw data from database (not reanimated)</div>${formatObjectEntriesPretty(obj, keys, prefix, isTopLevel)}`;
            }
            
            return formatObjectEntriesPretty(obj, keys, prefix, isTopLevel);
        }

        function formatObjectEntriesPretty(obj, keys, prefix, isTopLevel = false) {
            // For top-level objects, directly show the properties without collapsible
            if (isTopLevel) {
                let result = `<div class="top-level-container">`;
                
                for (const key of keys) {
                    // Skip internal properties that start with underscore
                    if (key.startsWith('_') && key !== '_raw_data') {
                        continue;
                    }
                    
                    const value = obj[key];
                    const formattedValue = formatObjectPretty(value, prefix + '_' + key);
                    result += `<div><span class="object-key">${key}</span>: ${formattedValue}</div>`;
                }
                
                result += '</div>';
                return result;
            }
            
            // For nested objects, use collapsible
            const uniqueId = prefix + '_obj_' + Math.random().toString(36).substr(2, 9);
            let objType = obj.type || 'Object';
            
            let result = `<div class="collapsible" onclick="toggleCollapsible('${uniqueId}')">${objType} {${keys.length} properties}</div>`;
            result += `<div id="${uniqueId}" class="collapsible-content">`;
            
            for (const key of keys) {
                // Skip internal properties that start with underscore
                if (key.startsWith('_') && key !== '_raw_data') {
                    continue;
                }
                
                const value = obj[key];
                const formattedValue = formatObjectPretty(value, uniqueId + '_' + key);
                result += `<div><span class="object-key">${key}</span>: ${formattedValue}</div>`;
            }
            
            result += '</div>';
            return result;
        }

        function escapeHtml(str) {
            return str
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }

        function toggleCollapsible(id) {
            const content = document.getElementById(id);
            if (content) {
                content.style.display = content.style.display === 'block' ? 'none' : 'block';
            }
        }

        function setupCollapsibles() {
            // Expand the first level of collapsibles by default
            const firstLevelCollapsibles = document.querySelectorAll('.tab-pane.active .collapsible-content');
            for (const collapsible of firstLevelCollapsibles) {
                collapsible.style.display = 'block';
            }
        }

        function debugNestedStructure(functionId, variableName) {
            console.log(`Debug structure called for function "${functionId}", variable "${variableName}"`);
            
            // Sanitize the function ID and variable name to ensure they're valid for URLs
            functionId = functionId.trim();
            variableName = variableName.trim();
            
            // Create a modal to show the debug information
            const modalId = 'debugModal';
            let modal = document.getElementById(modalId);
            
            if (!modal) {
                // Create the modal if it doesn't exist
                modal = document.createElement('div');
                modal.id = modalId;
                modal.className = 'modal fade';
                modal.tabIndex = -1;
                modal.setAttribute('aria-labelledby', 'debugModalLabel');
                modal.setAttribute('aria-hidden', 'true');
                
                modal.innerHTML = `
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="debugModalLabel">Structure Debug</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <div id="debugContent">
                                    <div class="text-center">
                                        <div class="spinner-border" role="status">
                                            <span class="visually-hidden">Loading...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                                <button type="button" class="btn btn-primary" id="viewVersionsBtn">View Version History</button>
                            </div>
                        </div>
                    </div>
                `;
                
                document.body.appendChild(modal);
            }
            
            // Show the modal
            const modalElement = new bootstrap.Modal(modal);
            modalElement.show();
            
            // Set up the View Version History button
            const viewVersionsBtn = document.getElementById('viewVersionsBtn');
            viewVersionsBtn.onclick = function() {
                viewVersionHistory(functionId, variableName);
            };
            
            // Properly encode the URL parameters
            const encodedFunctionId = encodeURIComponent(functionId);
            const encodedVariableName = encodeURIComponent(variableName);
            
            // Fetch the debug information
            const apiUrl = `/api/debug-structure/${encodedFunctionId}/${encodedVariableName}`;
            console.log(`Fetching from API: ${apiUrl}`);
            
            fetch(apiUrl)
                .then(response => {
                    console.log('API response received:', response);
                    
                    if (!response.ok) {
                        throw new Error(`HTTP error! Status: ${response.status}, URL: ${apiUrl}`);
                    }
                    
                    return response.text();  // Get the raw text first
                })
                .then(text => {
                    console.log('Raw API response text:', text);
                    
                    if (!text || text.trim() === '') {
                        throw new Error('Empty response from server');
                    }
                    
                    // Try to parse the JSON
                    try {
                        const data = JSON.parse(text);
                        console.log('Parsed JSON data:', data);
                        return data;
                    } catch (e) {
                        console.error('JSON parse error:', e);
                        throw new Error(`JSON parse error: ${e.message}\nRaw data: ${text.substring(0, 200)}...`);
                    }
                })
                .then(data => {
                    const debugContent = document.getElementById('debugContent');
                    
                    if (data.error) {
                        console.error('API returned error:', data.error);
                        debugContent.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                        return;
                    }
                    
                    console.log('Structure info:', data.structure_info);
                    const structureInfo = data.structure_info;
                    
                    // Check if we have reconstructed values
                    let reconstructedValueHtml = '';
                    if (structureInfo.structure && structureInfo.structure.reconstructed_value) {
                        console.log('Reconstructed value:', structureInfo.structure.reconstructed_value);
                        const reconstructedValue = structureInfo.structure.reconstructed_value;
                        reconstructedValueHtml = `
                            <div class="card mb-3">
                                <div class="card-header bg-success text-white">
                                    Reconstructed Value
                                </div>
                                <div class="card-body">
                                    <pre class="json-display">${JSON.stringify(reconstructedValue, null, 2)}</pre>
                                </div>
                            </div>
                        `;
                    }
                    
                    // Check if we have detailed structure information
                    let detailedStructureHtml = '';
                    if (structureInfo.structure && structureInfo.structure.detailed_structure) {
                        console.log('Detailed structure:', structureInfo.structure.detailed_structure);
                        const detailedStructure = structureInfo.structure.detailed_structure;
                        detailedStructureHtml = `
                            <div class="card mb-3">
                                <div class="card-header bg-info text-white">
                                    Detailed Structure
                                </div>
                                <div class="card-body">
                                    <pre class="json-display">${JSON.stringify(detailedStructure, null, 2)}</pre>
                                </div>
                            </div>
                        `;
                    }
                    
                    // Format the structure info - use a safer approach to display the structure
                    let structureHtml = '';
                    try {
                        // Create a copy of the structure without the detailed_structure and reconstructed_value
                        // to avoid duplicating large amounts of data
                        const structureCopy = {...structureInfo.structure};
                        delete structureCopy.detailed_structure;
                        delete structureCopy.reconstructed_value;
                        
                        // Convert the structure to a string with proper formatting
                        console.log('Structure copy for display:', structureCopy);
                        const structureStr = JSON.stringify(structureCopy, null, 2);
                        structureHtml = `<pre class="json-display">${structureStr}</pre>`;
                    } catch (e) {
                        console.error('Error formatting structure:', e);
                        // If JSON.stringify fails, use a more robust approach
                        structureHtml = `<div class="alert alert-warning">
                            Could not format structure as JSON. Displaying as string:
                            <pre>${String(structureInfo.structure)}</pre>
                        </div>`;
                    }
                    
                    // Format the structure info
                    let html = `
                        <h4>Variable: ${structureInfo.variable}</h4>
                        <p><strong>Location:</strong> ${structureInfo.location}</p>
                        <p><strong>Type:</strong> ${structureInfo.type}</p>
                        
                        ${reconstructedValueHtml}
                        ${detailedStructureHtml}
                        
                        <h5>Database Structure:</h5>
                        ${structureHtml}
                    `;
                    
                    debugContent.innerHTML = html;
                })
                .catch(error => {
                    console.error('Fetch error:', error);
                    const debugContent = document.getElementById('debugContent');
                    debugContent.innerHTML = `
                        <div class="alert alert-danger">
                            <h4>Error</h4>
                            <p>${error.message}</p>
                            <p>Function ID: ${functionId}</p>
                            <p>Variable Name: ${variableName}</p>
                            <p>API URL: ${apiUrl}</p>
                        </div>
                    `;
                });
        }

        // New function to view version history
        function viewVersionHistory(functionId, variableName) {
            console.log(`View version history called for function "${functionId}", variable "${variableName}"`);
            
            // Create a modal to show the version history
            const modalId = 'versionHistoryModal';
            let modal = document.getElementById(modalId);
            
            if (!modal) {
                // Create the modal if it doesn't exist
                modal = document.createElement('div');
                modal.id = modalId;
                modal.className = 'modal fade';
                modal.tabIndex = -1;
                modal.setAttribute('aria-labelledby', 'versionHistoryModalLabel');
                modal.setAttribute('aria-hidden', 'true');
                
                modal.innerHTML = `
                    <div class="modal-dialog modal-xl">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="versionHistoryModalLabel">Version History</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <div id="versionHistoryContent">
                                    <div class="text-center">
                                        <div class="spinner-border" role="status">
                                            <span class="visually-hidden">Loading...</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            </div>
                        </div>
                    </div>
                `;
                
                document.body.appendChild(modal);
            }
            
            // Show the modal
            const modalElement = new bootstrap.Modal(modal);
            modalElement.show();
            
            // Properly encode the URL parameters
            const encodedFunctionId = encodeURIComponent(functionId);
            const encodedVariableName = encodeURIComponent(variableName);
            
            // Fetch the version history
            const apiUrl = `/api/debug-versions/${encodedFunctionId}/${encodedVariableName}`;
            console.log(`Fetching from API: ${apiUrl}`);
            
            fetch(apiUrl)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! Status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    const versionHistoryContent = document.getElementById('versionHistoryContent');
                    
                    if (data.error) {
                        versionHistoryContent.innerHTML = `<div class="alert alert-danger">${data.error}</div>`;
                        return;
                    }
                    
                    // Format the version history
                    let html = `
                        <h4>Version History for ${data.variable_name}</h4>
                        <p><strong>Function:</strong> ${data.debug_info.function_context.function_name} (ID: ${data.debug_info.function_context.function_id})</p>
                        <p><strong>File:</strong> ${data.debug_info.function_context.file_path}:${data.debug_info.function_context.line_number}</p>
                        <p><strong>Variable Location:</strong> ${data.debug_info.function_context.variable_location}</p>
                    `;
                    
                    // Display identities and their versions
                    if (data.debug_info.identities && data.debug_info.identities.length > 0) {
                        html += `<div class="accordion" id="versionAccordion">`;
                        
                        data.debug_info.identities.forEach((identity, identityIndex) => {
                            const identityId = `identity-${identityIndex}`;
                            
                            html += `
                                <div class="accordion-item">
                                    <h2 class="accordion-header" id="heading-${identityId}">
                                        <button class="accordion-button" type="button" data-bs-toggle="collapse" data-bs-target="#collapse-${identityId}" aria-expanded="true" aria-controls="collapse-${identityId}">
                                            Identity: ${identity.name} (${identity.identity_hash.substring(0, 8)}...)
                                        </button>
                                    </h2>
                                    <div id="collapse-${identityId}" class="accordion-collapse collapse show" aria-labelledby="heading-${identityId}" data-bs-parent="#versionAccordion">
                                        <div class="accordion-body">
                                            <table class="table table-striped">
                                                <thead>
                                                    <tr>
                                                        <th>Version</th>
                                                        <th>Timestamp</th>
                                                        <th>Attributes</th>
                                                        <th>Function Calls</th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                            `;
                            
                            // Sort versions by version number
                            const sortedVersions = [...identity.versions].sort((a, b) => a.version_number - b.version_number);
                            
                            sortedVersions.forEach(version => {
                                // Format attributes
                                let attributesHtml = '<ul class="list-unstyled">';
                                if (version.attributes) {
                                    for (const [key, value] of Object.entries(version.attributes)) {
                                        attributesHtml += `<li><strong>${key}:</strong> ${value}</li>`;
                                    }
                                } else {
                                    attributesHtml += '<li>No attributes available</li>';
                                }
                                attributesHtml += '</ul>';
                                
                                // Format function calls
                                let functionCallsHtml = '<ul class="list-unstyled">';
                                if (version.function_calls && version.function_calls.length > 0) {
                                    version.function_calls.forEach(call => {
                                        functionCallsHtml += `
                                            <li>
                                                <a href="#" onclick="loadFunctionDetails(${call.call_id}); return false;">
                                                    ${call.function} (${call.role}: ${call.name})
                                                </a>
                                            </li>
                                        `;
                                    });
                                } else {
                                    functionCallsHtml += '<li>No function calls</li>';
                                }
                                functionCallsHtml += '</ul>';
                                
                                html += `
                                    <tr>
                                        <td>${version.version_number}</td>
                                        <td>${new Date(version.timestamp).toLocaleString()}</td>
                                        <td>${attributesHtml}</td>
                                        <td>${functionCallsHtml}</td>
                                    </tr>
                                `;
                            });
                            
                            html += `
                                                </tbody>
                                            </table>
                                        </div>
                                    </div>
                                </div>
                            `;
                        });
                        
                        html += `</div>`;
                    } else {
                        html += `<div class="alert alert-info">No version history found for this variable.</div>`;
                    }
                    
                    versionHistoryContent.innerHTML = html;
                })
                .catch(error => {
                    console.error('Fetch error:', error);
                    const versionHistoryContent = document.getElementById('versionHistoryContent');
                    versionHistoryContent.innerHTML = `
                        <div class="alert alert-danger">
                            <h4>Error</h4>
                            <p>${error.message}</p>
                        </div>
                    `;
                });
        }

        // Helper function to get the current function ID from the page
        function getCurrentFunctionId() {
            // Try to extract the function ID from the URL
            const pathParts = window.location.pathname.split('/');
            if (pathParts.length > 2 && pathParts[1] === 'api' && pathParts[2] === 'function-call') {
                return pathParts[3];
            }
            
            // If not in the URL, try to find it in the page content
            const functionDetailsHeader = document.querySelector('.card.detail-card .card-header h3');
            if (functionDetailsHeader) {
                // The function ID might be stored in a data attribute or we can try to find it in the DOM
                const detailsContainer = document.getElementById('function-details');
                if (detailsContainer && detailsContainer.dataset && detailsContainer.dataset.functionId) {
                    return detailsContainer.dataset.functionId;
                }
            }
            
            // As a last resort, check if we have any function calls loaded and use the first one
            const functionCards = document.querySelectorAll('.function-card');
            if (functionCards.length > 0 && functionCards[0].dataset && functionCards[0].dataset.functionId) {
                return functionCards[0].dataset.functionId;
            }
            
            return null;
        }
        
        // Legacy format function kept for backward compatibility
        function formatObject(obj) {
            if (obj === null || obj === undefined) {
                return 'null';
            }
            
            // Handle reanimated objects
            if (obj && typeof obj === 'object' && obj.is_reanimated) {
                return `<span class="text-success">${obj.value}</span> <span class="text-muted">(${obj.type})</span>`;
            }
            
            if (typeof obj === 'string') {
                return `"${obj}"`;
            }
            
            if (typeof obj !== 'object') {
                return String(obj);
            }
            
            try {
                return JSON.stringify(obj, null, 2);
            } catch (e) {
                return String(obj);
            }
        }
    </script>
</body>
</html>
"""

# Write the HTML template to the templates directory
with open(os.path.join(template_dir, 'index.html'), 'w') as f:
    f.write(index_html)

# JSON encoder for datetime objects
class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects"""
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super().default(obj)

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
    global db_manager, reanimator
    if not db_manager:
        abort(500, description="Database manager not initialized")
    
    # Convert function_id to integer since it comes as a string from the URL
    try:
        function_id_int = int(function_id)
    except ValueError:
        abort(400, description="Invalid function ID format")
        
    function_calls = db_manager.get_all_function_calls()
    
    # Find the function call
    function_call = None
    for call in function_calls:
        if call.id == function_id_int:  # Compare with integer ID
            function_call = call
            break
    
    if not function_call:
        abort(404, description=f"Function call with ID {function_id} not found")
    
    # Get the function call data directly from the database manager
    # This provides raw data without reanimating objects
    details = db_manager.get_function_call_data(function_id_int)  # Use integer ID
    
    # Add a flag to indicate that this data is raw (not reanimated)
    if details:
        details['_raw_data'] = True
        
        # Process nested lists and complex objects
        if 'locals' in details:
            _process_nested_structures(details['locals'])
        
        if 'globals' in details:
            _process_nested_structures(details['globals'])
        
        # Add a note about reanimation for complex objects
        if 'return_value' in details and details['return_value'] and isinstance(details['return_value'], dict):
            _process_nested_structures({'return': details['return_value']})
            
            if 'attributes' in details['return_value'] or 'items' in details['return_value']:
                details['return_value']['_needs_reanimation'] = True
                details['return_value']['_reanimation_note'] = "This complex object can be fully reconstructed using the reanimator API"
    
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
            'details': details,
            'reanimator_available': reanimator is not None
        }, cls=DateTimeEncoder),
        status=200,
        mimetype='application/json'
    )

def _process_nested_structures(data_dict):
    """
    Process nested structures like lists of lists to make them more displayable.
    
    Args:
        data_dict: Dictionary containing variable data
    """
    for key, value in data_dict.items():
        if isinstance(value, dict):
            # Check if it's a list
            if value.get('type') == 'list':
                items = value.get('items', {})
                
                # Check if it contains nested lists
                has_nested_lists = False
                all_primitive_sublists = True
                
                for item_key, item_value in items.items():
                    if isinstance(item_value, dict) and item_value.get('type') == 'list':
                        has_nested_lists = True
                        
                        # Check if this nested list contains only primitive values
                        if item_value.get('id'):
                            # This is a reference to another object, not a primitive
                            all_primitive_sublists = False
                
                if has_nested_lists:
                    value['_nested_list'] = True
                    value['_nested_structure'] = "List containing nested lists"
                    
                    # If all sublists contain only primitive values, we can display them directly
                    if all_primitive_sublists:
                        value['_can_display_directly'] = True
                        value['_display_note'] = "This nested list can be displayed directly"
                    
                    # Process each item in the list
                    for item_key, item_value in items.items():
                        if isinstance(item_value, dict):
                            _process_nested_structures({f"{key}_{item_key}": item_value})
            
            # Recursively process other dictionaries
            elif 'attributes' in value:
                _process_nested_structures(value['attributes'])
            elif 'items' in value:
                # Process dictionary items
                for item_key, item_value in value.get('items', {}).items():
                    if isinstance(item_value, dict):
                        _process_nested_structures({f"{key}_{item_key}": item_value})

def open_browser(url):
    """Open the browser after a short delay"""
    time.sleep(1.5)
    webbrowser.open(url)

def run_explorer(db_file, host='127.0.0.1', port=5000, debug=False, open_browser_flag=True):
    """
    Run the web explorer.
    
    Args:
        db_file: Path to the database file
        host: Host to run the server on
        port: Port to run the server on
        debug: Whether to run in debug mode
        open_browser_flag: Whether to open a browser automatically
    """
    global db_manager, db_path, reanimator
    
    # Check if the database file exists
    if not os.path.exists(db_file):
        logger.error(f"Database file not found: {db_file}")
        sys.exit(1)
    
    # Initialize the database manager
    db_path = db_file
    Session = init_db(db_file)
    db_manager = DatabaseManager(Session)
    
    # Initialize the reanimator
    try:
        reanimator = Reanimator(db_file)
        logger.info("Reanimator initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing reanimator: {e}")
        reanimator = None
    
    # Create the HTML template file
    with open(os.path.join(template_dir, 'index.html'), 'w') as f:
        f.write(index_html)
    
    # Open browser after a delay
    if open_browser_flag:
        url = f"http://{host}:{port}"
        threading.Timer(1.5, open_browser, args=[url]).start()
    
    # Run the Flask app
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

@app.route('/api/debug-structure/<function_id>/<variable_name>')
def debug_structure(function_id, variable_name):
    """Debug a nested structure in a function call"""
    global reanimator
    if not reanimator:
        abort(500, description="Reanimator not initialized")
    
    try:
        # Validate that function_id can be converted to an integer
        try:
            int(function_id)  # Just validate, but keep as string for the API call
        except ValueError:
            return jsonify({'error': f"Invalid function ID format: {function_id}"}), 400
            
        # Use the reanimator to debug the structure - pass function_id as string
        structure_info = reanimator.debug_nested_structure(function_id, variable_name)
        
        # Process the structure info to ensure it's JSON serializable
        def process_for_json(obj):
            if isinstance(obj, dict):
                return {k: process_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [process_for_json(item) for item in obj]
            elif isinstance(obj, (int, float, bool, str, type(None))):
                return obj
            else:
                return str(obj)
        
        # Process the structure info
        processed_info = process_for_json(structure_info)
        
        # Log the processed info for debugging
        logger.info(f"Debug structure for {function_id}/{variable_name}: {processed_info}")
        
        # Create the response data
        response_data = {
            'structure_info': processed_info
        }
        
        # Convert to JSON with the DateTimeEncoder
        json_data = json.dumps(response_data, cls=DateTimeEncoder)
        
        # Return the response
        return app.response_class(
            response=json_data,
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"Error debugging structure: {e}", exc_info=True)
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/api/object-history/<variable_name>')
def object_history(variable_name):
    """Get the version history for an object by name"""
    global reanimator
    if not reanimator:
        abort(500, description="Reanimator not initialized")
    
    try:
        # Use the reanimator to get the object history
        history = reanimator.get_object_history(variable_name)
        
        # Process the history to ensure it's JSON serializable
        def process_for_json(obj):
            if isinstance(obj, dict):
                return {k: process_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [process_for_json(item) for item in obj]
            elif isinstance(obj, (int, float, bool, str, type(None))):
                return obj
            else:
                return str(obj)
        
        # Process the history
        processed_history = process_for_json(history)
        
        # Log the processed history for debugging
        logger.info(f"Object history for {variable_name}: {processed_history}")
        
        # Create the response data
        response_data = {
            'variable_name': variable_name,
            'history': processed_history
        }
        
        # Convert to JSON with the DateTimeEncoder
        json_data = json.dumps(response_data, cls=DateTimeEncoder)
        
        # Return the response
        return app.response_class(
            response=json_data,
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"Error getting object history: {e}", exc_info=True)
        return jsonify({
            'error': str(e)
        }), 500

@app.route('/api/debug-versions/<function_id>/<variable_name>')
def debug_versions(function_id, variable_name):
    """Debug the versions of an object by name in the context of a specific function call"""
    global reanimator
    if not reanimator:
        abort(500, description="Reanimator not initialized")
    
    try:
        # Validate function_id
        try:
            int(function_id)
        except ValueError:
            return jsonify({'error': f"Invalid function ID format: {function_id}"}), 400
            
        # Get the function call details first to establish context
        call_details = reanimator.get_call_details(function_id)
        
        if 'error' in call_details:
            return jsonify({'error': f"Function call not found: {call_details['error']}"}), 404
            
        # Check if the variable exists in this function call
        var_found = False
        var_location = None
        var_data = None
        
        if 'locals' in call_details and variable_name in call_details['locals']:
            var_found = True
            var_location = 'locals'
            var_data = call_details['locals'][variable_name]
        elif 'globals' in call_details and variable_name in call_details['globals']:
            var_found = True
            var_location = 'globals'
            var_data = call_details['globals'][variable_name]
        elif variable_name == 'return_value' and 'return_value' in call_details:
            var_found = True
            var_location = 'return'
            var_data = call_details['return_value']
            
        if not var_found:
            return jsonify({'error': f"Variable '{variable_name}' not found in function call {function_id}"}), 404
            
        # Use the reanimator to debug the object versions
        debug_info = reanimator.debug_object_versions(variable_name)
        
        # Add context information
        debug_info['function_context'] = {
            'function_id': function_id,
            'function_name': call_details.get('function'),
            'file_path': call_details.get('file'),
            'line_number': call_details.get('line'),
            'variable_location': var_location
        }
        
        # Process the debug info to ensure it's JSON serializable
        def process_for_json(obj):
            if isinstance(obj, dict):
                return {k: process_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [process_for_json(item) for item in obj]
            elif isinstance(obj, (int, float, bool, str, type(None))):
                return obj
            else:
                return str(obj)
        
        # Process the debug info
        processed_info = process_for_json(debug_info)
        
        # Log the processed info for debugging
        logger.info(f"Debug versions for {function_id}/{variable_name}: {processed_info}")
        
        # Create the response data
        response_data = {
            'function_id': function_id,
            'variable_name': variable_name,
            'debug_info': processed_info
        }
        
        # Convert to JSON with the DateTimeEncoder
        json_data = json.dumps(response_data, cls=DateTimeEncoder)
        
        # Return the response
        return app.response_class(
            response=json_data,
            status=200,
            mimetype='application/json'
        )
    except Exception as e:
        logger.error(f"Error debugging object versions: {e}", exc_info=True)
        return jsonify({
            'error': str(e)
        }), 500 