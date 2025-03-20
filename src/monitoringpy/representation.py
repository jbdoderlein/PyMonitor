import pickle
from typing import Any, Dict, Optional, Union, TypeVar, Generic
import hashlib
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
from .models import StoredObject, ObjectVersion, ObjectIdentity
import datetime

# Configure logging
logger = logging.getLogger(__name__)

class ObjectType(Enum):
    PRIMITIVE = "primitive"
    LIST = "list"
    DICT = "dict"
    CUSTOM = "custom"

T = TypeVar('T')

class Object:
    """Represent an object at a certain state in the program"""
    def __init__(self, value: Any):
        self.value = value
        self.type = self._get_type()
        self._hash = None

    def _get_type(self) -> ObjectType:
        """Determine the type of the object"""
        if isinstance(self.value, (int, float, bool, str, type(None))):
            return ObjectType.PRIMITIVE
        elif isinstance(self.value, list):
            return ObjectType.LIST
        elif isinstance(self.value, dict):
            return ObjectType.DICT
        else:
            return ObjectType.CUSTOM

    def save(self) -> Dict[str, Any]:
        """Save the object to a dictionary format"""
        if self.type == ObjectType.PRIMITIVE:
            return {
                "type": self.type.value,
                "value": self.value
            }
        elif self.type in (ObjectType.LIST, ObjectType.DICT):
            return {
                "type": self.type.value,
                "value": pickle.dumps(self.value).hex()
            }
        else:  # Custom type
            return {
                "type": self.type.value,
                "value": pickle.dumps(self.value).hex()
            }

    @classmethod
    def load(cls, data: Dict[str, Any]) -> 'Object':
        """Load the object from a dictionary format"""
        obj_type = ObjectType(data["type"])
        if obj_type == ObjectType.PRIMITIVE:
            return cls(data["value"])
        else:
            value = pickle.loads(bytes.fromhex(data["value"]))
            return cls(value)

    def __str__(self) -> str:
        """Return a string representation of the object"""
        return str(self.value)

    def ref(self) -> str:
        """Return a reference to the object"""
        if self._hash is None:
            if self.type == ObjectType.PRIMITIVE:
                self._hash = str(self.value)
            else:
                self._hash = hashlib.md5(pickle.dumps(self.value)).hexdigest()
        return self._hash

class Primitive(Object):
    """Represent a primitive value at a certain state in the program"""
    def __init__(self, value: Union[int, float, bool, str, None]):
        super().__init__(value)
        if not isinstance(value, (int, float, bool, str, type(None))):
            raise TypeError("Primitive objects can only store primitive types")

class List(Object):
    """Represent a list at a certain state in the program"""
    def __init__(self, value: list):
        super().__init__(value)
        if not isinstance(value, list):
            raise TypeError("List objects can only store lists")

class DictObject(Object):
    """Represent a dictionary at a certain state in the program"""
    def __init__(self, value: dict):
        super().__init__(value)
        if not isinstance(value, dict):
            raise TypeError("DictObject objects can only store dictionaries")

class CustomClass(Object):
    """Represent a custom class at a certain state in the program"""
    def __init__(self, value: Any):
        super().__init__(value)
        if isinstance(value, (int, float, bool, str, type(None), list, dict)):
            raise TypeError("CustomClass objects cannot store primitive or structured types")

