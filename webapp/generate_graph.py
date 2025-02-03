import json

def generate_dot_graph(input_file, output_file):
    # Read and parse all events
    events = []
    with open(input_file, 'r') as f:
        for line in f:
            events.append(json.loads(line))

    # Add these two lines to organize events
    calls = {e['execution_id']: e for e in events if e['event_type'] == 'call'}
    returns = {e['execution_id']: e for e in events if e['event_type'] == 'return'}
    
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
            if call['parent_id'] is not None:
                # Simplified argument display
                args = []
                for k, v in call['locals'].items():
                    if k != 'self':
                        args.append(f"{k}={v}")
                arg_label = ", ".join(args) if args else ""
                
                # Call arrow (parent to child)
                f.write(f'  "{call["parent_id"]}" -> "{exec_id}" [color=blue')
                if arg_label:
                    f.write(f', label="{arg_label}"')
                f.write('];\n')
                
                # Return arrow (parent to child)
                if exec_id in returns:
                    return_value = returns[exec_id]['return_value'].strip('"')
                    safe_value = return_value.replace('"', '\\"')
                    f.write(f'  "{exec_id}" -> "{call["parent_id"]}" '
                            f'[label="{safe_value}", color=red, style=dashed];\n')

        f.write('}\n') 

if __name__ == "__main__":
    generate_dot_graph("data.jsonl", "execution_graph.dot")