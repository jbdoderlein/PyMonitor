import unittest
import sys
import os
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Add the src directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from monitoringpy.models import Base, StoredObject, ObjectVersion, ObjectIdentity
from monitoringpy.representation import ObjectManager, ObjectType, Primitive, List, DictObject, CustomClass

# Define test class outside of test method
class TestClass:
    def __init__(self, value):
        self.value = value

class TestObjectManager(unittest.TestCase):
    def setUp(self):
        """Set up test database"""
        # Create in-memory SQLite database
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()
        self.manager = ObjectManager(self.session)

    def tearDown(self):
        """Clean up after each test"""
        self.session.close()

    def test_primitive_storage(self):
        """Test storing and retrieving primitive values"""
        # Test integer
        x = 42
        ref = self.manager.store(x)
        self.assertEqual(self.manager.get(ref), 42)

        # Test float
        y = 3.14
        ref = self.manager.store(y)
        self.assertEqual(self.manager.get(ref), 3.14)

        # Test string
        s = "hello"
        ref = self.manager.store(s)
        self.assertEqual(self.manager.get(ref), "hello")

        # Test boolean
        b = True
        ref = self.manager.store(b)
        self.assertEqual(self.manager.get(ref), True)

        # Test None
        n = None
        ref = self.manager.store(n)
        self.assertEqual(self.manager.get(ref), None)

    def test_list_versioning(self):
        """Test versioning of list objects"""
        # Create and store initial list
        a = [1, 2, 3]
        ref1 = self.manager.store(a)
        self.assertEqual(self.manager.get(ref1), [1, 2, 3])

        # Modify and store new version
        a.append(5)
        ref2 = self.manager.store(a)
        self.assertEqual(self.manager.get(ref2), [1, 2, 3, 5])

        # Store identical state (should reuse ref2)
        ref3 = self.manager.store(a)
        self.assertEqual(ref2, ref3)

        # Modify and store another version
        a[0] = 9
        ref4 = self.manager.store(a)
        self.assertEqual(self.manager.get(ref4), [9, 2, 3, 5])

        # Test version history
        history = self.manager.get_history(ref1)
        self.assertEqual(len(history), 3)  # Three unique versions
        self.assertEqual(self.manager.get(history[0]), [1, 2, 3])
        self.assertEqual(self.manager.get(history[1]), [1, 2, 3, 5])
        self.assertEqual(self.manager.get(history[2]), [9, 2, 3, 5])

        # Test next_ref functionality
        self.assertEqual(self.manager.next_ref(ref1), ref2)
        self.assertEqual(self.manager.next_ref(ref2), ref4)
        self.assertIsNone(self.manager.next_ref(ref4))

    def test_dict_versioning(self):
        """Test versioning of dictionary objects"""
        # Create and store initial dict
        d = {"a": 1, "b": 2}
        ref1 = self.manager.store(d)
        self.assertEqual(self.manager.get(ref1), {"a": 1, "b": 2})

        # Modify and store new version
        d["c"] = 3
        ref2 = self.manager.store(d)
        self.assertEqual(self.manager.get(ref2), {"a": 1, "b": 2, "c": 3})

        # Store identical state (should reuse ref2)
        ref3 = self.manager.store(d)
        self.assertEqual(ref2, ref3)

        # Modify and store another version
        d["a"] = 10
        ref4 = self.manager.store(d)
        self.assertEqual(self.manager.get(ref4), {"a": 10, "b": 2, "c": 3})

        # Test version history
        history = self.manager.get_history(ref1)
        self.assertEqual(len(history), 3)  # Three unique versions
        self.assertEqual(self.manager.get(history[0]), {"a": 1, "b": 2})
        self.assertEqual(self.manager.get(history[1]), {"a": 1, "b": 2, "c": 3})
        self.assertEqual(self.manager.get(history[2]), {"a": 10, "b": 2, "c": 3})

        # Test next_ref functionality
        self.assertEqual(self.manager.next_ref(ref1), ref2)
        self.assertEqual(self.manager.next_ref(ref2), ref4)
        self.assertIsNone(self.manager.next_ref(ref4))

    def test_custom_class_versioning(self):
        """Test versioning of custom class objects"""
        # Create and store initial object
        obj = TestClass(42)
        ref1 = self.manager.store(obj)
        retrieved = self.manager.get(ref1)
        self.assertIsNotNone(retrieved)
        if retrieved is not None:
            self.assertEqual(retrieved.value, 42)

        # Modify and store new version
        obj.value = 43
        ref2 = self.manager.store(obj)
        retrieved = self.manager.get(ref2)
        self.assertIsNotNone(retrieved)
        if retrieved is not None:
            self.assertEqual(retrieved.value, 43)

        # Store identical state (should reuse ref2)
        ref3 = self.manager.store(obj)
        self.assertEqual(ref2, ref3)

        # Modify and store another version
        obj.value = 44
        ref4 = self.manager.store(obj)
        retrieved = self.manager.get(ref4)
        self.assertIsNotNone(retrieved)
        if retrieved is not None:
            self.assertEqual(retrieved.value, 44)

        # Test version history
        history = self.manager.get_history(ref1)
        self.assertEqual(len(history), 3)  # Three unique versions

        # Test next_ref functionality
        self.assertEqual(self.manager.next_ref(ref1), ref2)
        self.assertEqual(self.manager.next_ref(ref2), ref4)
        self.assertIsNone(self.manager.next_ref(ref4))

    def test_error_cases(self):
        """Test error cases and invalid inputs"""
        # Test invalid primitive type
        with self.assertRaises(TypeError):
            Primitive([1, 2, 3])  # Should raise TypeError for non-primitive

        # Test invalid list type
        with self.assertRaises(TypeError):
            List("not a list")  # Should raise TypeError for non-list

        # Test invalid dict type
        with self.assertRaises(TypeError):
            DictObject("not a dict")  # Should raise TypeError for non-dict

        # Test invalid custom class type
        with self.assertRaises(TypeError):
            CustomClass([1, 2, 3])  # Should raise TypeError for primitive/structured type

        # Test non-existent reference
        self.assertIsNone(self.manager.get("non_existent_ref"))
        self.assertIsNone(self.manager.next_ref("non_existent_ref"))
        self.assertEqual(self.manager.get_history("non_existent_ref"), [])

if __name__ == '__main__':
    unittest.main() 