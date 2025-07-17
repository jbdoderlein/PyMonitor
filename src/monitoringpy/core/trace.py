from collections import defaultdict
from typing import Dict, Any, Optional, List, Union
from sqlalchemy.orm import Session
from .function_call import FunctionCallRepository
from .representation import ObjectManager, PickleConfig
from .models import FunctionCall, StackSnapshot, CodeDefinition
import logging
import networkx as nx

logger = logging.getLogger(__name__)


class TraceExporter:
    """Export traces to different formats with line-level granularity"""
    
    def __init__(self, session: Session, pickle_config: Optional[PickleConfig] = None):
        self.session = session
        self.function_call_repo = FunctionCallRepository(session, pickle_config)
        self.object_manager = ObjectManager(session, pickle_config)
    
    def export_function_trace(self, function_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """
        Export a function trace with line-level granularity.
        
        Args:
            function_id: The ID of the function call to export
            
        Returns:
            Dictionary containing:
            - function_info: metadata about the function
            - code: the source code and file offset information  
            - trace: ordered list of stack snapshots with actual variable values
        """
        try:
            # Convert function_id to int if needed
            if isinstance(function_id, str):
                try:
                    function_id = int(function_id)
                except ValueError:
                    logger.error(f"Invalid function ID: {function_id}")
                    return None
            
            # Get the function call
            function_call = self.session.get(FunctionCall, function_id)
            if not function_call:
                logger.error(f"Function call {function_id} not found")
                return None
            
            # Get all stack snapshots ordered by execution sequence
            snapshots = self.session.query(StackSnapshot).filter(
                StackSnapshot.function_call_id == function_id
            ).order_by(StackSnapshot.order_in_call.asc()).all()
            
            if not snapshots:
                logger.warning(f"No stack snapshots found for function call {function_id}")
                return None
            
            # Get code information
            code_info = None
            if function_call.code_definition_id:
                code_definition = self.session.query(CodeDefinition).filter(
                    CodeDefinition.id == function_call.code_definition_id
                ).first()
                
                if code_definition:
                    code_info = {
                        'name': code_definition.name,
                        'type': code_definition.type,
                        'module_path': code_definition.module_path,
                        'code_content': code_definition.code_content,
                        'first_line_no': code_definition.first_line_no or 1,
                        'creation_time': code_definition.creation_time.isoformat() if code_definition.creation_time else None
                    }
            
            # Build function metadata
            function_info = {
                'id': function_call.id,
                'function_name': function_call.function,
                'file_path': function_call.file,
                'line_number': function_call.line,
                'start_time': function_call.start_time.isoformat() if function_call.start_time else None,
                'end_time': function_call.end_time.isoformat() if function_call.end_time else None,
                'call_metadata': function_call.call_metadata
            }
            
            # Export the trace with actual variable values
            trace_snapshots = []
            for snapshot in snapshots:
                try:
                    # Rehydrate local variables
                    locals_values = {}
                    if snapshot.locals_refs:
                        for var_name, obj_ref in snapshot.locals_refs.items():
                            try:
                                value = self.object_manager.rehydrate(obj_ref)
                                locals_values[var_name] = self._serialize_value(value)
                            except Exception as e:
                                logger.warning(f"Could not rehydrate local variable '{var_name}': {e}")
                                locals_values[var_name] = f"<Error rehydrating: {str(e)}>"
                    
                    # Rehydrate global variables (filtered to exclude system variables)
                    globals_values = {}
                    if snapshot.globals_refs:
                        for var_name, obj_ref in snapshot.globals_refs.items():
                            # Skip system variables and modules
                            if not var_name.startswith("__") and not var_name.endswith("__"):
                                try:
                                    value = self.object_manager.rehydrate(obj_ref)
                                    globals_values[var_name] = self._serialize_value(value)
                                except Exception as e:
                                    logger.warning(f"Could not rehydrate global variable '{var_name}': {e}")
                                    globals_values[var_name] = f"<Error rehydrating: {str(e)}>"
                    
                    # Create the snapshot entry
                    snapshot_data = {
                        'snapshot_id': snapshot.id,
                        'line_number': snapshot.line_number,
                        'timestamp': snapshot.timestamp.isoformat() if snapshot.timestamp else None,
                        'order_in_call': snapshot.order_in_call,
                        'locals': locals_values,
                        'globals': globals_values,
                        'is_first_in_call': snapshot.is_first_in_call,
                        'is_last_in_call': snapshot.is_last_in_call
                    }
                    
                    trace_snapshots.append(snapshot_data)
                    
                except Exception as e:
                    logger.error(f"Error processing snapshot {snapshot.id}: {e}")
                    # Add a placeholder entry to maintain sequence
                    trace_snapshots.append({
                        'snapshot_id': snapshot.id,
                        'line_number': snapshot.line_number,
                        'timestamp': snapshot.timestamp.isoformat() if snapshot.timestamp else None,
                        'order_in_call': snapshot.order_in_call,
                        'locals': {},
                        'globals': {},
                        'error': f"Error processing snapshot: {str(e)}",
                        'is_first_in_call': snapshot.is_first_in_call,
                        'is_last_in_call': snapshot.is_last_in_call
                    })
            
            return {
                'function_info': function_info,
                'code': code_info,
                'trace': trace_snapshots
            }
            
        except Exception as e:
            logger.error(f"Error exporting function trace {function_id}: {e}")
            return None
    
    def _serialize_value(self, value: Any) -> Any:
        """
        Serialize a value for JSON export, handling special cases.
        
        Args:
            value: The value to serialize
            
        Returns:
            A JSON-serializable representation of the value
        """
        try:
            # Handle None
            if value is None:
                return None
            
            # Handle primitive types
            if isinstance(value, (int, float, bool, str)):
                return value
            
            # Handle lists and tuples
            if isinstance(value, (list, tuple)):
                try:
                    return [self._serialize_value(item) for item in value]
                except Exception:
                    return f"<{type(value).__name__} with {len(value)} items>"
            
            # Handle dictionaries
            if isinstance(value, dict):
                try:
                    return {str(k): self._serialize_value(v) for k, v in value.items()}
                except Exception:
                    return f"<dict with {len(value)} items>"
            
            # Handle custom objects
            if hasattr(value, '__dict__'):
                try:
                    # Try to get a meaningful representation
                    if hasattr(value, '__str__'):
                        str_repr = str(value)
                        # Avoid very long string representations 
                        if len(str_repr) > 200:
                            str_repr = str_repr[:200] + "..."
                        return {
                            '_type': type(value).__name__,
                            '_module': getattr(type(value), '__module__', 'unknown'),
                            '_repr': str_repr,
                            '_attributes': {k: self._serialize_value(v) for k, v in value.__dict__.items() 
                                          if not k.startswith('_')}
                        }
                    else:
                        return f"<{type(value).__name__} object>"
                except Exception:
                    return f"<{type(value).__name__} object (serialization failed)>"
            
            # Fallback for other types
            try:
                return str(value)
            except Exception:
                return f"<{type(value).__name__} object (not serializable)>"
                
        except Exception as e:
            logger.debug(f"Error serializing value: {e}")
            return f"<serialization error: {str(e)}>"
    
    def export_traces_to_json(self, function_ids: List[Union[str, int]]) -> List[Dict[str, Any]]:
        """
        Export multiple function traces to JSON format.
        
        Args:
            function_ids: List of function call IDs to export
            
        Returns:
            List of exported trace dictionaries
        """
        results = []
        for function_id in function_ids:
            trace = self.export_function_trace(function_id)
            if trace:
                results.append(trace)
            else:
                logger.warning(f"Could not export trace for function {function_id}")
        return results
    
    def get_available_traces(self) -> List[Dict[str, Any]]:
        """
        Get a list of all available function traces.
        
        Returns:
            List of dictionaries with basic info about available traces
        """
        return self.function_call_repo.get_functions_with_traces()


def generate_graph_from_trace(trace):
    graph = nx.DiGraph()
    
    previous_node = None
    for i, snapshot in enumerate(trace["trace"]):
        line = snapshot["line_number"]
        vars = snapshot["locals"]
        matching_nodes = [n for n, d in graph.nodes(data=True) if d.get("line") == line]
        if len(matching_nodes) == 0:
            graph.add_node(i, line=line, vars=[vars])
        else:
            graph.nodes[matching_nodes[0]]['vars'].append(vars)
            i = matching_nodes[0]


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

def export_graph(graph):
    return {
        "type": "graph",
        "nodes": dict(graph.nodes(data=True)),
        "edges": list(graph.edges(data=True))
    }