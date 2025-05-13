#!/usr/bin/env python3
"""
Basic example demonstrating PyMonitor.
"""
import monitoringpy
import random

class MyCustomClass:
    """A simple custom class with attributes."""
    def __init__(self, x):
        self.x = x
        self.y = 5
        
    def __repr__(self):
        return f"CustomClass(x={self.x}, y={self.y})"

    def rep(self):
        """Return the sum of x and y."""
        return self.x + self.y

# Create a global instance
custom_class_1 = MyCustomClass(10)
imbricated_list = [[1,2,3], [4,5,6]]

@monitoringpy.pymonitor(mode="line")
def foo1(x, cl):
    """A simple function that uses custom objects."""
    a = imbricated_list[0][0]
    for i in range(10*x):
        a += cl.rep() + i + custom_class_1.rep()
    return a

def get_event():
    """A function that could be used for effects"""
    return {"type": "event", "data": random.randint(0, 100)}

@monitoringpy.pymonitor(mode="function",
                        return_hooks=[lambda m,c,o,r: {"custom_return_metric": r+1}],
                        start_hooks=[lambda m,c,o: {"custom_start_metric": 1}],
                        track=[get_event])
def complex_function(x):
    """A function that uses custom objects and could be used for effects"""
    y = 1
    z = x + y + get_event()["data"]
    z += get_event()["data"]
    return z

if __name__ == "__main__":
    # Initialize monitoring
    monitoringpy.init_monitoring(db_path="main1.db")
    with monitoringpy.session_context(name="main1"):
        foo1(10, custom_class_1)
        complex_function(10)
        complex_function(15)
    