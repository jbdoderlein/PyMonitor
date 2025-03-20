import unittest
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from monitoringpy.models import Base, init_db
from monitoringpy.function_call import FunctionCallTracker, FunctionCallInfo

class TestClass:
    def __init__(self, value):
        self.value = value

class TestFunctionCallTracker(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite database for testing
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.tracker = FunctionCallTracker(self.session)

    def tearDown(self):
        self.session.close()

    def test_simple_function_call(self):
        def test_func(x, y):
            a = x + y  # local variable
            return a

        # Capture function call
        x, y = 5, 3
        call_id = self.tracker.capture_call('test_func', {'x': x, 'y': y, 'a': 8}, {})
        self.tracker.capture_return(call_id, 8)

        # Get call info
        call_info: FunctionCallInfo = self.tracker.get_call(call_id)
        
        # Check basic info
        self.assertEqual(call_info['function'], 'test_func')
        self.assertIsNotNone(call_info['file'])
        self.assertIsNotNone(call_info['line'])
        
        # Check variables
        self.assertEqual(call_info['locals']['x'], 5)
        self.assertEqual(call_info['locals']['y'], 3)
        self.assertEqual(call_info['locals']['a'], 8)
        self.assertEqual(call_info['return_value'], 8)

    def test_complex_objects(self):
        def test_func(lst, obj):
            lst.append(42)
            obj.value += 1
            return lst, obj

        # Create test objects
        test_list = [1, 2, 3]
        test_obj = TestClass(10)

        # Capture function call
        test_list.append(42)  # Modify list before storing
        test_obj.value += 1   # Modify object before storing
        locals_dict = {'lst': test_list, 'obj': test_obj}
        call_id = self.tracker.capture_call('test_func', locals_dict, {})
        
        # Return the modified objects
        self.tracker.capture_return(call_id, (test_list, test_obj))

        # Get call info
        call_info: FunctionCallInfo = self.tracker.get_call(call_id)
        
        # Check input variables
        stored_list = call_info['locals']['lst']
        self.assertEqual(stored_list, [1, 2, 3, 42])
        
        stored_obj = call_info['locals']['obj']
        self.assertEqual(stored_obj.value, 11)
        
        # Check return value
        return_value = call_info['return_value']
        self.assertIsNotNone(return_value)  # Ensure return value exists
        if return_value is not None:  # Type guard for mypy
            ret_list, ret_obj = return_value
            self.assertEqual(ret_list, [1, 2, 3, 42])
            self.assertEqual(ret_obj.value, 11)

    def test_globals(self):
        global_var = {'key': 'value'}
        
        def test_func():
            return global_var['key']

        # Capture function call with globals
        call_id = self.tracker.capture_call('test_func', {}, {'global_var': global_var})
        self.tracker.capture_return(call_id, 'value')

        # Get call info
        call_info: FunctionCallInfo = self.tracker.get_call(call_id)
        
        # Check globals were stored
        self.assertEqual(call_info['globals']['global_var'], {'key': 'value'})
        self.assertEqual(call_info['return_value'], 'value')

    def test_call_history(self):
        def func1(): pass
        def func2(): pass

        # Create multiple function calls
        call1 = self.tracker.capture_call('func1', {}, {})
        self.tracker.capture_return(call1, None)
        
        call2 = self.tracker.capture_call('func2', {}, {})
        self.tracker.capture_return(call2, None)
        
        call3 = self.tracker.capture_call('func1', {}, {})
        self.tracker.capture_return(call3, None)

        # Get all calls
        all_calls = self.tracker.get_call_history()
        self.assertEqual(len(all_calls), 3)
        
        # Get calls for specific function
        func1_calls = self.tracker.get_call_history('func1')
        self.assertEqual(len(func1_calls), 2)
        
        func2_calls = self.tracker.get_call_history('func2')
        self.assertEqual(len(func2_calls), 1)

    def test_error_handling(self):
        # Test non-existent call ID
        with self.assertRaises(ValueError):
            self.tracker.capture_return('999', None)

        # Test getting non-existent call
        with self.assertRaises(ValueError):
            self.tracker.get_call('999')

        # Test storing unstoreable object
        def test_func():
            pass  # Function objects can't be pickled by default
        
        call_id = self.tracker.capture_call('test_func', {'func': test_func}, {})
        # Should not raise exception, but func won't be in locals
        call_info: FunctionCallInfo = self.tracker.get_call(call_id)
        self.assertEqual(call_info['locals'], {})

if __name__ == '__main__':
    unittest.main() 