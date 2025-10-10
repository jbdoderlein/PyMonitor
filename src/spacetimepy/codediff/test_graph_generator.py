import pytest

from spacetimepy.codediff.graph_generator import (
    generate_edit_graph,
    generate_graph,
    generate_line_mapping_from_string,
)


@pytest.fixture
def sample_traces():
    return {
        "trace1": [
            (6, {}),
            (7, {"i": 10}),
            (8, {"i": 10, "j": 8}),
            (9, {"i": 10, "j": 8}),
            (12, {"i": 10, "j": 50}),
        ],
        "trace2": [
            (6, {}),
            (7, {"i": 5}),
            (8, {"i": 5, "j": 8}),
            (11, {"i": 5, "j": 8}),
            (12, {"i": 5, "j": 6}),
        ],
        "trace3": [
            (6, {}),
            (7, {"i": 5}),
            (8, {"i": 5}),
            (9, {"i": 6}),
            (8, {"i": 6}),
            (9, {"i": 7}),
            (8, {"i": 7}),
            (10, {"i": 7}),
        ],
    }


@pytest.fixture
def sample_code():
    return {
        "trace1": """def bar():
    return 42


def foo():
    i = 10
    j = 8
    if i > j:
        j+=bar()
    else:
        j-=2
    return i + j
""",
        "trace2": """def bar():
    return 42


def foo():
    i = 5
    j = 8
    if i > j:
        j+=bar()
    else:
        j-=2
    return i + j
""",
        "trace3": """
def foo():
    i = 5
    pass
    while i < 8:
        i += 1
    return i
""",
    }



class TestGenerateGraph:
    def test_linear_trace(self, sample_traces):
        trace = sample_traces["trace1"]
        graph = generate_graph(trace)
        node_id = list(graph.nodes)
        assert graph.nodes[node_id[0]]["line"] == 6
        assert graph.nodes[node_id[1]]["line"] == 7
        assert graph.nodes[node_id[2]]["line"] == 8
        assert graph.nodes[node_id[3]]["line"] == 9
        assert graph.nodes[node_id[4]]["line"] == 12

        assert graph.nodes[node_id[0]]["vars"] == [{}]
        assert graph.nodes[node_id[1]]["vars"] == [{"i": 10}]
        assert graph.nodes[node_id[2]]["vars"] == [{"i": 10, "j": 8}]
        assert graph.nodes[node_id[3]]["vars"] == [{"i": 10, "j": 8}]
        assert graph.nodes[node_id[4]]["vars"] == [{"i": 10, "j": 50}]

        assert graph.edges[node_id[0], node_id[1]]["diff"] == [{"i": (None, 10)}]
        assert graph.edges[node_id[1], node_id[2]]["diff"] == [{"j": (None, 8)}]
        assert graph.edges[node_id[2], node_id[3]]["diff"] == [{}]
        assert graph.edges[node_id[3], node_id[4]]["diff"] == [{"j": (8, 50)}]

    def test_loop_trace(self, sample_traces):
        trace = sample_traces["trace3"]
        graph = generate_graph(trace)
        print(graph.nodes(data=True))
        node_id = list(graph.nodes)
        assert graph.nodes[node_id[0]]["line"] == 6
        assert graph.nodes[node_id[1]]["line"] == 7
        assert graph.nodes[node_id[2]]["line"] == 8
        assert graph.nodes[node_id[3]]["line"] == 9
        assert graph.nodes[node_id[4]]["line"] == 10

        assert graph.nodes[node_id[0]]["vars"] == [{}]
        assert graph.nodes[node_id[1]]["vars"] == [{"i": 5}]
        assert graph.nodes[node_id[2]]["vars"] == [{"i": 5}, {"i": 6}, {"i": 7}]
        assert graph.nodes[node_id[3]]["vars"] == [{"i": 6}, {"i": 7}]
        assert graph.nodes[node_id[4]]["vars"] == [{"i": 7}]

        assert graph.edges[node_id[0], node_id[1]]["diff"] == [{"i": (None, 5)}]
        assert graph.edges[node_id[1], node_id[2]]["diff"] == [{}]
        assert graph.edges[node_id[2], node_id[3]]["diff"] == [
            {"i": (5, 6)},
            {"i": (6, 7)},
        ]
        assert graph.edges[node_id[2], node_id[4]]["diff"] == [{}]


class TestGenerateEditGraph:
    def test_graph_diff(self, sample_traces, sample_code):
        g1 = generate_graph(sample_traces["trace1"])
        g2 = generate_graph(sample_traces["trace2"])
        mapping_v1_to_v2, mapping_v2_to_v1, modified_lines = (
            generate_line_mapping_from_string(
                sample_code["trace1"], sample_code["trace2"]
            )
        )
        print(mapping_v1_to_v2)
        print(mapping_v2_to_v1)
        print(modified_lines)
        edit_graph = generate_edit_graph(
            g1, g2, mapping_v1_to_v2, mapping_v2_to_v1, modified_lines
        )
        print(edit_graph.nodes(data=True))
        print(edit_graph.edges(data=True))
        # Check that there exists a node for each expected line1 value
        expected_lines1 = {6, 7, 8, 9, 12}
        expected_lines2 = {6, 7, 8, 11, 12}
        actual_lines1 = {data["line1"] for _, data in edit_graph.nodes(data=True) if "line1" in data}
        actual_lines2 = {data["line2"] for _, data in edit_graph.nodes(data=True) if "line2" in data}
        for line in expected_lines1:
            assert line in actual_lines1, f"Missing node for line1={line}"
        for line in expected_lines2:
            assert line in actual_lines2, f"Missing node for line2={line}"