class ObjectManager:
    """Manage objects in the program"""
    def __init__(self, session: Session):
        self.session = session
        try:
            from .code_manager import CodeManager
            from .class_loader import ClassLoader
            self.code_manager = CodeManager(session)
            self.class_loader = ClassLoader(session)
        except ImportError:
            logger.warning("CodeManager/ClassLoader not available, code tracking disabled")
            self.code_manager = None
            self.class_loader = None

    def _get_identity(self, obj: Object) -> str:
        """Get the identity of an object (independent of its state)"""
        if obj.type == ObjectType.PRIMITIVE:
            return obj.ref()  # For primitives, ref is the identity
        else:
            # For non-primitives, identity is based on object id
            return str(id(obj.value))

    def _store_object(self, obj: Object) -> StoredObject:
        """Store an object in the database"""
        ref = obj.ref()
        
        # Check if object already exists
        stored_obj = self.session.query(StoredObject).filter(StoredObject.id == ref).first()
        if stored_obj:
            return stored_obj

        # Create new stored object
        if obj.type == ObjectType.PRIMITIVE:
            stored_obj = StoredObject(
                id=ref,
                type_name=type(obj.value).__name__,  # Store actual type name (int, float, etc.)
                is_primitive=True,
                primitive_value=str(obj.value)
            )
        else:
            stored_obj = StoredObject(
                id=ref,
                type_name=type(obj.value).__name__,
                is_primitive=False,
                pickle_data=pickle.dumps(obj.value)
            )

        self.session.add(stored_obj)
        try:
            self.session.flush()
        except SQLAlchemyError as e:
            logger.warning(f"Error storing object: {e}")
            self.session.rollback()
            # Try to get the object again (might have been created by another process)
            stored_obj = self.session.query(StoredObject).filter(StoredObject.id == ref).first()
            if not stored_obj:
                raise

        # If it's a custom class and we have a code manager, store the class definition
        if (obj.type == ObjectType.CUSTOM and self.code_manager is not None and 
            not isinstance(obj.value, (int, float, bool, str, list, dict, type(None)))):
            try:
                code_ref = self.code_manager.store_class(type(obj.value))
                if code_ref:
                    self.code_manager.link_object(ref, code_ref)
            except Exception as e:
                logger.warning(f"Error storing class definition: {e}")

        return stored_obj

    def store(self, value: Any) -> str:
        """Store an object and return its reference"""
        # Create appropriate Object instance
        if isinstance(value, (int, float, bool, str, type(None))):
            obj = Primitive(value)
        elif isinstance(value, list):
            obj = List(value)
        elif isinstance(value, dict):
            obj = DictObject(value)
        else:
            obj = CustomClass(value)

        ref = obj.ref()
        identity = self._get_identity(obj)

        # Store the object
        stored_obj = self._store_object(obj)

        # Handle versioning for non-primitive types
        if obj.type != ObjectType.PRIMITIVE:
            # Get or create identity record
            identity_record = self.session.query(ObjectIdentity).filter(
                ObjectIdentity.identity_hash == identity
            ).first()

            if not identity_record:
                identity_record = ObjectIdentity(
                    identity_hash=identity,
                    creation_time=datetime.datetime.now()
                )
                self.session.add(identity_record)
                try:
                    self.session.flush()
                except SQLAlchemyError as e:
                    logger.warning(f"Error creating identity: {e}")
                    self.session.rollback()
                    identity_record = self.session.query(ObjectIdentity).filter(
                        ObjectIdentity.identity_hash == identity
                    ).first()
                    if not identity_record:
                        raise

            # Check if this exact state already exists in the version history
            existing_version = self.session.query(ObjectVersion).filter(
                ObjectVersion.identity_id == identity_record.id,
                ObjectVersion.object_id == stored_obj.id
            ).first()

            if existing_version:
                # This exact state already exists, return its reference
                return ref

            # Get latest version number
            latest_version = self.session.query(ObjectVersion).filter(
                ObjectVersion.identity_id == identity_record.id
            ).order_by(ObjectVersion.version_number.desc()).first()

            version_number = 1
            if latest_version:
                version_number = latest_version.version_number + 1

            # Create new version
            version = ObjectVersion(
                object_id=stored_obj.id,
                identity_id=identity_record.id,
                version_number=version_number,
                timestamp=datetime.datetime.now()
            )
            self.session.add(version)

            # Update identity's latest version
            identity_record.latest_version_id = stored_obj.id

            try:
                self.session.flush()
            except SQLAlchemyError as e:
                logger.warning(f"Error creating version: {e}")
                self.session.rollback()
                raise

        return ref

    def get(self, ref: str) -> Optional[Any]:
        """Get an object by its reference"""
        stored_obj = self.session.query(StoredObject).filter(StoredObject.id == ref).first()
        if not stored_obj:
            return None

        if stored_obj.is_primitive:
            # Convert primitive value back to appropriate type
            if stored_obj.type_name == 'int':
                return int(stored_obj.primitive_value)
            elif stored_obj.type_name == 'float':
                return float(stored_obj.primitive_value)
            elif stored_obj.type_name == 'bool':
                return stored_obj.primitive_value.lower() == 'true'
            elif stored_obj.type_name == 'str':
                return stored_obj.primitive_value
            elif stored_obj.type_name == 'NoneType':
                return None
        else:
            try:
                return pickle.loads(stored_obj.pickle_data)
            except (ImportError, AttributeError) as e:
                # If we can't unpickle due to missing class, try to load it
                if self.class_loader:
                    try:
                        # Get the code definition for this object
                        if self.code_manager:
                            code_info = self.code_manager.get_object_code(ref)
                            if code_info:
                                # Load the class
                                cls = self.class_loader.get_class(code_info['name'], code_info['module_path'])
                                if cls:
                                    # Add the class to the module namespace so pickle can find it
                                    import sys
                                    module = sys.modules.get(code_info['module_path'])
                                    if module:
                                        setattr(module, code_info['name'], cls)
                                    # Try unpickling again
                                    return pickle.loads(stored_obj.pickle_data)
                    except Exception as e2:
                        logger.warning(f"Error loading class for object {ref}: {e2}")
                # If we still can't unpickle, raise the original error
                raise

    def next_ref(self, ref: str) -> Optional[str]:
        """Get the next version reference of an object"""
        # Get the current version
        current_version = self.session.query(ObjectVersion).filter(
            ObjectVersion.object_id == ref
        ).first()

        if not current_version:
            return None

        # Get the next version with the same identity but higher version number
        next_version = self.session.query(ObjectVersion).filter(
            ObjectVersion.identity_id == current_version.identity_id,
            ObjectVersion.version_number > current_version.version_number
        ).order_by(ObjectVersion.version_number.asc()).first()

        return next_version.object_id if next_version else None

    def get_history(self, ref: str) -> list:
        """Get the complete history of an object"""
        # First get the object to find its identity
        obj = self.session.query(StoredObject).filter(StoredObject.id == ref).first()
        if not obj:
            return []

        # Find the identity through any version that references this object
        version = self.session.query(ObjectVersion).filter(
            ObjectVersion.object_id == ref
        ).first()
        if not version:
            return [ref]  # No versioning for this object (e.g. primitives)

        # Get all versions for this identity
        versions = self.session.query(ObjectVersion).filter(
            ObjectVersion.identity_id == version.identity_id
        ).order_by(ObjectVersion.version_number.asc()).all()

        return [version.object_id for version in versions]
