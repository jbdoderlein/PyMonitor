import json
import os
from .models import init_db
from .db_operations import DatabaseManager

def generate_dot_graph(db_path, output_file):
    # Initialize database session and manager
    Session = init_db(db_path)
    db_manager = DatabaseManager(Session)
    
    # Query all function calls from the database
    function_calls = db_manager.get_all_function_calls()
    
    # Organize events
    calls = {}
    returns = {}
    
    for call in function_calls:
        # Get function call data (locals, globals, return value)
        call_data = db_manager.get_function_call_data(call.id)
        if not call_data:
            continue
            
        # Convert database record to dictionary
        event = {
            'execution_id': call.id,
            'event_type': call.event_type,
            'file': call.file,
            'function': call.function,
            'line': call.line,
            'start_time': call.start_time.isoformat() if call.start_time else None,
            'end_time': call.end_time.isoformat() if call.end_time else None,
            'locals': call_data['locals'],
            'globals': call_data['globals'],
        }
        
        # Add return value if available
        if call_data['return_value'] is not None:
            event['return_value'] = call_data['return_value']
        
        # Add to appropriate dictionary
        if call.event_type == 'call':
            calls[call.id] = event
        else:
            returns[call.id] = event
    
    with open(output_file, 'w') as f:
        f.write('digraph ExecutionGraph {\n')
        f.write('  rankdir=LR;\n')  # Left to right layout
        f.write('  node [shape=rect, style=rounded, fontname="Helvetica"];\n')
        f.write('  edge [fontsize=10, minlen=2];\n')  # Minimum edge length for spacing

        # Create nodes
        for exec_id, call in calls.items():
            label = f"{call['function']}()\\n{call['file'].split('/')[-1]}"
            if 'caller_line' in call:
                label += f"\\nline {call['caller_line']}"  # Simplified line reference
            f.write(f'  "{exec_id}" [label="{label}"];\n')

        # Create edges
        for exec_id, call in calls.items():
            if 'parent_id' in call and call['parent_id'] is not None:
                # Simplified argument display
                args = []
                for k, v in call.get('locals', {}).items():
                    if k != 'self':
                        # Limit the string representation for complex objects
                        arg_str = str(v)
                        if len(arg_str) > 50:
                            arg_str = arg_str[:47] + "..."
                        args.append(f"{k}={arg_str}")
                arg_label = ", ".join(args) if args else ""
                
                # Call arrow (parent to child)
                f.write(f'  "{call["parent_id"]}" -> "{exec_id}" [color=blue')
                if arg_label:
                    f.write(f', label="{arg_label}"')
                f.write('];\n')
                
                # Return arrow (parent to child)
                if exec_id in returns:
                    return_value = str(returns[exec_id].get('return_value', '')).strip('"')
                    # Limit the string representation for complex return values
                    if len(return_value) > 50:
                        return_value = return_value[:47] + "..."
                    safe_value = return_value.replace('"', '\\"')
                    f.write(f'  "{exec_id}" -> "{call["parent_id"]}" '
                            f'[label="{safe_value}", color=red, style=dashed];\n')

        f.write('}\n') 
