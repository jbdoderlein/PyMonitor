import pandas as pd
import os

df = pd.read_parquet("humanevalplus.parquet")

# create dir humaneval_data
current_path = os.path.dirname(os.path.abspath(__file__))
humaneval_data_path = os.path.join(current_path, "humaneval_data")
os.makedirs(humaneval_data_path, exist_ok=True)
reference_path = os.path.join(humaneval_data_path, "reference")
os.makedirs(reference_path, exist_ok=True)
monitoring_line_path = os.path.join(humaneval_data_path, "monitoring_line")
os.makedirs(monitoring_line_path, exist_ok=True)
monitoring_function_path = os.path.join(humaneval_data_path, "monitoring_function")
os.makedirs(monitoring_function_path, exist_ok=True)

REFERENCE_CHECK = """
data = []
entry_point = {entry_point}
def tester(*args, **kwargs):
    global data
    t1 = time.perf_counter_ns()
    result = entry_point(*args, **kwargs)
    t2 = time.perf_counter_ns()
    data.append(t2 - t1)
    return result

check(tester)
print(data)
"""

MONITORING_LINE_CHECK = """
data = []
entry_point = pymonitor('line')({entry_point})
def tester(*args, **kwargs):
    global data
    t1 = time.perf_counter_ns()
    result = entry_point(*args, **kwargs)
    t2 = time.perf_counter_ns()
    data.append(t2 - t1)
    return result

check(tester)
print(data)
"""

MONITORING_FUNCTION_CHECK = """
data = []
entry_point = pymonitor('function')({entry_point})
def tester(*args, **kwargs):
    global data
    t1 = time.perf_counter_ns()
    result = entry_point(*args, **kwargs)
    t2 = time.perf_counter_ns()
    data.append(t2 - t1)
    return result

check(tester)
print(data)
"""
    

# for each line in parquet create a file with inside the content of "canonical_solution" followed by "test"
for index, row in df.iterrows():
    print(index)
    with open(os.path.join(reference_path, f"{index}.py"), "w") as f:
        f.write("import time\n")
        f.write(row["prompt"])
        f.write(row["canonical_solution"])
        f.write(row["test"])
        f.write(REFERENCE_CHECK.format(entry_point=row['entry_point']))

    with open(os.path.join(monitoring_line_path, f"{index}.py"), "w") as f:
        f.write("import time\n")
        f.write(f"""from spacetimepy import pymonitor,init_monitoring
init_monitoring(db_path="{index}.db")
""")
        f.write(row["prompt"])
        f.write(row["canonical_solution"])
        f.write(row["test"])
        f.write(MONITORING_LINE_CHECK.format(entry_point=row['entry_point']))

    with open(os.path.join(monitoring_function_path, f"{index}.py"), "w") as f:
        f.write("import time\n")
        f.write(f"""from spacetimepy import pymonitor,init_monitoring
init_monitoring(db_path="{index}.db")
""")
        f.write(row["prompt"])
        f.write(row["canonical_solution"])
        f.write(row["test"])
        f.write(MONITORING_FUNCTION_CHECK.format(entry_point=row['entry_point']))



