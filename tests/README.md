# PyMonitor Tests

This directory contains unit tests for the PyMonitor package.

## Test Structure

- `test_db_operations.py`: Tests for the `DatabaseManager` class in `db_operations.py`, focusing on the object versioning system.
- `run_tests.py`: A simple test runner script that discovers and runs all tests in this directory.

## Running the Tests

You can run the tests using the `run_tests.py` script:

```bash
python tests/run_tests.py
```

Or you can use the standard Python unittest module:

```bash
python -m unittest discover tests
```

## Test Database

The tests use an in-memory SQLite database, which is created and destroyed for each test. This ensures that the tests are isolated and do not affect any existing databases.

## Test Coverage

The tests cover the following functionality:

1. **Object Hashing**: Testing the methods that generate hashes for objects and object identities.
2. **Object Storage**: Testing the methods that store objects in the database.
3. **Object Versioning**: Testing the methods that create and manage object versions.
4. **Function Call Data**: Testing the methods that store and retrieve function call data, including local variables, global variables, and return values.
5. **Complex Objects**: Testing the versioning of complex objects with nested structures.
6. **Custom Classes**: Testing the versioning of custom class objects.

## Adding New Tests

To add new tests, create a new test file in this directory with a name starting with `test_`. The test runner will automatically discover and run these tests.

Each test file should import the necessary modules and define a test class that inherits from `unittest.TestCase`. The test class should define test methods that start with `test_`.

Example:

```python
import unittest
from src.monitoringpy.some_module import SomeClass

class TestSomeClass(unittest.TestCase):
    def test_some_method(self):
        # Test code here
        self.assertEqual(expected, actual)

if __name__ == '__main__':
    unittest.main() 