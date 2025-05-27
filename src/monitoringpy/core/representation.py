import pickle
import copyreg
from typing import Any, Dict, Mapping, Optional, Tuple, Union, TypeVar, Sequence
import hashlib
from enum import Enum
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
from .models import StoredObject, ObjectIdentity, CodeObjectLink, CodeDefinition
import datetime
import io
import importlib.util
import sys
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

class ObjectType(Enum):
    PRIMITIVE = "primitive"
    LIST = "list"
    DICT = "dict"
    CUSTOM = "custom"

T = TypeVar('T')

class PickleConfig:
    """Configuration for custom pickling behavior"""
    def __init__(self, dispatch_table=None, custom_picklers=None):
        self.dispatch_table = dispatch_table or copyreg.dispatch_table.copy()
        
        # Load custom picklers if specified
        if custom_picklers:
            self.load_custom_picklers(custom_picklers)

        
    def load_custom_picklers(self, module_names):
        """
        Load custom pickler modules and update the dispatch table.
        
        Args:
            module_names: List of module names to load custom picklers from
        """
        if not self.dispatch_table:
            self.dispatch_table = copyreg.dispatch_table.copy()
            
        # Get the base path for custom picklers
        base_path = Path(__file__).parent.parent / "picklers"
        
        # First make sure the picklers package is imported
        try:
            import monitoringpy.picklers
        except ImportError:
            logger.warning("Could not import picklers package")
            
        for module_name in module_names:
            try:
                # Try to import the module
                full_module_name = f"monitoringpy.picklers.{module_name}"
                module = importlib.util.find_spec(full_module_name)
                if module is None:
                    # Try loading from file
                    module_path = base_path / f"{module_name}.py"
                    if module_path.exists():
                        spec = importlib.util.spec_from_file_location(full_module_name, module_path)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            sys.modules[full_module_name] = module
                    else:
                        logger.warning(f"Could not find pickler module: {module_name}")
                        continue
                else:
                    module = importlib.import_module(full_module_name)
                
                if module and hasattr(module, 'get_dispatch_table'):
                    dispatch_table = module.get_dispatch_table()
                    self.dispatch_table.update(dispatch_table)
                            
            except Exception as e:
                logger.error(f"Error loading custom pickler for {module_name}: {e}")
                logger.exception(e)
        
    def create_pickler(self, file):
        """Create a pickler with the custom dispatch table"""
        p = pickle.Pickler(file)
        if self.dispatch_table:
            p.dispatch_table = self.dispatch_table
        return p
        
    def create_unpickler(self, file, correct_module_path=None):
        """Create an unpickler, optionally with module path fixing"""
        if correct_module_path:
            return ModulePathFixingUnpickler(file, correct_module_path)
        return pickle.Unpickler(file)
        
    def dumps(self, obj, correct_module_path=None):
        """Pickle an object with custom reducers and optional module path normalization"""
        # Handle module path normalization for custom classes
        original_modules = {}
        if correct_module_path and hasattr(obj, '__class__'):
            cls = obj.__class__
            if hasattr(cls, '__module__') and cls.__module__ != correct_module_path:
                original_modules[cls] = cls.__module__
                cls.__module__ = correct_module_path
                logger.debug(f"Temporarily changed {cls.__name__}.__module__ from {original_modules[cls]} to {correct_module_path}")
        
        try:
            f = io.BytesIO()
            pickler = self.create_pickler(f)
            pickler.dump(obj)
            return f.getvalue()
        finally:
            # Restore original module paths
            for cls, original_module in original_modules.items():
                cls.__module__ = original_module
                logger.debug(f"Restored {cls.__name__}.__module__ to {original_module}")
        
    def loads(self, data, correct_module_path=None):
        """Unpickle an object with optional module path fixing"""
        f = io.BytesIO(data)
        unpickler = self.create_unpickler(f, correct_module_path)
        return unpickler.load()


