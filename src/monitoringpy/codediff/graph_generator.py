import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import time
import types
from collections import defaultdict

import networkx as nx
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

MONITOR_TOOL_ID = sys.monitoring.PROFILER_ID

def get_line_number_from_index(text:str, index:int) -> int:
    """Get a text and a index position in the file, return the line number
    """
    lines = text.split("\n")
    base_index = 0
    for i, line in enumerate(lines):
        if index in range(base_index, base_index + len(line)+1):
            return i+1
        base_index += len(line)+1
    raise ValueError(f"Index {index} not found in text")

def generate_line_mapping(code_path_1:str, code_path_2:str) -> tuple[dict, dict, list]:
    gumtree_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "gumtree","bin","gumtree"))
    diff_proc = subprocess.run(
        [gumtree_path, "textdiff", code_path_1, code_path_2],
        capture_output=True, text=True
    )
    diff = diff_proc.stdout

    with open(code_path_1) as f1:
        foo1_code = f1.read()
    with open(code_path_2) as f2:
        foo2_code = f2.read()


    mapping_v1_to_v2 = {}
    mapping_v2_to_v1 = {}
    modified_lines = []
    regex = r"\[.*\]"


    for section in diff.split('==='):
        section = section.strip()
        if section.startswith('insert-tree'):
            data = section.split("---")[1].strip()
            matches = re.finditer(regex, data, re.MULTILINE)
            m1,m2 = tuple(map(int, next(matches).group(0)[1:-1].split(',')))
            m1_line = get_line_number_from_index(foo2_code, m1)
            m2_line = get_line_number_from_index(foo2_code, m2)
            for i in range(m1_line, m2_line+1):
                mapping_v2_to_v1[i] = None
        elif section.startswith('delete-tree'):
            data = section.split("---")[1].strip()
            matches = re.finditer(regex, data, re.MULTILINE)
            m1,m2 = tuple(map(int, next(matches).group(0)[1:-1].split(',')))
            m1_line = get_line_number_from_index(foo1_code, m1)
            m2_line = get_line_number_from_index(foo1_code, m2)
            for i in range(m1_line, m2_line+1):
                mapping_v1_to_v2[i] = None
        elif section.startswith('update-node'):
            data = section.split("---")[1].strip()
            matches = re.finditer(regex, data, re.MULTILINE)
            m1,m2 = tuple(map(int, next(matches).group(0)[1:-1].split(',')))
            m1_line = get_line_number_from_index(foo1_code, m1)
            m2_line = get_line_number_from_index(foo2_code, m2)
            if m1_line == m2_line:
                modified_lines.append(m1_line)

        elif section.startswith('match'):
            data = section.split("---")[1].strip()
            matches = re.finditer(regex, data, re.MULTILINE)
            m1,m2 = [tuple(map(int, match.group(0)[1:-1].split(','))) for match in matches]

            m1_line_start = get_line_number_from_index(foo1_code, m1[0])
            m1_line_end = get_line_number_from_index(foo1_code, m1[1])
            m2_line_start = get_line_number_from_index(foo2_code, m2[0])
            m2_line_end = get_line_number_from_index(foo2_code, m2[1])

            if m1_line_start == m1_line_end and m2_line_start == m2_line_end:
                if m1_line_start not in mapping_v1_to_v2:
                    mapping_v1_to_v2[m1_line_start] = m2_line_start
                if m2_line_start not in mapping_v2_to_v1:
                    mapping_v2_to_v1[m2_line_start] = m1_line_start

    return mapping_v1_to_v2, mapping_v2_to_v1, modified_lines


def generate_trace(func):
    if sys.monitoring.get_tool(MONITOR_TOOL_ID) is None:
            sys.monitoring.use_tool_id(MONITOR_TOOL_ID, "py_monitoring")

    events = (sys.monitoring.events.LINE |
                     sys.monitoring.events.PY_START |
                     sys.monitoring.events.PY_RETURN)
    sys.monitoring.set_local_events(MONITOR_TOOL_ID, func.__code__, events)
    trace = []
    def hook(code: types.CodeType, line_number):
        current_frame = inspect.currentframe()
        if current_frame is None or current_frame.f_back is None:
            return
        frame = current_frame.f_back
        trace.append((frame.f_lineno, {k:v for k,v in frame.f_locals.items() if not k.startswith('__')}))
    sys.monitoring.register_callback(
                MONITOR_TOOL_ID,
                sys.monitoring.events.LINE,
                hook
            )
    func()
    return trace


