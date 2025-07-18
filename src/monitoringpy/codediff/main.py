import os
import re
import subprocess
from .gumtree_utils import ensure_gumtree_available

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
    gumtree_path = ensure_gumtree_available()
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
