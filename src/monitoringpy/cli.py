import argparse
import os
from .generate_graph import generate_dot_graph

def main():
    parser = argparse.ArgumentParser(
        description='Generate execution graph from monitoring data'
    )
    parser.add_argument(
        'input_file',
        help='Input JSONL file containing monitoring data'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output DOT file (default: execution_graph.dot)',
        default='execution_graph.dot'
    )
    parser.add_argument(
        '--png',
        action='store_true',
        help='Also generate PNG file using graphviz'
    )

    args = parser.parse_args()

    # Generate DOT file
    generate_dot_graph(args.input_file, args.output)
    print(f"Generated DOT file: {args.output}")

    # Optionally generate PNG
    if args.png:
        png_file = os.path.splitext(args.output)[0] + '.png'
        os.system(f"dot -Tpng {args.output} -o {png_file}")
        print(f"Generated PNG file: {png_file}")

if __name__ == '__main__':
    main() 