def generate_graph(trace, merge_node_on_line):
    graph = nx.DiGraph()
    previous_node = None
    for i, (line, vars) in enumerate(trace):
        if merge_node_on_line:
            matching_nodes = [n for n, d in graph.nodes(data=True) if d.get("line") == line]
            if len(matching_nodes) == 0:
                graph.add_node(i, line=line, vars=[vars])
            else:
                graph.nodes[matching_nodes[0]]['vars'].append(vars)
                i = matching_nodes[0]

        else:
            graph.add_node(i, line=line, vars=[vars])

        if previous_node is not None:
            diff = defaultdict(list)
            for k,v in previous_node[1][1].items():
                if k not in vars:
                    diff[k].append((None, v))
                elif vars[k] != v:
                    diff[k].append((v,vars[k]))
            if (previous_node[0], i) in graph.edges:
                for k,v in diff.items():
                    graph.edges[previous_node[0], i]['diff'][k].extend(v)
            else:
                graph.add_edge(previous_node[0], i, diff=diff)

        previous_node = (i, (line, vars))
    return graph

def generate_edit_graph(g1, g2, mapping_v1_to_v2, modified_lines):
    # First make sure g1 and g2 have no common indices (i.e. shift g2 indices)
    g2_offset = max(g1.nodes) + 1
    g2 = nx.relabel_nodes(g2, {n: n + g2_offset for n in g2.nodes})

    paths = list(nx.optimal_edit_paths(
        g1,
        g2,
        node_match=None,  # Let cost function handle it
        edge_match=None,
        node_subst_cost=lambda n1_attrs, n2_attrs: 0 if mapping_v1_to_v2[n1_attrs['line']] == n2_attrs['line'] else 10,
        node_del_cost=lambda _: 1,
        node_ins_cost=lambda _: 1,
        edge_subst_cost=lambda _a, _b: 0,
        edge_del_cost=lambda _: 1,
        edge_ins_cost=lambda _: 1,
    ))
    node_map, edge_map = paths[0][0]
    inverse_node_map = {v: k for k, v in node_map if v is not None and k is not None}

    # Deletede node and edge keep their original number
    # Inserted nodes and edges get a new number, starting from g2_offset

    deleted_nodes = [n1 for n1, n2 in node_map if n2 is None]
    inserted_nodes = [n2 for n1, n2 in node_map if n1 is None]

    deleted_edges = [e1 for e1, e2 in edge_map if e2 is None]
    inserted_edges = [e2 for e1, e2 in edge_map if e1 is None]


    edit_graph = nx.DiGraph()

    # Add all G1 nodes
    for n, data in g1.nodes(data=True):
        edit_graph.add_node(n, line1=data['line'], vars1=data['vars'])

    # Mark deleted nodes
    for n in deleted_nodes:
        if n in edit_graph.nodes:
            edit_graph.nodes[n]['state'] = 'only1'

    # Add inserted nodes
    for n in inserted_nodes:
        edit_graph.add_node(n, line2=g2.nodes[n]['line'], vars2=g2.nodes[n]['vars'], state='only2')

    # Add all G1 edges
    for u, v, data in g1.edges(data=True):
        edit_graph.add_edge(u, v, diff=data['diff'])

    # Mark deleted edges
    for u, v in deleted_edges:
        if edit_graph.has_edge(u, v):
            edit_graph[u][v]['state'] = 'only1'

    # Add inserted edges (possibly between inserted or existing nodes)
    for u, v in inserted_edges:
        diff = {}
        if (u, v) in g2.edges:
            diff = g2.edges[(u,v)]['diff']

        if u in inverse_node_map:
            u = inverse_node_map[u]
        if v in inverse_node_map:
            v = inverse_node_map[v]

        edit_graph.add_edge(u, v, state='only2', diff=diff)

    # Mark unchanged edges/nodes as gray
    for u, v in edit_graph.edges():
        if 'state' not in edit_graph[u][v]:
            edit_graph[u][v]['state'] = 'common'


    for n,v in edit_graph.nodes(data=True):
        if 'state' not in v:
            edit_graph.nodes[n]['state'] = 'common'
        if 'line1' in v:
            if v['line1'] in modified_lines and v['state'] != 'only1' and v['state'] != 'only2':
                edit_graph.nodes[n]['state'] = 'modified'

    for u,v in node_map:
        if u is not None and v is not None:
            edit_graph.nodes[u]['line2'] = g2.nodes[v]['line']
            u_vars = g1.nodes[u]['vars']
            v_vars = g2.nodes[v]['vars']
            if u in edit_graph.nodes and 'vars1' not in edit_graph.nodes[u]:
                edit_graph.nodes[u]['vars1'] = u_vars
            if u in edit_graph.nodes and 'vars2' not in edit_graph.nodes[u]:
                edit_graph.nodes[u]['vars2'] = v_vars

            same = True
            for generation in u_vars:
                for k,v in generation.items():
                    if k not in v_vars or v_vars[k] != v:
                        same = False
            if not same:
                edit_graph.nodes[u]['equal'] = False
            else:
                edit_graph.nodes[u]['equal'] = True

    return edit_graph


