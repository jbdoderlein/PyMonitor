import types
import logging
from typing import Dict, Any, Optional, Type
from sqlalchemy.orm import Session
from .models import CodeDefinition

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