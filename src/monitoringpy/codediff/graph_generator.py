import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import types
from collections import defaultdict

import networkx as nx


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

def generate_line_mapping_from_string(code_1:str, code_2:str) -> tuple[dict, dict, list]:
    with tempfile.NamedTemporaryFile(delete=False,suffix=".py") as f1, tempfile.NamedTemporaryFile(delete=False,suffix=".py") as f2:
        f1.write(code_1.encode())
        f2.write(code_2.encode())
        f1.flush()
        f2.flush()
        return generate_line_mapping(f1.name, f2.name)

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
            m2_line = get_line_number_from_index(foo1_code, m2)
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


def convert_trace(trace :list[dict], use_ref :bool = False, include_globals :bool = False) -> list[tuple[int, dict]]:
    result = []
    for frame in trace:
        locals = frame['locals'] if not use_ref else frame['locals_ref']
        if include_globals:
            globals = frame['globals'] if not use_ref else frame['globals_ref']
            locals.update(globals)
        result.append((frame['line'], locals))
    return result


def generate_graph(trace:list[tuple[int, dict]]) -> nx.DiGraph:
    graph = nx.DiGraph()
    previous_node: int | None = None
    line_to_node = {}
    for i, (line, vars) in enumerate(trace):
        if line not in line_to_node:
            graph.add_node(i, line=line, vars=[vars])
            line_to_node[line] = i
        else:
            graph.nodes[line_to_node[line]]['vars'].append(vars)
            i = line_to_node[line]

        if previous_node is not None:
            diff = {}
            previous_vars = graph.nodes[previous_node]['vars'][-1]
            for k,v in vars.items():
                if k not in previous_vars:
                    diff[k] = (None, v)
                elif previous_vars[k] != v:
                    diff[k] = (previous_vars[k],v)
            if (previous_node, i) in graph.edges:
                graph.edges[previous_node, i]['diff'].append(diff)
            else:
                graph.add_edge(previous_node, i, diff=[diff])
        previous_node = i
    return graph

def generate_edit_graph(g1 :nx.DiGraph, g2 :nx.DiGraph, mapping_v1_to_v2 :dict, mapping_v2_to_v1 :dict, modified_lines :list[int]) -> nx.DiGraph:
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
    dict_node_map = {k:v for k, v in node_map if v is not None and k is not None}
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
        edit_graph.add_edge(u, v, diff1=data['diff'])

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
        
        edit_graph.add_edge(u, v, state='only2', diff2=diff)

    # Mark unchanged edges/nodes as gray
    for u, v in edit_graph.edges():
        if 'state' not in edit_graph[u][v]:
            edit_graph[u][v]['state'] = 'common'
            # common edge, need to have both diffs
            if (u, v) in g1.edges:
                edit_graph[u][v]['diff1'] = g1.edges[(u, v)]['diff']
            g2u, g2v = u, v
            if g2u in dict_node_map:
                g2u = dict_node_map[g2u]
            if g2v in dict_node_map:
                g2v = dict_node_map[g2v]
            if (g2u, g2v) in g2.edges:
                edit_graph[u][v]['diff2'] = g2.edges[(g2u, g2v)]['diff']
            

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

def export_edit_graph(edit_graph :nx.DiGraph) -> dict:
    return {
        "nodes": edit_graph.nodes(data=True),
        "edges": edit_graph.edges(data=True),
    }

