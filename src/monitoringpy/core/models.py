from sqlalchemy import String, DateTime, Integer, ForeignKey, create_engine, LargeBinary, Boolean, JSON, Text, desc, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
import datetime
import os
import logging
import shutil
import sqlite3

# Configure logging
logger = logging.getLogger(__name__)

Base = declarative_base()

class ObjectIdentity(Base):
    """Model for tracking object identity"""
    __tablename__ = 'object_identities'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identity_hash: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    creation_time: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    
    # Relationship - one identity has many object states/versions
    versions = relationship("StoredObject", back_populates="identity", order_by="StoredObject.version_number")
    
    def get_latest_version(self, session=None):
        """Get the latest version using a direct query
        
        Args:
            session: SQLAlchemy session to use (optional)
        
        Returns:
            The latest StoredObject version or None
        """
        if session is None:
            # If no session provided, we can't query
            return None
            
        # Use SQLAlchemy query to get the latest version by version_number
        return session.query(StoredObject).filter(
            StoredObject.identity_id == self.id
        ).order_by(desc(StoredObject.version_number)).first()

class StoredObject(Base):
    """Model for storing object versions"""
    __tablename__ = 'stored_objects'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    identity_id: Mapped[int] = mapped_column(Integer, ForeignKey('object_identities.id'), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    type_name: Mapped[str] = mapped_column(String, nullable=False)
    is_primitive: Mapped[bool] = mapped_column(Boolean, nullable=False)
    primitive_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pickle_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    
    # Relationships
    identity = relationship("ObjectIdentity", back_populates="versions")
    code_definitions = relationship("CodeDefinition", secondary="code_object_links", back_populates="objects")

class StackSnapshot(Base):
    """Model for storing stack state at each line execution
    
    Each snapshot represents the state of local and global variables
    at a specific line during function execution. Snapshots form a 
    chronological sequence within a function call.
    """
    __tablename__ = 'stack_snapshots'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    function_call_id: Mapped[int] = mapped_column(Integer, ForeignKey('function_calls.id'), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.now)
    locals_refs: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)  # Dict[str, str] mapping variable names to object refs
    globals_refs: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)  # Dict[str, str] mapping variable names to object refs
    
    # Chronological ordering within a function call
    order_in_call: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Position in the execution sequence
    
    # Relationships
    function_call = relationship("FunctionCall", back_populates="stack_snapshots")
    next_snapshot_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('stack_snapshots.id'), nullable=True)
    next_snapshot = relationship("StackSnapshot", foreign_keys=[next_snapshot_id], remote_side=[id], uselist=False)
    
    def get_previous_snapshot(self, session):
        """Get the previous snapshot in the execution sequence.
        
        Args:
            session: SQLAlchemy session to use for query
            
        Returns:
            The previous StackSnapshot or None if this is the first snapshot
        """
        return session.query(StackSnapshot).filter(
            StackSnapshot.function_call_id == self.function_call_id,
            StackSnapshot.order_in_call < self.order_in_call
        ).order_by(desc(StackSnapshot.order_in_call)).first()
        
    @property
    def is_first_in_call(self):
        """Return True if this is the first snapshot in its function call"""
        return self.order_in_call == 0
        
    @property
    def is_last_in_call(self):
        """Return True if this is the last snapshot in its function call"""
        return self.next_snapshot_id is None

