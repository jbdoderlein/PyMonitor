#!/usr/bin/env python3
"""
Basic example demonstrating custom object handling in PyMonitor.
"""

import os
import monitoringpy

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
gcl = MyCustomClass(10)
ncl = [[1,2,3], [4,5,6]]

@monitoringpy.pymonitor
def linear_function(x, cl):
    """A simple function that uses custom objects."""
    a = ncl[0][0]
    for i in range(100*x):
        a += cl.rep() + i + gcl.rep()
    return a

if __name__ == "__main__":

    # Initialize monitoring
    monitor = monitoringpy.init_monitoring(db_path="basic.db", pyrapl_enabled=True)
    
    # Run the function with a custom object
    for i in range(5):
        cl = MyCustomClass(i)
        linear_function(100*i, cl)
    
    gcl.x = 100
    linear_function(100*i, cl)
    
    
    