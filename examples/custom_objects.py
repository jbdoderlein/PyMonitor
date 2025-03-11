#!/usr/bin/env python3
"""
Custom Objects Example for PyMonitor

This example demonstrates how PyMonitor handles custom objects,
including nested objects, inheritance, and various data structures.
"""

import monitoringpy
import datetime
import json

# Simple custom class
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def distance_from_origin(self):
        return (self.x**2 + self.y**2)**0.5
    
    def __str__(self):
        return f"Point({self.x}, {self.y})"

# Class with nested objects
class Rectangle:
    def __init__(self, top_left, bottom_right):
        self.top_left = top_left
        self.bottom_right = bottom_right
        self.width = bottom_right.x - top_left.x
        self.height = top_left.y - bottom_right.y
    
    def area(self):
        return self.width * self.height
    
    def __str__(self):
        return f"Rectangle({self.top_left}, {self.bottom_right})"

# Class with inheritance
class ColoredPoint(Point):
    def __init__(self, x, y, color):
        super().__init__(x, y)
        self.color = color
    
    def __str__(self):
        return f"ColoredPoint({self.x}, {self.y}, {self.color})"

# Class with various data types
class DataContainer:
    def __init__(self, name):
        self.name = name
        self.created_at = datetime.datetime.now()
        self.data = {
            "numbers": [1, 2, 3, 4, 5],
            "text": "Sample text",
            "nested": {
                "a": 1,
                "b": 2
            },
            "boolean": True,
            "none_value": None
        }
        self.tags = ["sample", "test", "example"]
    
    def to_json(self):
        data_copy = self.data.copy()
        data_copy["created_at"] = self.created_at.isoformat()
        return json.dumps(data_copy)
    
    def __str__(self):
        return f"DataContainer({self.name})"

# Function that uses custom objects
@monitoringpy.pymonitor
def process_objects(point, rectangle, data_container):
    """Process various custom objects and return a summary"""
    
    # Create some local objects
    colored_point = ColoredPoint(point.x * 2, point.y * 2, "red")
    
    # Perform some calculations
    distance = point.distance_from_origin()
    area = rectangle.area()
    
    # Create a dictionary with results
    results = {
        "point_distance": distance,
        "rectangle_area": area,
        "colored_point": str(colored_point),
        "data_container_name": data_container.name,
        "data_container_created_at": data_container.created_at.isoformat(),
        "tags": data_container.tags
    }
    
    return results

# Function that creates and manipulates custom objects
@monitoringpy.pymonitor
def create_and_process_shapes(num_shapes):
    """Create and process multiple shapes"""
    
    shapes = []
    for i in range(num_shapes):
        # Create points with increasing coordinates
        point = Point(i, i*2)
        
        # Create rectangles using the points
        top_left = Point(i, i*3)
        bottom_right = Point(i*2, i)
        rectangle = Rectangle(top_left, bottom_right)
        
        # Add to shapes list
        shapes.append({
            "point": point,
            "rectangle": rectangle,
            "area": rectangle.area()
        })
    
    # Process the shapes
    total_area = sum(shape["area"] for shape in shapes)
    max_area = max(shape["area"] for shape in shapes)
    min_area = min(shape["area"] for shape in shapes)
    
    return {
        "shapes": shapes,
        "total_area": total_area,
        "max_area": max_area,
        "min_area": min_area,
        "average_area": total_area / num_shapes if num_shapes > 0 else 0
    }

if __name__ == "__main__":
    # Initialize monitoring
    monitoringpy.init_monitoring(db_path="custom_objects.db")
    
    print("Running custom objects example...")
    
    # Create some objects
    point = Point(3, 4)
    top_left = Point(0, 10)
    bottom_right = Point(5, 0)
    rectangle = Rectangle(top_left, bottom_right)
    data_container = DataContainer("test_container")
    
    # Process the objects
    result1 = process_objects(point, rectangle, data_container)
    print(f"Process objects result: {result1}")
    
    # Create and process shapes
    result2 = create_and_process_shapes(5)
    print(f"Created and processed {len(result2['shapes'])} shapes")
    print(f"Total area: {result2['total_area']}")
    
    print("Example completed. Check the database for results.")
    print("You can view the results using the web explorer:")
    print("python -m monitoringpy.web_explorer custom_objects.db") 