class ModulePathFixingUnpickler(pickle.Unpickler):
    """Custom unpickler that fixes module path mismatches using stored metadata"""
    
    def __init__(self, file, correct_module_path):
        super().__init__(file)
        self.correct_module_path = correct_module_path
        
    def find_class(self, module, name):
        """Override find_class to fix module path mismatches"""
        original_module = module
        
        # If we're trying to load from __main__ but should use a different module path
        if module == "__main__" and self.correct_module_path and self.correct_module_path != "__main__":
            module = self.correct_module_path
            logger.debug(f"Fixed module path: {original_module}.{name} -> {module}.{name}")
        
        # If we're trying to load from a module path but it was originally __main__
        elif module != "__main__" and self.correct_module_path == "__main__":
            # Try __main__ first, then fall back to the original module
            try:
                return super().find_class("__main__", name)
            except (ImportError, AttributeError):
                logger.debug(f"Class not found in __main__, trying original module {module}")
                # Fall through to use original module
        
        try:
            return super().find_class(module, name)
        except (ImportError, AttributeError) as e:
            # If we can't find the class, try some common alternatives
            if module == "__main__":
                # Try to find the class in any loaded module
                for mod_name, mod in sys.modules.items():
                    if hasattr(mod, name) and isinstance(getattr(mod, name), type):
                        logger.debug(f"Found class {name} in module {mod_name} instead of {module}")
                        return getattr(mod, name)
            
            # Re-raise the original error if we can't fix it
            raise e

class Object:
    """Represent an object at a certain state in the program"""
    def __init__(self, value: Any, pickle_config: Optional[PickleConfig] = None):
        self.value = value
        self.type = self._get_type()
        self._hash = None
        self.pickle_config = pickle_config or PickleConfig()

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
                "value": self.pickle_config.dumps(self.value).hex()
            }
        else:  # Custom type
            return {
                "type": self.type.value,
                "value": self.pickle_config.dumps(self.value).hex()
            }

    @classmethod
    def load(cls, data: Dict[str, Any], pickle_config: Optional[PickleConfig] = None) -> 'Object':
        """Load the object from a dictionary format"""
        config = pickle_config or PickleConfig()
        obj_type = ObjectType(data["type"])
        if obj_type == ObjectType.PRIMITIVE:
            return cls(data["value"], pickle_config=config)
        else:
            value = config.loads(bytes.fromhex(data["value"]))
            return cls(value, pickle_config=config)

    def __str__(self) -> str:
        """Return a string representation of the object"""
        return str(self.value)

    def ref(self) -> str:
        """Return a reference to the object"""
        if self._hash is None:
            if self.type == ObjectType.PRIMITIVE:
                self._hash = str(self.value)
            else:
                self._hash = hashlib.md5(self.pickle_config.dumps(self.value)).hexdigest()
        return self._hash

class Primitive(Object):
    """Represent a primitive value at a certain state in the program"""
    def __init__(self, value: Union[int, float, bool, str, None], pickle_config: Optional[PickleConfig] = None):
        super().__init__(value, pickle_config)
        if not isinstance(value, (int, float, bool, str, type(None))):
            raise TypeError("Primitive objects can only store primitive types")

class List(Object):
    """Represent a list at a certain state in the program"""
    def __init__(self, value: list, pickle_config: Optional[PickleConfig] = None):
        super().__init__(value, pickle_config)
        if not isinstance(value, list):
            raise TypeError("List objects can only store lists")

class DictObject(Object):
    """Represent a dictionary at a certain state in the program"""
    def __init__(self, value: dict, pickle_config: Optional[PickleConfig] = None):
        super().__init__(value, pickle_config)
        if not isinstance(value, dict):
            raise TypeError("DictObject objects can only store dictionaries")

class CustomClass(Object):
    """Represent a custom class at a certain state in the program"""
    def __init__(self, value: Any, pickle_config: Optional[PickleConfig] = None):
        super().__init__(value, pickle_config)
        if isinstance(value, (int, float, bool, str, type(None), list, dict)):
            raise TypeError("CustomClass objects cannot store primitive or structured types")

