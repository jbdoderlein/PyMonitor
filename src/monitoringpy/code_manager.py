import inspect
import hashlib
from typing import Optional, Dict, List, Any, Type
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import logging
from .models import CodeDefinition, CodeVersion, CodeObjectLink, StoredObject

logger = logging.getLogger(__name__)

class CodeManager:
    """Manages code definitions in the database."""
    
    def __init__(self, session: Session):
        self.session = session
    
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
            
        # Create new code definition
        code_def = CodeDefinition(
            id=code_hash,
            name=cls.__name__,
            type='class',
            module_path=cls.__module__,
            code_content=code_content
        )
        
        self.session.add(code_def)
        
        # Create initial version
        version = CodeVersion(
            definition=code_def,
            version_number=1
        )
        
        self.session.add(version)
        
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
            
        return {
            'id': code_def.id,
            'name': code_def.name,
            'type': code_def.type,
            'module_path': code_def.module_path,
            'code_content': code_def.code_content,
            'creation_time': code_def.creation_time
        }
    
    def get_object_code(self, object_ref: str) -> Optional[Dict[str, Any]]:
        """Get the code definition for an object."""
        link = self.session.query(CodeObjectLink).filter(
            CodeObjectLink.object_id == object_ref
        ).first()
        
        if not link:
            return None
            
        return self.get_code(link.definition_id)
    
    def get_code_history(self, code_ref: str) -> List[Dict[str, Any]]:
        """Get the version history of a code definition."""
        versions = self.session.query(CodeVersion).filter(
            CodeVersion.definition_id == code_ref
        ).order_by(CodeVersion.version_number.asc()).all()
        
        return [{
            'version_number': v.version_number,
            'timestamp': v.timestamp,
            'git_commit': v.git_commit,
            'git_repo': v.git_repo
        } for v in versions] 