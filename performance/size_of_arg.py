#!/usr/bin/env python3
import json
import time
import string
import itertools
import matplotlib.pyplot as plt
import seaborn as sns
import tqdm
import sys

import spacetimepy

def name_generator(size):
    """Generate all name of given size using alphabetic lowercase letters."""
    alphabet = string.ascii_lowercase
    for name_tuple in itertools.product(alphabet, repeat=size):
        yield "".join(name_tuple)


def custom_args_nm(*args, **kwargs):
    pass

@spacetimepy.pymonitor(mode="function")
def custom_args_m(*args, **kwargs):
    pass


if __name__ == "__main__":
    spacetimepy.init_monitoring(db_path="main2.db", performance=True)
    size = []
    times1 = []
    times2 = []

    for arg_n in tqdm.trange(1, 10000):
        arg = {name: i for i, name in itertools.islice(enumerate(name_generator(8)), arg_n)}

        t1 = time.perf_counter_ns()
        custom_args_m(arg)
        t2 = time.perf_counter_ns()

        del arg


        size.append(sys.getsizeof(arg))
        times1.append((t2 - t1) / 1_000_000_000)

    for arg_n in tqdm.trange(1, 10000):
        arg = {name: i for i, name in itertools.islice(enumerate(name_generator(8)), arg_n)}


        t3 = time.perf_counter_ns()
        custom_args_nm(arg)
        t4 = time.perf_counter_ns()

        del arg

        times2.append((t4 - t3) / 1_000_000_000)

    plt.scatter(size, times1, color='blue', label='With Monitoring')
    plt.scatter(size, times2, color='orange',label='Without Monitoring')
    plt.title('Custom Args Function Call Overhead\n(Function-level Monitoring)')
    plt.xlabel('Size of Argument (bytes)')
    plt.ylabel('Time (seconds)')
    plt.grid(True, alpha=0.3) 
    plt.legend()
    plt.show()
