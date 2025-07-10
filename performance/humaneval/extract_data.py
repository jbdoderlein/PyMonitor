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


    
    

# for each line in parquet create a file with inside the content of "canonical_solution" followed by "test"
for index, row in df.iterrows():
    print(index)
    with open(os.path.join(reference_path, f"{index}.py"), "w") as f:
        f.write(row["prompt"])
        f.write(row["canonical_solution"])
        f.write(row["test"])
        f.write(f"\n\ncheck({row['entry_point']})\n")

    with open(os.path.join(monitoring_line_path, f"{index}.py"), "w") as f:
        f.write(f"""from monitoringpy import pymonitor,init_monitoring
init_monitoring(db_path="{index}.db")
""")
        f.write(row["prompt"])
        f.write(row["canonical_solution"])
        f.write(row["test"])
        f.write(f"\n\ncheck(pymonitor('line')({row['entry_point']}))\n")

    with open(os.path.join(monitoring_function_path, f"{index}.py"), "w") as f:
        f.write(f"""from monitoringpy import pymonitor,init_monitoring
init_monitoring(db_path="{index}.db")
""")
        f.write(row["prompt"])
        f.write(row["canonical_solution"])
        f.write(row["test"])
        f.write(f"\n\ncheck(pymonitor('function')({row['entry_point']}))\n")