class FunctionCall(Base):
    """Model for storing function call information"""
    __tablename__ = 'function_calls'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    function: Mapped[str] = mapped_column(String, nullable=False)
    file: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    line: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)
    call_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # For storing additional data like PyRAPL measurements
    
    # Store references to objects
    locals_refs: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)  # Dict[str, str] mapping variable names to object refs
    globals_refs: Mapped[Dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)  # Dict[str, str] mapping variable names to object refs
    return_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Reference to return value in object manager

    # Code version tracking
    code_definition_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey('code_definitions.id'), nullable=True)
    
    # Session relationship
    session_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('monitoring_sessions.id'), nullable=True)

    # Hierarchical structure - parent/child relationships
    parent_call_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('function_calls.id'), nullable=True)
    
    # Ordering within the parent function (position among siblings)
    order_in_parent: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Chronological ordering within a session
    order_in_session: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Position in the session sequence
    
    # First snapshot reference for efficient stack trace retrieval
    first_snapshot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Relationships
    session = relationship("MonitoringSession", foreign_keys=[session_id], back_populates="function_calls")
    stack_snapshots = relationship("StackSnapshot", back_populates="function_call", order_by="StackSnapshot.timestamp")
    code_definition = relationship("CodeDefinition", back_populates="function_calls")
    parent_call = relationship("FunctionCall", foreign_keys=[parent_call_id], remote_side=[id], backref="child_calls")
    
    def get_child_calls(self, session : Session):
        """Get all child function calls ordered by their execution sequence
        
        Args:
            session: SQLAlchemy session to use for query
            
        Returns:
            List of child FunctionCall objects in execution order
        """
        return session.query(FunctionCall).filter(
            FunctionCall.parent_call_id == self.id
        ).order_by(FunctionCall.order_in_parent, FunctionCall.start_time).all()
    
    def get_execution_tree(self, session, max_depth=None, current_depth=0):
        """Recursively build the execution tree starting from this function call
        
        Args:
            session: SQLAlchemy session to use for query
            max_depth: Maximum depth to traverse (None for unlimited)
            current_depth: Current depth in the recursion
            
        Returns:
            Dict containing this call's info and its child calls
        """
        # Stop recursion if we've reached max depth
        if max_depth is not None and current_depth >= max_depth:
            return {"id": self.id, "function": self.function, "has_children": bool(self.child_calls)}
        
        # Get child calls ordered by execution
        children = self.get_child_calls(session)
        
        # Build the current node
        node = {
            "id": self.id,
            "function": self.function,
            "file": self.file,
            "line": self.line,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "return_ref": self.return_ref,
            "children": []
        }
        
        # Recursively add children
        for child in children:
            child_node = child.get_execution_tree(
                session, 
                max_depth=max_depth, 
                current_depth=current_depth + 1
            )
            node["children"].append(child_node)
            
        return node

    def to_dict(self):
        """Convert the FunctionCall object to a dictionary for API responses"""
        return {
            "id": self.id,
            "function": self.function,
            "file": self.file,
            "line": self.line,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "call_metadata": self.call_metadata,
            "locals_refs": self.locals_refs,
            "globals_refs": self.globals_refs,
            "return_ref": self.return_ref,
            "code_definition_id": self.code_definition_id,
            "session_id": self.session_id,
            "parent_call_id": self.parent_call_id,
            "order_in_parent": self.order_in_parent,
            "order_in_session": self.order_in_session,
            "first_snapshot_id": self.first_snapshot_id
        }

class CodeDefinition(Base):
    """Represents a code definition (class, function, etc.).
    
    This stores the actual code content of functions and classes that are monitored,
    allowing replay and analysis of the exact code version used during execution.
    """
    __tablename__ = 'code_definitions'

    id: Mapped[str] = mapped_column(String, primary_key=True)  # Hash of the code content
    name: Mapped[str] = mapped_column(String, nullable=False)  # Class/function name
    type: Mapped[str] = mapped_column(String, nullable=False)  # 'class' or 'function'
    module_path: Mapped[str] = mapped_column(String, nullable=False)  # Full module path
    code_content: Mapped[str] = mapped_column(Text, nullable=False)  # The actual code
    first_line_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Line offset in the file
    creation_time: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Direct relationships
    function_calls = relationship("FunctionCall", back_populates="code_definition")
    objects = relationship("StoredObject", secondary="code_object_links", back_populates="code_definitions")

