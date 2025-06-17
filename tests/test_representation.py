#!/usr/bin/env python3
"""
Unit tests for the object representation and storage system.
"""

import unittest
import sys
import os
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from monitoringpy.core.models import Base, init_db, StoredObject, ObjectIdentity
from monitoringpy.core.representation import ObjectManager, ObjectType, Primitive, List, DictObject, CustomClass

class TestClass:
    def __init__(self, value):
        self.value = value

class TestObjectManager(unittest.TestCase):
    """Test cases for the ObjectManager class."""
    
    def setUp(self):
        """Set up an in-memory SQLite database for testing."""
        # Create an in-memory SQLite database
        self.engine = create_engine('sqlite:///:memory:')
        
        # Create all tables
        Base.metadata.create_all(self.engine)
        
        # Create a session factory with expire_on_commit=False to prevent detached instance errors
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        
        # Create a session and ObjectManager instance
        self.session = self.Session()
        self.manager = ObjectManager(self.session)
    
    def tearDown(self):
        """Clean up after each test."""
        self.session.close()

    def test_primitive_storage(self):
        """Test storing and retrieving primitive values."""
        # Test integer
        x = 42
        ref = self.manager.store(x)
        self.assertEqual(self.manager.get(ref), 42)
        
        # Test float
        y = 3.14
        ref = self.manager.store(y)
        self.assertEqual(self.manager.get(ref), 3.14)
        
        # Test string
        z = "hello"
        ref = self.manager.store(z)
        self.assertEqual(self.manager.get(ref), "hello")
        
        # Test boolean
        b = True
        ref = self.manager.store(b)
        self.assertEqual(self.manager.get(ref), True)
        
        # Test None
        n = None
        ref = self.manager.store(n)
        self.assertIsNone(self.manager.get(ref))

    def test_list_versioning(self):
        """Test versioning of list objects."""
        # Create initial list
        a = [1, 2, 3]
        ref1 = self.manager.store(a)
        self.assertEqual(self.manager.get(ref1), [1, 2, 3])
        
        # Modify list
        a.append(5)
        ref2 = self.manager.store(a)
        self.assertEqual(self.manager.get(ref2), [1, 2, 3, 5])
        
        # Store same state again
        ref3 = self.manager.store(a)
        self.assertEqual(ref2, ref3)  # Should get same ref for identical state
        
        # Modify list again
        a[0] = 9
        ref4 = self.manager.store(a)
        self.assertEqual(self.manager.get(ref4), [9, 2, 3, 5])
        
        # Check version history
        history = self.manager.get_history(ref1)
        self.assertEqual(len(history), 3)  # Three unique versions
        self.assertEqual(history[0], ref1)  # First version
        self.assertEqual(history[1], ref2)  # Second version
        self.assertEqual(history[2], ref4)  # Latest version
        
        # Check next_ref
        self.assertEqual(self.manager.next_ref(ref1), ref2)
        self.assertEqual(self.manager.next_ref(ref2), ref4)
        self.assertIsNone(self.manager.next_ref(ref4))

    def test_dict_versioning(self):
        """Test versioning of dictionary objects."""
        # Create initial dict
        d = {"a": 1, "b": 2}
        ref1 = self.manager.store(d)
        self.assertEqual(self.manager.get(ref1), {"a": 1, "b": 2})
        
        # Modify dict
        d["c"] = 3
        ref2 = self.manager.store(d)
        self.assertEqual(self.manager.get(ref2), {"a": 1, "b": 2, "c": 3})
        
        # Store same state again
        ref3 = self.manager.store(d)
        self.assertEqual(ref2, ref3)  # Should get same ref for identical state
        
        # Modify dict again
        d["a"] = 9
        ref4 = self.manager.store(d)
        self.assertEqual(self.manager.get(ref4), {"a": 9, "b": 2, "c": 3})
        
        # Check version history
        history = self.manager.get_history(ref1)
        self.assertEqual(len(history), 3)  # Three unique versions
        self.assertEqual(history[0], ref1)  # First version
        self.assertEqual(history[1], ref2)  # Second version
        self.assertEqual(history[2], ref4)  # Latest version
        
        # Check next_ref
        self.assertEqual(self.manager.next_ref(ref1), ref2)
        self.assertEqual(self.manager.next_ref(ref2), ref4)
        self.assertIsNone(self.manager.next_ref(ref4))

    def test_custom_class_versioning(self):
        """Test versioning of custom class objects."""
        # Create initial object
        obj = TestClass(42)
        ref1 = self.manager.store(obj)
        retrieved = self.manager.get(ref1)
        self.assertIsNotNone(retrieved)
        if retrieved is not None:
            self.assertEqual(retrieved.value, 42)
        
        # Modify object
        obj.value = 43
        ref2 = self.manager.store(obj)
        retrieved = self.manager.get(ref2)
        self.assertIsNotNone(retrieved)
        if retrieved is not None:
            self.assertEqual(retrieved.value, 43)
        
        # Store same state again
        ref3 = self.manager.store(obj)
        self.assertEqual(ref2, ref3)  # Should get same ref for identical state
        
        # Modify object again
        obj.value = 44
        ref4 = self.manager.store(obj)
        retrieved = self.manager.get(ref4)
        self.assertIsNotNone(retrieved)
        if retrieved is not None:
            self.assertEqual(retrieved.value, 44)
        
        # Check version history
        history = self.manager.get_history(ref1)
        self.assertEqual(len(history), 3)  # Three unique versions
        self.assertEqual(history[0], ref1)  # First version
        self.assertEqual(history[1], ref2)  # Second version
        self.assertEqual(history[2], ref4)  # Latest version
        
        # Check next_ref
        self.assertEqual(self.manager.next_ref(ref1), ref2)
        self.assertEqual(self.manager.next_ref(ref2), ref4)
        self.assertIsNone(self.manager.next_ref(ref4))

        # retrieve an old version and load it
        old_version = self.manager.get_history(ref1)[0]
        loaded = self.manager.get(old_version)
        self.assertIsNotNone(loaded)
        if loaded is not None:
            self.assertEqual(loaded.value, 42)

    def test_error_cases(self):
        """Test error cases and invalid inputs"""
        # Test invalid primitive type
        with self.assertRaises(TypeError):
            # type: ignore
            Primitive([1, 2, 3])  # Should raise TypeError for non-primitive

        # Test invalid list type
        with self.assertRaises(TypeError):
            # type: ignore
            List("not a list")  # Should raise TypeError for non-list

        # Test invalid dict type
        with self.assertRaises(TypeError):
            # type: ignore
            DictObject("not a dict")  # Should raise TypeError for non-dict

        # Test invalid custom class type
        with self.assertRaises(TypeError):
            # type: ignore
            CustomClass([1, 2, 3])  # Should raise TypeError for primitive/structured type

        # Test non-existent reference
        self.assertIsNone(self.manager.get("non_existent_ref"))
        self.assertIsNone(self.manager.next_ref("non_existent_ref"))
        self.assertEqual(self.manager.get_history("non_existent_ref"), [])

if __name__ == '__main__':
    unittest.main(failfast=True) 