class ObjectManager:
    """Manage objects in the program"""
    def __init__(self, session: Session, pickle_config: Optional[PickleConfig] = None):
        self.session = session
        self.pickle_config = pickle_config or PickleConfig()
        try:
            from .code_manager import CodeManager, ClassLoader # type: ignore
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

    def _get_correct_module_path_for_object(self, stored_obj: StoredObject) -> Optional[str]:
        """Get the correct module path for an object from stored metadata"""
        try:
            # Get the code definition through the link table
            code_link = self.session.query(CodeObjectLink).filter_by(object_id=stored_obj.id).first()
            if code_link:
                code_def = self.session.query(CodeDefinition).filter_by(id=code_link.definition_id).first()
                if code_def:
                    return code_def.module_path
        except Exception as e:
            logger.debug(f"Could not get module path for object {stored_obj.id}: {e}")
        return None

    def _store_object(self, obj: Object) -> StoredObject:
        """Store an object in the database"""
        ref = obj.ref()
        
        # Check if object already exists
        stored_obj = self.session.query(StoredObject).filter(StoredObject.id == ref).first()
        if stored_obj:
            return stored_obj

        # Get or create an identity for the object
        identity_hash = self._get_identity(obj)
        identity = self.session.query(ObjectIdentity).filter(ObjectIdentity.identity_hash == identity_hash).first()
        
        if not identity:
            identity = ObjectIdentity(
                identity_hash=identity_hash,
                name=type(obj.value).__name__
            )
            self.session.add(identity)
            self.session.flush()  # Ensure identity gets an ID
        
        # For custom objects, determine the correct module path for consistent storage
        correct_module_path = None
        if obj.type == ObjectType.CUSTOM and hasattr(obj.value, '__class__'):
            cls = obj.value.__class__
            if hasattr(cls, '__module__'):
                # Normalize __main__ to the actual module name if we can determine it
                if cls.__module__ == "__main__":
                    # Try to find a better module name from the file path or other context
                    # For now, we'll store as __main__ but this could be enhanced
                    correct_module_path = "__main__"
                else:
                    correct_module_path = cls.__module__
        
        # Create new stored object
        if obj.type == ObjectType.PRIMITIVE:
            stored_obj = StoredObject(
                id=ref,
                identity_id=identity.id,
                version_number=1,  # First version
                type_name=type(obj.value).__name__,  # Store actual type name (int, float, etc.)
                is_primitive=True,
                primitive_value=str(obj.value)
            )
        else:
            # Get appropriate type name
            if obj.type == ObjectType.LIST:
                actual_type_name = 'list'
            elif obj.type == ObjectType.DICT:
                actual_type_name = 'dict'
            else:
                # For custom types, get the actual class name
                actual_type_name = obj.value.__class__.__name__
                
            # Use the correct module path for pickling if available
            pickle_data = self.pickle_config.dumps(obj.value, correct_module_path)
                
            stored_obj = StoredObject(
                id=ref,
                identity_id=identity.id,
                version_number=1,  # First version
                type_name=actual_type_name,  # Use the actual class name instead of our representation type
                is_primitive=False,
                pickle_data=pickle_data
            )
        
        # Add to session
        self.session.add(stored_obj)
        self.session.flush()
        
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

    def store_code_definition(self, name: str, type: str, module_path: str, code_content: str, first_line_no: Optional[int] = None) -> str:
        """Store a code definition and return its ID"""
        # Create a hash of the code content as the ID
        code_hash = hashlib.md5(code_content.encode()).hexdigest()
        
        # Check if definition already exists
        definition = self.session.query(CodeDefinition).filter_by(id=code_hash).first()
        if definition:
            return code_hash
            
        # Create new definition
        definition = CodeDefinition(
            id=code_hash,
            name=name,
            type=type,
            module_path=module_path,
            code_content=code_content,
            first_line_no=first_line_no
        )
        self.session.add(definition)
        self.session.flush()
        return code_hash

    def store(self, value: Any) -> str:
        """Store an object and return its reference"""
        # Create appropriate Object instance
        if isinstance(value, (int, float, bool, str, type(None))):
            obj = Primitive(value, pickle_config=self.pickle_config)
        elif isinstance(value, list):
            obj = List(value, pickle_config=self.pickle_config)
        elif isinstance(value, dict):
            obj = DictObject(value, pickle_config=self.pickle_config)
        else:
            obj = CustomClass(value, pickle_config=self.pickle_config)

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
            existing_version = self.session.query(StoredObject).filter(
                StoredObject.identity_id == identity_record.id,
                StoredObject.id == stored_obj.id
            ).first()

            if existing_version:
                # This exact state already exists, return its reference
                return ref

            # Get latest version number
            latest_version = self.session.query(StoredObject).filter(
                StoredObject.identity_id == identity_record.id
            ).order_by(StoredObject.version_number.desc()).first()

            # No need to create a version record, as StoredObject now includes versioning
            # Just set the version number on the stored_obj
            new_version_num = 1
            if latest_version:
                new_version_num = latest_version.version_number + 1
            setattr(stored_obj, 'version_number', new_version_num)
            
            try:
                self.session.flush()
            except SQLAlchemyError as e:
                logger.warning(f"Error creating version: {e}")
                self.session.rollback()
                raise

        return ref

    def get(self, ref: str) -> Tuple[Any, str]:
        """Get an object by its reference"""
        stored_obj = self.session.query(StoredObject).filter(StoredObject.id == ref).first()
        if not stored_obj:
            return None, "None"

        if stored_obj.is_primitive:
            # Convert primitive value back to appropriate type
            if stored_obj.type_name == 'int':
                return int(stored_obj.primitive_value), 'int' # type: ignore
            elif stored_obj.type_name == 'float':
                return float(stored_obj.primitive_value), 'float' # type: ignore
            elif stored_obj.type_name == 'bool':
                return stored_obj.primitive_value.lower() == 'true', 'bool' # type: ignore
            elif stored_obj.type_name == 'str':
                return stored_obj.primitive_value, 'str'
            elif stored_obj.type_name == 'NoneType':
                return None, 'NoneType'
            else:
                raise ValueError(f"Unknown primitive type: {stored_obj.type_name}")
        else:
            try:
                # Get the correct module path from stored metadata
                correct_module_path = self._get_correct_module_path_for_object(stored_obj)
                
                # Use the module path fixing unpickler
                return self.pickle_config.loads(stored_obj.pickle_data, correct_module_path), stored_obj.type_name # type: ignore
            except (ImportError, AttributeError, ModuleNotFoundError) as e:
                # First try to load the class using the stored code if available
                if self.class_loader is not None and self.code_manager is not None:
                    try:
                        # Get the code definition through the link table
                        code_link = self.session.query(CodeObjectLink).filter_by(object_id=stored_obj.id).first()
                        if code_link:
                            # Get the complete code info
                            code_info = self.code_manager.get_code(code_link.definition_id)
                            if code_info and 'code' in code_info:
                                # Execute the code directly to recreate the class
                                namespace = {}
                                exec(code_info['code'], namespace)
                                if stored_obj.type_name in namespace:
                                    # Try unpickling again now that we have recreated the class
                                    correct_module_path = self._get_correct_module_path_for_object(stored_obj)
                                    return self.pickle_config.loads(stored_obj.pickle_data, correct_module_path), stored_obj.type_name # type: ignore
                                # Store the code info for the UnpickleableObject
                                self._last_code_info = code_info
                    except Exception as loader_e:
                        logger.debug(f"Failed to load class from stored code: {loader_e}")

                logger.debug(f"Could not unpickle object of type {stored_obj.type_name}: {e}")
                # If ClassLoader failed or wasn't available, create a placeholder object
                class UnpickleableObject:
                    def __init__(self, type_name, pickle_data=None, code_info=None):
                        self._type_name = type_name
                        self._pickle_data = pickle_data
                        self._code_info = code_info
                        # Try to get the actual content for lists/tuples
                        self._content = None
                        if pickle_data and type_name in ('list', 'tuple'):
                            try:
                                # Try to safely unpickle just the content
                                self._content = pickle.loads(pickle_data)
                            except:
                                pass
                    
                    def __str__(self):
                        if self._content is not None:
                            # For lists/tuples, show the actual content
                            return str(self._content)
                        return f"<{self._type_name} (unpickleable)>"
                    
                    def __repr__(self):
                        return self.__str__()
                    
                    @property
                    def __class__(self):
                        # This allows isinstance() checks to still work with the type name
                        return type(self._type_name, (), {})

                    @property
                    def code(self):
                        """Return code info in the format expected by the web interface"""
                        if self._code_info:
                            return {
                                'name': self._code_info.get('name', self._type_name),
                                'module_path': self._code_info.get('module_path', 'unknown'),
                                'code_content': self._code_info.get('code', ''),
                                'creation_time': self._code_info.get('creation_time', datetime.datetime.now()).isoformat()
                            }
                        return None
                
                return UnpickleableObject(stored_obj.type_name, stored_obj.pickle_data, 
                                        getattr(self, '_last_code_info', None)), stored_obj.type_name # type: ignore
            except Exception as e:
                logger.error(f"Unexpected error unpickling object of type {stored_obj.type_name}: {e}")
                raise e

    def get_without_pickle(self, ref: str) -> Optional[Any]:
        """Get an object by its reference without unpickling"""
        stored_obj = self.session.query(StoredObject).filter(StoredObject.id == ref).first()
        if not stored_obj:
            return None
        
        if stored_obj.is_primitive: # type: ignore
            # Convert primitive value back to appropriate type
            if stored_obj.type_name == 'int':
                return int(stored_obj.primitive_value), 'int' # type: ignore
            elif stored_obj.type_name == 'float':
                return float(stored_obj.primitive_value), 'float' # type: ignore
            elif stored_obj.type_name == 'bool':
                return stored_obj.primitive_value.lower() == 'true', 'bool' # type: ignore
            elif stored_obj.type_name == 'str':
                return stored_obj.primitive_value, 'str'
            elif stored_obj.type_name == 'NoneType':
                return None, 'NoneType'
        elif stored_obj.type_name == 'list':
            return "WIP", 'list'
        elif stored_obj.type_name == 'dict':
            return "WIP", 'dict'
        else:
            return stored_obj.id, stored_obj.type_name

    def next_ref(self, ref: str) -> Optional[str]:
        """Get the next version of an object"""
        try:
            # Get the current version
            current_version = self.session.query(StoredObject).filter(
                StoredObject.id == ref
            ).first()
            
            if not current_version:
                return None
                
            # Get the next version
            next_version = self.session.query(StoredObject).filter(
                StoredObject.identity_id == current_version.identity_id,
                StoredObject.version_number > current_version.version_number
            ).order_by(StoredObject.version_number.asc()).first()
            
            return next_version.id if next_version else None
        except Exception as e:
            logger.warning(f"Error getting next version: {e}")
            return None

    def get_history(self, ref: str) -> list:
        """Get the history of an object (all versions)"""
        try:
            # Get the current version
            version = self.session.query(StoredObject).filter(
                StoredObject.id == ref
            ).first()
            
            if not version:
                return []
                
            # Get all versions
            versions = self.session.query(StoredObject).filter(
                StoredObject.identity_id == version.identity_id
            ).order_by(StoredObject.version_number.asc()).all()
            
            return [v.id for v in versions]
        except Exception as e:
            logger.warning(f"Error getting object history: {e}")
            return []

    def rehydrate(self, ref: Optional[str]) -> Any:
        """
        Rehydrate an object from its reference.
        
        Args:
            ref: The reference to the stored object
            
        Returns:
            The rehydrated object
            
        Raises:
            ValueError: If the reference is invalid or object cannot be rehydrated
        """
        if ref is None:
            return None
        try:
            return self.get(ref)[0]
        except Exception as e:
            raise ValueError(f"Could not rehydrate object with reference {ref}: {e}")

    def rehydrate_dict(self, refs: Mapping[str, Optional[str]]) -> Dict[str, Any]:
        """
        Rehydrate a dictionary of references to their actual values.
        
        Args:
            refs: Dictionary of names to object references
            
        Returns:
            Dictionary of names to rehydrated values
        """
        result = {}
        for name, ref in refs.items():
            try:
                result[name] = self.rehydrate(ref)
            except ValueError as e:
                logger.warning(f"Could not rehydrate value for {name}: {e}")
                result[name] = f"<Error rehydrating {ref}: {str(e)}>"
        return result

    def rehydrate_sequence(self, refs: Sequence[Optional[str]]) -> list:
        """
        Rehydrate a sequence of references to their actual values.
        
        Args:
            refs: Sequence of object references
            
        Returns:
            List of rehydrated values
        """
        result = []
        for ref in refs:
            try:
                result.append(self.rehydrate(ref))
            except ValueError as e:
                logger.warning(f"Could not rehydrate value: {e}")
                result.append(f"<Error rehydrating {ref}: {str(e)}>")
        return result