def load_module_and_generate_trace(file_path: str, func_name: str):
    """Load a Python module from file path and generate execution trace for specified function."""
    module_name = os.path.splitext(os.path.basename(file_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore
    spec.loader.exec_module(module)  # type: ignore
    return generate_trace(module.__dict__[func_name])  # type: ignore


def export_graph(graph):
    return {
        "type": "graph",
        "nodes": dict(graph.nodes(data=True)),
        "edges": list(graph.edges(data=True))
    }

class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, file1, file2, func_name, callback):
        self.file1 = file1
        self.file2 = file2
        self.func_name = func_name
        self.callback = callback
        self.last_modified = {}

    def on_modified(self, event):
        if event.is_directory:
            return

        file_path = os.path.abspath(event.src_path) # type: ignore

        # Check if it's one of our monitored files
        if file_path in [self.file1, self.file2]:
            # Debounce rapid file changes
            current_time = time.time()
            if file_path in self.last_modified:
                if current_time - self.last_modified[file_path] < 1.0:  # 1 second debounce
                    return

            self.last_modified[file_path] = current_time

            # Call the callback with the specific file that changed
            self.callback(file_path)


def regenerate_graph_selective(file1, file2, func_name, changed_file, trace_cache):
    """Regenerate the graph, only regenerating trace for the changed file."""
    try:
        # Generate line mapping (always needed as it compares both files)
        mapping_v1_to_v2, mapping_v2_to_v1, modified_lines = generate_line_mapping(file1, file2)

        # Only regenerate trace for the changed file
        if changed_file == file1:
            trace_cache['trace_1'] = load_module_and_generate_trace(file1, func_name)
        elif changed_file == file2:
            trace_cache['trace_2'] = load_module_and_generate_trace(file2, func_name)

        # Use cached traces
        trace_1 = trace_cache['trace_1']
        trace_2 = trace_cache['trace_2']

        g1 = generate_graph(trace_1, merge_node_on_line=True)
        g2 = generate_graph(trace_2, merge_node_on_line=True)

        edit_graph = generate_edit_graph(g1, g2, mapping_v1_to_v2, mapping_v2_to_v1, modified_lines)

        # Export to dot
        output_json(export_graph(edit_graph))

    except Exception as e:
        output_json({"type": "error", "message": f"Error regenerating graph: {e}"})


def regenerate_graph_full(file1, file2, func_name, trace_cache):
    """Regenerate the graph completely (both traces)."""
    try:
        # Generate line mapping
        mapping_v1_to_v2, mapping_v2_to_v1, modified_lines = generate_line_mapping(file1, file2)

        # Generate both traces and cache them
        trace_cache['trace_1'] = load_module_and_generate_trace(file1, func_name)
        trace_cache['trace_2'] = load_module_and_generate_trace(file2, func_name)

        g1 = generate_graph(trace_cache['trace_1'], merge_node_on_line=True)
        g2 = generate_graph(trace_cache['trace_2'], merge_node_on_line=True)

        edit_graph = generate_edit_graph(g1, g2, mapping_v1_to_v2, mapping_v2_to_v1, modified_lines)

        # Export to dot
        output_json(export_graph(edit_graph))

    except Exception as e:
        raise e
        output_json({"type": "error", "message": f"Error generating graph: {e}"})


def watch_files(file1, file2, func_name, trace_cache):
    """Set up file watching and continuous monitoring."""
    def on_file_change(changed_file):
        regenerate_graph_selective(file1, file2, func_name, changed_file, trace_cache)

    # Create event handler
    event_handler = FileChangeHandler(file1, file2, func_name, on_file_change)

    # Set up observers for both file directories
    observer = Observer()

    # Watch directory containing file1
    dir1 = os.path.dirname(file1)
    observer.schedule(event_handler, dir1, recursive=False)

    # Watch directory containing file2 (if different)
    dir2 = os.path.dirname(file2)
    if dir2 != dir1:
        observer.schedule(event_handler, dir2, recursive=False)

    # Start monitoring
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()



def output_json(data):
    """Output JSON data to stdout for the VS Code extension to capture."""
    print(json.dumps(data))
    sys.stdout.flush()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(json.dumps({"type": "error", "message": "Usage: python analysis_script.py <original_file> <alternative_file> <function_name>"}))
        sys.exit(1)

    original_file = os.path.abspath(sys.argv[1])
    alternative_file = os.path.abspath(sys.argv[2])
    function_name = sys.argv[3]

    trace_cache = {}
    regenerate_graph_full(original_file, alternative_file, function_name, trace_cache)
    watch_files(original_file, alternative_file, function_name, trace_cache)