class CodeObjectLink(Base):
    """Links objects to their code definitions.
    
    This is a many-to-many join table that connects StoredObjects with CodeDefinitions.
    It allows tracking which objects were created by which code definitions,
    enabling features like:
    1. Finding all objects created by a particular class/function
    2. Seeing the source code that created a given object
    3. Analyzing changes in object creation across code versions
    """
    __tablename__ = 'code_object_links'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    object_id: Mapped[str] = mapped_column(String, ForeignKey('stored_objects.id'), nullable=False)
    definition_id: Mapped[str] = mapped_column(String, ForeignKey('code_definitions.id'), nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Add indexes for faster queries
    __table_args__ = (
        Index('idx_code_object_link_object', 'object_id'),
        Index('idx_code_object_link_definition', 'definition_id'),
    )

class MonitoringSession(Base):
    """Model for grouping function calls into a logical session
    
    A monitoring session represents a continuous period of execution monitoring,
    typically corresponding to a single run of a program or a specific task.
    It provides organization and context for function calls captured during that period.
    """
    __tablename__ = 'monitoring_sessions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Optional name for the session
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Optional description
    start_time: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=False, default=datetime.datetime.now)
    end_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, nullable=True)  # Will be filled when session ends
    
    # Metadata about the session - renamed to avoid SQLAlchemy reserved name conflict
    session_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)  # For any additional data
    
    # Relationships
    function_calls = relationship("FunctionCall", foreign_keys=[FunctionCall.session_id], back_populates="session")
    
    @property
    def duration(self):
        """Return the duration of the session in seconds, or None if session is still active"""
        end_time_value = getattr(self, 'end_time', None)
        if not end_time_value:
            return None
        start_time_value = getattr(self, 'start_time', None)
        if not start_time_value:
            return None
        return (end_time_value - start_time_value).total_seconds()
    
    def get_function_calls_by_name(self, session, function_name):
        """Get all function calls with the given name in this session
        
        Args:
            session: SQLAlchemy session to use for query
            function_name: Name of the function to find calls for
            
        Returns:
            List of FunctionCall objects for the given function name
        """
        return session.query(FunctionCall).filter(
            FunctionCall.session_id == self.id,
            FunctionCall.function == function_name
        ).order_by(FunctionCall.order_in_session).all()
    
    def get_call_sequence(self, session):
        """Get the chronological sequence of top-level function calls in this session
        
        Args:
            session: SQLAlchemy session to use for query
            
        Returns:
            List of FunctionCall objects in chronological order
        """
        return session.query(FunctionCall).filter(
            FunctionCall.session_id == self.id,
            FunctionCall.parent_call_id is None  # Only top-level calls
        ).order_by(FunctionCall.order_in_session).all()

def init_db(db_path, in_memory=True):
    """Initialize the database and return session factory
    
    Args:
        db_path: Path to the SQLite database file or ':memory:' for in-memory database
        in_memory: Whether to use an in-memory database (default: True)
        
    Returns:
        SQLAlchemy Session factory configured for the database
    
    Raises:
        RuntimeError: If database initialization fails
    """
    try:
        # Handle file-based databases
        if in_memory:
            dest = sqlite3.connect(':memory:')
            if db_path != ":memory:":
                # Ensure we have an absolute path
                db_path = os.path.abspath(db_path)
                
                # If database exists but appears corrupted, create a backup
                if os.path.exists(db_path):
                    source = sqlite3.connect(db_path)
                    source.backup(dest)
                    db_path = ':memory:'
        else:
            dest = sqlite3.connect(db_path)


        def get_connection():
            # just a debug print to verify that it's indeed getting called: 
            return dest

        engine = create_engine('sqlite://', creator = get_connection)

        # Create tables
        Base.metadata.create_all(engine)
        
        # Create and return session factory
        return sessionmaker(bind=engine, expire_on_commit=False)
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise RuntimeError(f"Failed to initialize database: {e}") from e 
    

def export_db(session : "Session", db_path: str):
    """Exports the current sessionto a specified file.

    Args:
        session: The session to export
        db_path: The path to the file where the database should be saved.

    """
    source_engine = session.get_bind()

    # Ensure any pending changes are committed to release potential locks
    try:
        session.commit()
    except Exception as e:
        logger.error(f"Error committing session before export: {e}. Attempting rollback.")
        session.rollback()

    source_conn = None
    target_conn = None
    try:
        # Get the raw DBAPI connection from the engine
        dbapi_connection = source_engine.raw_connection() # type: ignore
        
        # Extract the actual sqlite3 connection object
        # This might be nested depending on SQLAlchemy version/setup
        if hasattr(dbapi_connection, 'connection'): # Standard DBAPI connection wrapper
            source_conn = dbapi_connection.connection # type: ignore
        else: # Might be the raw connection itself
            source_conn = dbapi_connection

        # Verify it's an SQLite connection
        if not isinstance(source_conn, sqlite3.Connection):
                raise TypeError(f"Database connection is not a sqlite3 connection. Type is {type(source_conn)}")
        
        # Create a connection to the target file database
        target_conn = sqlite3.connect(db_path)

        # Perform the backup
        with target_conn: # 'with target_conn' handles commit/rollback on the target
            source_conn.backup(target_conn)


        target_conn.close()
        logger.info(f"Closed target database connection: {db_path}")
        
    except Exception as e:
        logger.error(f"Error exporting database: {e}")
        raise RuntimeError(f"Failed to export database: {e}") from e 