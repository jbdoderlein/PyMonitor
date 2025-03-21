#!/usr/bin/env python3
"""
Unit tests for the DatabaseManager class in db_operations.py.
These tests focus on the object versioning system and use an in-memory SQLite database.
"""

import unittest
import datetime
import sys
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add the parent directory to the path so we can import the package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.monitoringpy.models import init_db, Base, FunctionCall, Object, ObjectAttribute, ObjectItem, ObjectIdentity, ObjectVersion
from src.monitoringpy.db_operations import DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define test classes at the module level to avoid pickle errors
class TestClass:
    """A simple test class for testing object serialization."""
    def __init__(self, value):
        self.value = value
        self.name = "test"
    
    def __str__(self):
        return f"TestClass(value={self.value}, name={self.name})"

class TestDatabaseManager(unittest.TestCase):
    """Test cases for the DatabaseManager class."""
    
    def setUp(self):
        """Set up an in-memory SQLite database for testing."""
        # Create an in-memory SQLite database
        self.engine = create_engine('sqlite:///:memory:')
        
        # Create all tables
        Base.metadata.create_all(self.engine)
        
        # Create a session factory with expire_on_commit=False to prevent detached instance errors
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        
        # Create a DatabaseManager instance
        self.db_manager = DatabaseManager(self.Session)
    
    def tearDown(self):
        """Clean up after each test."""
        # Drop all tables
        Base.metadata.drop_all(self.engine)
    
    def test_get_object_hash(self):
        """Test the _get_object_hash method. Should be different if the object is not exactly the same"""
        # Test with primitive types
        int_hash_1 = self.db_manager._get_object_hash(42)
        int_hash_2 = self.db_manager._get_object_hash(42)
        int_hash_3 = self.db_manager._get_object_hash(43)
        self.assertIsInstance(int_hash_1, str)
        self.assertIsInstance(int_hash_2, str)
        self.assertIsInstance(int_hash_3, str)
        self.assertEqual(int_hash_1, int_hash_2)
        self.assertNotEqual(int_hash_1, int_hash_3)
        
        str_hash_1 = self.db_manager._get_object_hash("test")
        str_hash_2 = self.db_manager._get_object_hash("test")
        str_hash_3 = self.db_manager._get_object_hash("test2")
        self.assertIsInstance(str_hash_1, str)
        self.assertIsInstance(str_hash_2, str)
        self.assertIsInstance(str_hash_3, str)
        self.assertEqual(str_hash_1, str_hash_2)
        self.assertNotEqual(str_hash_1, str_hash_3)
        
        bool_hash_1 = self.db_manager._get_object_hash(True)
        bool_hash_2 = self.db_manager._get_object_hash(True)
        bool_hash_3 = self.db_manager._get_object_hash(False)
        self.assertIsInstance(bool_hash_1, str)
        self.assertIsInstance(bool_hash_2, str)
        self.assertIsInstance(bool_hash_3, str)
        self.assertEqual(bool_hash_1, bool_hash_2)
        self.assertNotEqual(bool_hash_1, bool_hash_3)
        
        # Test with structured types
        dict_hash_1 = self.db_manager._get_object_hash({"a": 1, "b": 2})
        dict_hash_2 = self.db_manager._get_object_hash({"a": 1, "b": 2})
        dict_hash_3 = self.db_manager._get_object_hash({"a": 1, "c": 3})
        self.assertIsInstance(dict_hash_1, str)
        self.assertIsInstance(dict_hash_2, str)
        self.assertIsInstance(dict_hash_3, str)
        self.assertEqual(dict_hash_1, dict_hash_2)
        self.assertNotEqual(dict_hash_1, dict_hash_3)
        
        list_hash_1 = self.db_manager._get_object_hash([1, 2, 3])
        list_hash_2 = self.db_manager._get_object_hash([1, 2, 3])
        list_hash_3 = self.db_manager._get_object_hash([1, 2, 4])
        self.assertIsInstance(list_hash_1, str)
        self.assertIsInstance(list_hash_2, str)
        self.assertIsInstance(list_hash_3, str)
        self.assertEqual(list_hash_1, list_hash_2)
        self.assertNotEqual(list_hash_1, list_hash_3)
        
        # Test with custom class
        obj_test_1 = TestClass(42)
        obj_test_2 = TestClass(42)
        obj_test_3 = TestClass(43)
        obj_hash_1 = self.db_manager._get_object_hash(obj_test_1)
        obj_hash_2 = self.db_manager._get_object_hash(obj_test_2)
        obj_hash_3 = self.db_manager._get_object_hash(obj_test_3)
        self.assertIsInstance(obj_hash_1, str)
        self.assertIsInstance(obj_hash_2, str)
        self.assertIsInstance(obj_hash_3, str)
        self.assertNotEqual(obj_hash_1, obj_hash_2)
        self.assertNotEqual(obj_hash_1, obj_hash_3)
        obj_test_1.value = 43
        obj_hash_4 = self.db_manager._get_object_hash(obj_test_1)
        self.assertIsInstance(obj_hash_4, str)
        self.assertNotEqual(obj_hash_1, obj_hash_4)
    
    def test_get_identity_hash(self):
        """Test the _get_identity_hash method."""
        # Test with primitive types
        int_hash_1 = self.db_manager._get_identity_hash(42)
        int_hash_2 = self.db_manager._get_identity_hash(42)
        int_hash_3 = self.db_manager._get_identity_hash(43)
        self.assertIsInstance(int_hash_1, str)
        self.assertIsInstance(int_hash_2, str)
        self.assertIsInstance(int_hash_3, str)
        self.assertEqual(int_hash_1, int_hash_2)
        self.assertNotEqual(int_hash_1, int_hash_3)
        
        # Test with named object
        obj_dict = {"a": 1, "b": 2}
        obj_name = "test_dict"
        dict_hash_1 = self.db_manager._get_identity_hash(obj_dict, obj_name)
        obj_dict["c"] = 3
        dict_hash_2 = self.db_manager._get_identity_hash(obj_dict, obj_name)
        self.assertIsInstance(dict_hash_1, str)
        self.assertIsInstance(dict_hash_2, str)
        self.assertEqual(dict_hash_1, dict_hash_2)
        
        
        # Test that same object with same name gets same identity hash
        obj = TestClass(42)
        hash1 = self.db_manager._get_identity_hash(obj, "test_obj")
        hash2 = self.db_manager._get_identity_hash(obj, "test_obj")
        self.assertIsInstance(hash1, str)
        self.assertIsInstance(hash2, str)
        self.assertEqual(hash1, hash2)
    
    def test_create_object_identity(self):
        """Test the _create_object_identity method."""
        # Create a test object
        test_obj = {"a": 1, "b": 2}
        obj_name = "test_dict"
        
        # Create an identity
        identity, session = self.db_manager._create_object_identity(test_obj, obj_name)
        
        # Check that the identity was created
        self.assertIsNotNone(identity)
        self.assertEqual(identity.name, obj_name)
        
        # Check that the identity can be retrieved from the database
        identity_hash = self.db_manager._get_identity_hash(test_obj, obj_name)
        db_identity = session.query(ObjectIdentity).filter(
            ObjectIdentity.identity_hash == identity_hash
        ).first()
        
        self.assertIsNotNone(db_identity)
        self.assertIsNotNone(identity)  # Ensure identity is not None
        self.assertIsNotNone(db_identity)  # Ensure db_identity is not None
        if identity and db_identity:  # Check both are not None before comparing
            self.assertEqual(db_identity.id, identity.id)
        
        # Clean up
        session.close()
    
    def test_store_object(self):
        """Test the _store_object method."""
        # Create a test object
        test_obj = {"a": 1, "b": 2}
        
        # Create a session
        session = self.Session()
        
        # Store the object
        obj_model = self.db_manager._store_object(test_obj, session)
        assert obj_model is not None
        # Check that the object was stored
        self.assertIsNotNone(obj_model)
        self.assertEqual(obj_model.type_name, "dict")
        self.assertFalse(obj_model.is_primitive)
        
        # Check that the object can be retrieved from the database
        obj_hash = self.db_manager._get_object_hash(test_obj)
        db_obj = session.query(Object).filter(Object.id == obj_hash).first()
        
        self.assertIsNotNone(db_obj)
        self.assertIsNotNone(obj_model)  # Ensure obj_model is not None
        if obj_model and db_obj:  # Check both are not None before comparing
            self.assertEqual(db_obj.id, obj_model.id)
        
        # Check that the object's items were stored
        if obj_model:  # Ensure obj_model is not None
            items = session.query(ObjectItem).filter(ObjectItem.parent_id == obj_model.id).all()
            self.assertEqual(len(items), 2)  # Two items: "a" and "b"
        
        # Clean up
        session.close()
    
    def test_create_object_version(self):
        """Test the _create_object_version method."""
        # Create a test object
        test_obj = {"a": 1, "b": 2}
        obj_name = "test_dict"
        
        # Create an identity
        identity, session = self.db_manager._create_object_identity(test_obj, obj_name)
        
        # Create a version
        version, session = self.db_manager._create_object_version(test_obj, identity, session)
        
        # Check that the version was created
        self.assertIsNotNone(version)
        self.assertIsNotNone(identity)  # Ensure identity is not None
        if identity and version:  # Check both are not None before comparing
            self.assertEqual(version.identity_id, identity.id)
            self.assertEqual(version.version_number, 1)  # First version
        
        # Check that the version can be retrieved from the database
        if version:  # Ensure version is not None
            db_version = session.query(ObjectVersion).filter(
                ObjectVersion.id == version.id
            ).first()
            
            self.assertIsNotNone(db_version)
            if db_version and version:  # Check both are not None before comparing
                self.assertEqual(db_version.id, version.id)
        
        # Clean up
        session.close()
    
    def test_store_object_with_versioning(self):
        """Test the _store_object_with_versioning method."""
        # Create a test object
        test_obj = {"a": 1, "b": 2}
        obj_name = "test_dict"
        
        # Store the object with versioning
        obj_model, version, session = self.db_manager._store_object_with_versioning(test_obj, obj_name)
        
        # Check that the object and version were created
        self.assertIsNotNone(obj_model)
        self.assertIsNotNone(version)
        
        # Store object and version IDs for later comparison
        obj_id = obj_model.id if obj_model else None
        version_id = version.id if version else None
        
        # Check that the object can be retrieved from the database
        obj_hash = self.db_manager._get_object_hash(test_obj)
        db_obj = session.query(Object).filter(Object.id == obj_hash).first()
        
        self.assertIsNotNone(db_obj)
        self.assertIsNotNone(obj_id)
        self.assertEqual(db_obj.id, obj_id)
        
        # Check that the version can be retrieved from the database
        self.assertIsNotNone(version_id)
        db_version = session.query(ObjectVersion).filter(
            ObjectVersion.id == version_id
        ).first()
        
        self.assertIsNotNone(db_version)
        self.assertEqual(db_version.id, version_id)
        
        # Clean up
        session.close()
    
    def test_store_object_version(self):
        """Test the store_object_version method."""
        # Create a test object
        test_obj = {"a": 1, "b": 2}
        obj_name = "test_dict"
        
        # Store the object with versioning and immediately get the IDs
        obj_model, version = self.db_manager.store_object_version(test_obj, obj_name)
        obj_id = obj_model.id if obj_model else None
        version_id = version.id if version else None
        
        # Check that the object and version were created
        self.assertIsNotNone(obj_model)
        self.assertIsNotNone(version)
        self.assertIsNotNone(obj_id)
        self.assertIsNotNone(version_id)
        
        # Create a session to verify the objects in the database
        session = self.Session()
        
        # Check that the object can be retrieved from the database
        obj_hash = self.db_manager._get_object_hash(test_obj)
        db_obj = session.query(Object).filter(Object.id == obj_hash).first()
        
        self.assertIsNotNone(db_obj)
        assert db_obj is not None
        self.assertEqual(db_obj.id, obj_id)
        
        # Check that the version can be retrieved from the database
        db_version = session.query(ObjectVersion).filter(
            ObjectVersion.id == version_id
        ).first()

        
        self.assertIsNotNone(db_version)
        assert db_version is not None
        self.assertEqual(db_version.id, version_id)
        
        # Clean up
        session.close()
    
    def test_get_object_version(self):
        """Test the get_object_version method."""
        # Create a test object
        test_obj = {"a": 1, "b": 2}
        obj_name = "test_dict"
        
        # Store the object with versioning and immediately get the IDs
        obj_model, version = self.db_manager.store_object_version(test_obj, obj_name)
        obj_id = obj_model.id if obj_model else None
        version_id = version.id if version else None
        
        # Get the identity hash
        identity_hash = self.db_manager._get_identity_hash(test_obj, obj_name)
        
        # Get the object version
        retrieved_obj, retrieved_version = self.db_manager.get_object_version(identity_hash)
        
        # Check that the object and version were retrieved
        assert retrieved_obj is not None
        assert retrieved_version is not None
        
        # Check that the retrieved objects match the stored objects
        assert obj_id is not None
        assert version_id is not None
        assert retrieved_obj.id == obj_id
        assert retrieved_version.id == version_id
    
    def test_get_version_specific_object_data(self):
        """Test the get_version_specific_object_data method."""
        # Create a test object
        test_obj = {"a": 1, "b": 2}
        obj_name = "test_dict"
        
        # Store the object with versioning and immediately get the IDs
        obj_model, version = self.db_manager.store_object_version(test_obj, obj_name)
        obj_id = obj_model.id if obj_model else None
        version_id = version.id if version else None
        
        # Get the version-specific object data
        self.assertIsNotNone(obj_id)
        self.assertIsNotNone(version_id)
        obj_data = self.db_manager.get_version_specific_object_data(obj_id, version_id)
        
        # Check that the object data was retrieved
        self.assertIsNotNone(obj_data)
        self.assertEqual(obj_data['id'], obj_id)
        self.assertEqual(obj_data['type'], "dict")
        
        # Check that the version information is included
        self.assertIn('version', obj_data)
        self.assertEqual(obj_data['version']['id'], version_id)
        
        # Check that the identity information is included
        self.assertIn('identity', obj_data)
        
        # Check that the items are included
        self.assertIn('items', obj_data)
        self.assertEqual(len(obj_data['items']), 2)  # Two items: "a" and "b"
    
    def test_object_versioning(self):
        """Test the object versioning system with multiple versions."""
        # Create a test object
        test_obj = {"a": 1, "b": 2}
        obj_name = "test_dict"
        
        # Store the first version and immediately get the IDs
        obj_model1, version1 = self.db_manager.store_object_version(test_obj, obj_name)
        obj_id1 = obj_model1.id if obj_model1 else None
        version_id1 = version1.id if version1 else None
        version_number1 = version1.version_number if version1 else None
        
        # Modify the object
        test_obj["a"] = 3
        test_obj["c"] = 4
        
        # Store the second version and immediately get the IDs
        obj_model2, version2 = self.db_manager.store_object_version(test_obj, obj_name)
        obj_id2 = obj_model2.id if obj_model2 else None
        version_id2 = version2.id if version2 else None
        version_number2 = version2.version_number if version2 else None
        
        # Check that two different versions were created
        self.assertIsNotNone(version_id1)
        self.assertIsNotNone(version_id2)
        self.assertNotEqual(version_id1, version_id2)
        self.assertIsNotNone(version_number1)
        self.assertIsNotNone(version_number2)
        self.assertEqual(version_number1, 1)
        self.assertEqual(version_number2, 2)
        
        # Get the identity hash
        identity_hash = self.db_manager._get_identity_hash(test_obj, obj_name)
        
        # Get the object version history
        history = self.db_manager.get_object_version_history(identity_hash)
        
        # Check that the history contains two versions
        self.assertEqual(len(history), 2)
        
        # Check that the versions are in the correct order
        self.assertEqual(history[0]['version_number'], 1)
        self.assertEqual(history[1]['version_number'], 2)
        
        # Compare the versions
        self.assertIsNotNone(version_id1)
        self.assertIsNotNone(version_id2)
        comparison = self.db_manager.compare_object_versions(version_id1, version_id2)
        
        # Check that the comparison contains differences
        self.assertIn('differences', comparison)
        self.assertTrue(len(comparison['differences']) > 0)
        
        # Check specific differences
        differences = {diff['type'] + '_' + diff.get('name', diff.get('key', '')): diff for diff in comparison['differences']}
        
        # Check that "a" was changed - for dictionaries, we have "item_changed" instead of "attribute_changed"
        self.assertIn('item_changed_a', differences)
        self.assertEqual(differences['item_changed_a']['value1'], '1')
        self.assertEqual(differences['item_changed_a']['value2'], '3')
        
        # Check that "c" was added - for dictionaries, we have "item_added" instead of "attribute_added"
        self.assertIn('item_added_c', differences)
        self.assertEqual(differences['item_added_c']['value2'], '4')
    
    def test_function_call_with_versioned_objects(self):
        """Test storing and retrieving function calls with versioned objects."""
        # Create test objects
        local_obj = {"a": 1, "b": 2}
        global_obj = {"x": 10, "y": 20}
        return_obj = {"result": 42}
        
        # Create a session
        session = self.Session()
        
        # Create a function call
        function_call = FunctionCall(
            event_type="call",
            function="test_function",
            file="test_file.py",
            line=42,
            start_time=datetime.datetime.now(),
            end_time=datetime.datetime.now()
        )
        
        session.add(function_call)
        session.flush()
        
        # Store local variables
        locals_dict = {"local_obj": local_obj}
        self.db_manager._store_function_locals(function_call, locals_dict, session)
        
        # Store global variables
        globals_dict = {"global_obj": global_obj}
        self.db_manager._store_function_globals(function_call, globals_dict, session)
        
        # Store return value
        self.db_manager._store_function_return(function_call, return_obj, session)
        
        # Commit the transaction
        session.commit()
        
        # Get the function call data
        function_call_data = self.db_manager.get_function_call_data(function_call.id)
        
        # Check that the function call data contains the versioned objects
        self.assertIn('locals', function_call_data)
        self.assertIn('local_obj', function_call_data['locals'])
        
        self.assertIn('globals', function_call_data)
        self.assertIn('global_obj', function_call_data['globals'])
        
        self.assertIn('return_value', function_call_data)
        
        # Check that the version information is included
        self.assertIn('version', function_call_data['locals']['local_obj'])
        self.assertIn('version', function_call_data['globals']['global_obj'])
        self.assertIn('version', function_call_data['return_value'])
        
        # Clean up
        session.close()
    
    def test_complex_object_versioning(self):
        """Test versioning of complex objects with nested structures."""
        # Create a complex object with nested structures
        complex_obj = {
            "name": "test",
            "nested_dict": {"a": 1, "b": 2},
            "nested_list": [1, 2, 3],
            "nested_mixed": {"list": [4, 5, 6], "dict": {"c": 3, "d": 4}}
        }
        obj_name = "complex_obj"
        
        # Create a session that will remain open throughout the test
        session = self.Session()
        
        try:
            # Store the first version
            obj_model1, version1 = self.db_manager.store_object_version(complex_obj, obj_name)
            
            # Immediately extract the IDs as primitive values
            obj_id1 = obj_model1.id if obj_model1 else None
            version_id1 = version1.id if version1 else None
            
            # Ensure the objects are still attached to the session
            session.add(obj_model1)
            session.add(version1)
            session.flush()
            
            # Modify the object
            complex_obj["name"] = "modified"
            complex_obj["nested_dict"]["a"] = 10
            complex_obj["nested_list"].append(4)
            complex_obj["nested_mixed"]["list"][0] = 40
            
            # Store the second version
            obj_model2, version2 = self.db_manager.store_object_version(complex_obj, obj_name)
            
            # Immediately extract the IDs as primitive values
            obj_id2 = obj_model2.id if obj_model2 else None
            version_id2 = version2.id if version2 else None
            
            # Ensure the objects are still attached to the session
            session.add(obj_model2)
            session.add(version2)
            session.flush()
            
            # Get the identity hash
            identity_hash = self.db_manager._get_identity_hash(complex_obj, obj_name)
            
            # Get the object version history
            history = self.db_manager.get_object_version_history(identity_hash)
            
            # Check that the history contains two versions
            self.assertEqual(len(history), 2)
            
            # Compare the versions using the primitive IDs we stored
            self.assertIsNotNone(version_id1)
            self.assertIsNotNone(version_id2)
            comparison = self.db_manager.compare_object_versions(version_id1, version_id2)
            
            # Check that the comparison contains differences
            self.assertIn('differences', comparison)
            self.assertTrue(len(comparison['differences']) > 0)
            
            # Get the version-specific object data using the primitive IDs
            self.assertIsNotNone(obj_id1)
            self.assertIsNotNone(version_id1)
            self.assertIsNotNone(obj_id2)
            self.assertIsNotNone(version_id2)
            obj_data1 = self.db_manager.get_version_specific_object_data(obj_id1, version_id1, session=session)
            obj_data2 = self.db_manager.get_version_specific_object_data(obj_id2, version_id2, session=session)
            
            # Check that the object data was retrieved
            self.assertIsNotNone(obj_data1)
            self.assertIsNotNone(obj_data2)
            
            # Check that the items are included
            self.assertIn('items', obj_data1)
            self.assertIn('items', obj_data2)
        finally:
            # Always close the session at the end of the test
            session.close()
    
    def test_custom_class_versioning(self):
        """Test versioning of custom class objects."""
        # Create an instance
        test_obj = TestClass(42)
        obj_name = "test_obj"
        
        # Store the first version and immediately get the IDs
        obj_model1, version1 = self.db_manager.store_object_version(test_obj, obj_name)
        obj_id1 = obj_model1.id if obj_model1 else None
        version_id1 = version1.id if version1 else None
        
        # Modify the object
        test_obj.value = 100
        test_obj.name = "modified"
        
        # Store the second version and immediately get the IDs
        obj_model2, version2 = self.db_manager.store_object_version(test_obj, obj_name)
        obj_id2 = obj_model2.id if obj_model2 else None
        version_id2 = version2.id if version2 else None
        
        # Get the identity hash
        identity_hash = self.db_manager._get_identity_hash(test_obj, obj_name)
        
        # Get the object version history
        history = self.db_manager.get_object_version_history(identity_hash)
        
        # Check that the history contains two versions
        self.assertEqual(len(history), 2)
        
        # Get the version-specific object data
        self.assertIsNotNone(obj_id1)
        self.assertIsNotNone(version_id1)
        self.assertIsNotNone(obj_id2)
        self.assertIsNotNone(version_id2)
        obj_data1 = self.db_manager.get_version_specific_object_data(obj_id1, version_id1)
        obj_data2 = self.db_manager.get_version_specific_object_data(obj_id2, version_id2)
        
        # Check that the object data was retrieved
        self.assertIsNotNone(obj_data1)
        self.assertIsNotNone(obj_data2)
        
        # Check that the attributes are included
        self.assertIn('attributes', obj_data1)
        self.assertIn('attributes', obj_data2)
        
        # Check specific attributes
        self.assertIn('value', obj_data1['attributes'])
        self.assertIn('value', obj_data2['attributes'])
        
        # Check that the values are different
        self.assertEqual(obj_data1['attributes']['value']['value'], '42')
        self.assertEqual(obj_data2['attributes']['value']['value'], '100')

if __name__ == '__main__':
    unittest.main() 