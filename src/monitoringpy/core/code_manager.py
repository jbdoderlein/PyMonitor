import inspect
import hashlib
import types
from typing import Optional, Dict, List, Any, Type
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
from .models import CodeDefinition, CodeObjectLink, StoredObject

logger = logging.getLogger(__name__)

class ClassLoader:
    """Dynamically loads and creates classes from stored definitions."""
    
    def __init__(self, session: Session):
        self.session = session
        self._class_cache: Dict[str, Type] = {}
    
    def get_class(self, class_name: str, module_path: str) -> Optional[Type]:
        """Get a class by name and module path. Creates it from stored definition if needed."""
        cache_key = f"{module_path}.{class_name}"
        
        # Check cache first
        if cache_key in self._class_cache:
            return self._class_cache[cache_key]
            
        # Try to find the code definition
        code_def = self.session.query(CodeDefinition).filter(
            CodeDefinition.name == class_name,
            CodeDefinition.module_path == module_path,
            CodeDefinition.type == 'class'
        ).first()
        
        if not code_def:
            logger.debug(f"No code definition found for {cache_key}")
            return None
            
        try:
            # Create a new module to hold our class
            module = types.ModuleType(module_path)
            
            # Execute the code in the module's context
            exec(code_def.code_content, module.__dict__)
            
            # Get the class from the module
            cls = getattr(module, class_name)
            
            # Cache the class
            self._class_cache[cache_key] = cls
            
            return cls
        except Exception as e:
            logger.error(f"Error creating class {cache_key}: {e}")
            return None
    
    def clear_cache(self) -> None:
        """Clear the class cache."""
        self._class_cache.clear()

class CodeManager:
    """Manages code definitions and dynamic class loading in the database."""
    
    def __init__(self, session: Session):
        self.session = session
        self._class_cache: Dict[str, Type] = {}
    
    def _get_code_hash(self, code_content: str) -> str:
        """Generate a hash for the code content."""
        return hashlib.md5(code_content.encode()).hexdigest()
    
    def store_class(self, cls: Type) -> Optional[str]:
        """Store a class definition and return its reference.
        
        Returns:
            str: The reference hash of the stored code, or None if the source code couldn't be retrieved.
        """
        # Skip built-in types
        if cls.__module__ == 'builtins':
            logger.debug(f"Skipping built-in class {cls.__name__}")
            return None
            
        # Get the source code
        try:
            code_content = inspect.getsource(cls)
        except (TypeError, OSError) as e:
            logger.debug(f"Could not get source for class {cls.__name__}: {e}")
            return None
            
        code_hash = self._get_code_hash(code_content)
        
        # Check if this exact code already exists
        existing_def = self.session.query(CodeDefinition).filter(
            CodeDefinition.id == code_hash
        ).first()
        
        if existing_def:
            return code_hash
            
        # Check if we have any previous versions of this class
        previous_def = self.session.query(CodeDefinition).filter(
            CodeDefinition.name == cls.__name__,
            CodeDefinition.module_path == cls.__module__
        ).order_by(CodeDefinition.creation_time.desc()).first()
        
        # Get the next version number
        next_version = 1
            
        # Create new code definition
        code_def = CodeDefinition(
            id=code_hash,
            name=cls.__name__,
            type='class',
            module_path=cls.__module__,
            code_content=code_content
        )
        
        self.session.add(code_def)
        
        # Create new version with incremented number
        
        
        try:
            self.session.flush()
        except SQLAlchemyError as e:
            logger.warning(f"Error storing code definition: {e}")
            self.session.rollback()
            # Try to get the definition again (might have been created by another process)
            existing_def = self.session.query(CodeDefinition).filter(
                CodeDefinition.id == code_hash
            ).first()
            if not existing_def:
                raise
            return existing_def.id
            
        return code_hash
    
    def link_object(self, object_ref: str, code_ref: str) -> None:
        """Link an object to its code definition."""
        # Check if link already exists
        existing_link = self.session.query(CodeObjectLink).filter(
            CodeObjectLink.object_id == object_ref,
            CodeObjectLink.definition_id == code_ref
        ).first()
        
        if existing_link:
            return
            
        # Create new link
        link = CodeObjectLink(
            object_id=object_ref,
            definition_id=code_ref
        )
        
        self.session.add(link)
        
        try:
            self.session.flush()
        except SQLAlchemyError as e:
            logger.warning(f"Error creating code link: {e}")
            self.session.rollback()
    
    def get_code(self, code_ref: str) -> Optional[Dict[str, Any]]:
        """Get a code definition by its reference."""
        code_def = self.session.query(CodeDefinition).filter(
            CodeDefinition.id == code_ref
        ).first()
        
        if not code_def:
            return None
            
        # Get the latest version number
        
        

        return {
            'id': code_def.id,
            'name': code_def.name,
            'type': code_def.type,
            'module_path': code_def.module_path,
            'code': code_def.code_content,
            'creation_time': code_def.creation_time,
        }
    
    def get_object_code(self, object_ref: str) -> Optional[Dict[str, Any]]:
        """Get the code definition for an object."""
        link = self.session.query(CodeObjectLink).filter(
            CodeObjectLink.object_id == object_ref
        ).first()
        
        if not link:
            return None
            
        code_def = self.session.query(CodeDefinition).filter(
            CodeDefinition.id == link.definition_id
        ).first()
        
        if not code_def:
            return None
        
            
        return {
            'id': code_def.id,
            'name': code_def.name,
            'type': code_def.type,
            'module_path': code_def.module_path,
            'code': code_def.code_content,
            'creation_time': code_def.creation_time,
        }


    def get_class(self, class_name: str, module_path: str) -> Optional[Type]:
        """Get a class by name and module path. Creates it from stored definition if needed.
        
        Args:
            class_name: Name of the class to load
            module_path: Full module path where the class is defined
            
        Returns:
            The loaded class or None if not found/error loading
        """
        cache_key = f"{module_path}.{class_name}"
        
        # Check cache first
        if cache_key in self._class_cache:
            return self._class_cache[cache_key]
            
        # Try to find the code definition
        code_def = self.session.query(CodeDefinition).filter(
            CodeDefinition.name == class_name,
            CodeDefinition.module_path == module_path,
            CodeDefinition.type == 'class'
        ).first()
        
        if not code_def:
            logger.debug(f"No code definition found for {cache_key}")
            return None
            
        try:
            # Create a new module to hold our class
            module = types.ModuleType(module_path)
            
            # Execute the code in the module's context
            exec(code_def.code_content, module.__dict__)
            
            # Get the class from the module
            cls = getattr(module, class_name)
            
            # Cache the class
            self._class_cache[cache_key] = cls
            
            return cls
        except Exception as e:
            logger.error(f"Error creating class {cache_key}: {e}")
            return None
    
    def clear_class_cache(self) -> None:
        """Clear the class cache."""
        self._class_cache.clear() 