from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, create_engine, LargeBinary, Boolean, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
import datetime
import os
import logging
import sqlite3
import shutil

# Configure logging
logger = logging.getLogger(__name__)

Base = declarative_base()

class StoredObject(Base):
    """Model for storing objects"""
    __tablename__ = 'stored_objects'

    id = Column(String, primary_key=True)
    type_name = Column(String, nullable=False)
    is_primitive = Column(Boolean, nullable=False)
    primitive_value = Column(String, nullable=True)
    pickle_data = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    # Relationships
    versions = relationship("ObjectVersion", back_populates="object", cascade="all, delete-orphan")
    identities = relationship("ObjectIdentity", back_populates="latest_version")

class ObjectVersion(Base):
    """Model for tracking object versions"""
    __tablename__ = 'object_versions'

    id = Column(Integer, primary_key=True)
    object_id = Column(String, ForeignKey('stored_objects.id'), nullable=False)
    identity_id = Column(Integer, ForeignKey('object_identities.id'), nullable=False)
    version_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.now)

    # Relationships
    object = relationship("StoredObject", back_populates="versions")
    identity = relationship("ObjectIdentity", back_populates="versions")

class ObjectIdentity(Base):
    """Model for tracking object identity across versions"""
    __tablename__ = 'object_identities'

    id = Column(Integer, primary_key=True)
    identity_hash = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    creation_time = Column(DateTime, default=datetime.datetime.now)
    latest_version_id = Column(String, ForeignKey('stored_objects.id'), nullable=True)

    # Relationships
    latest_version = relationship("StoredObject", back_populates="identities")
    versions = relationship("ObjectVersion", back_populates="identity", cascade="all, delete-orphan")

class StackSnapshot(Base):
    """Model for storing stack state at each line execution"""
    __tablename__ = 'stack_snapshots'

    id = Column(Integer, primary_key=True)
    function_call_id = Column(Integer, ForeignKey('function_calls.id'), nullable=False)
    line_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.now)
    locals_refs = Column(JSON, nullable=False, default=dict)  # Dict[str, str] mapping variable names to object refs
    globals_refs = Column(JSON, nullable=False, default=dict)  # Dict[str, str] mapping variable names to object refs
    
    # Linked list structure
    previous_snapshot_id = Column(Integer, ForeignKey('stack_snapshots.id'), nullable=True)
    next_snapshot_id = Column(Integer, ForeignKey('stack_snapshots.id'), nullable=True)
    
    # Relationships
    function_call = relationship("FunctionCall", foreign_keys=[function_call_id], back_populates="stack_recording")
    previous_snapshot = relationship("StackSnapshot", foreign_keys=[previous_snapshot_id], remote_side=[id], backref="next_snapshot_ref")
    next_snapshot = relationship("StackSnapshot", foreign_keys=[next_snapshot_id], remote_side=[id], backref="previous_snapshot_ref")

class FunctionCall(Base):
    """Model for storing function call information"""
    __tablename__ = 'function_calls'

    id = Column(Integer, primary_key=True)
    function = Column(String, nullable=False)
    file = Column(String, nullable=True)
    line = Column(Integer, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    call_metadata = Column(JSON, nullable=True)  # For storing additional data like PyRAPL measurements
    
    # Store references to objects
    locals_refs = Column(JSON, nullable=False, default=dict)  # Dict[str, str] mapping variable names to object refs
    globals_refs = Column(JSON, nullable=False, default=dict)  # Dict[str, str] mapping variable names to object refs
    return_ref = Column(String, nullable=True)  # Reference to return value in object manager

    # Store error information
    exception = Column(String, nullable=True)  # Exception information if any
    error_stack_trace = Column(Text, nullable=True)  # Stack trace at the time of error

    # Reference to the first stack snapshot (if line monitoring is enabled)
    first_snapshot_id = Column(Integer, ForeignKey('stack_snapshots.id'), nullable=True)
    
    # Code version tracking
    code_definition_id = Column(String, ForeignKey('code_definitions.id'), nullable=True)
    code_version_id = Column(Integer, ForeignKey('code_versions.id'), nullable=True)
    
    # Relationships
    stack_recording = relationship("StackSnapshot", foreign_keys=[StackSnapshot.function_call_id], back_populates="function_call")
    first_snapshot = relationship("StackSnapshot", foreign_keys=[first_snapshot_id], overlaps="stack_recording")
    code_definition = relationship("CodeDefinition")
    code_version = relationship("CodeVersion")

    # New session relationship
    session_id = Column(Integer, ForeignKey('monitoring_sessions.id'), nullable=True)
    session = relationship("MonitoringSession", back_populates="function_calls")

class CodeDefinition(Base):
    """Represents a code definition (class, function, etc.)."""
    __tablename__ = 'code_definitions'

    id = Column(String, primary_key=True)  # Hash of the code content
    name = Column(String, nullable=False)  # Class/function name
    type = Column(String, nullable=False)  # 'class' or 'function'
    module_path = Column(String, nullable=False)  # Full module path
    code_content = Column(Text, nullable=False)  # The actual code
    first_line_no = Column(Integer, nullable=True)  # Line offset in the file
    creation_time = Column(DateTime, server_default=func.now())
    
    # Relationships
    versions = relationship("CodeVersion", back_populates="definition", cascade="all, delete-orphan")
    objects = relationship("StoredObject", secondary="code_object_links")

class CodeVersion(Base):
    """Represents a version of a code definition."""
    __tablename__ = 'code_versions'

    id = Column(Integer, primary_key=True)
    definition_id = Column(String, ForeignKey('code_definitions.id'), nullable=False)
    version_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, server_default=func.now())
    git_commit = Column(String)  # Optional link to git commit
    git_repo = Column(String)    # Optional link to git repository
    
    # Relationships
    definition = relationship("CodeDefinition", back_populates="versions")

class CodeObjectLink(Base):
    """Links objects to their code definitions."""
    __tablename__ = 'code_object_links'

    id = Column(Integer, primary_key=True)
    object_id = Column(String, ForeignKey('stored_objects.id'), nullable=False)
    definition_id = Column(String, ForeignKey('code_definitions.id'), nullable=False)
    timestamp = Column(DateTime, server_default=func.now())

class MonitoringSession(Base):
    """Model for grouping function calls into a logical session"""
    __tablename__ = 'monitoring_sessions'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)  # Optional name for the session
    description = Column(String, nullable=True)  # Optional description
    start_time = Column(DateTime, nullable=False, default=datetime.datetime.now)
    end_time = Column(DateTime, nullable=True)  # Will be filled when session ends
    
    # Store the structure: function_name -> ordered list of function call ids
    function_calls_map = Column(JSON, nullable=False, default=dict)  # Dict[str, List[int]]
    
    # Store precalculated data
    common_globals = Column(JSON, nullable=False, default=dict)  # Dict[function_name, List[var_name]]
    common_locals = Column(JSON, nullable=False, default=dict)   # Dict[function_name, List[var_name]]
    
    # Metadata about the session - renamed to avoid SQLAlchemy reserved name conflict
    session_metadata = Column(JSON, nullable=True)  # For any additional data
    
    # Relationships
    function_calls = relationship("FunctionCall", back_populates="session")

def init_db(db_path):
    """Initialize the database and return session factory"""
    if db_path != ":memory:":
        # Ensure we have an absolute path for file-based databases
        db_path = os.path.abspath(db_path)
        
        # Create the directory if it doesn't exist
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
        
        try:
            # Check if the database file exists and is valid
            if os.path.exists(db_path):
                try:
                    # Try to open the database to check if it's valid
                    conn = sqlite3.connect(db_path)
                    # Try a simple query to verify the database is functional
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    cursor.fetchall()
                    conn.close()
                    logger.info(f"Successfully connected to existing database at {db_path}")
                except sqlite3.Error as e:
                    # If there's an error, the database might be corrupted
                    logger.error(f"Error connecting to database: {e}")
                    logger.warning(f"Database at {db_path} might be corrupted. Creating backup and new database.")
                    
                    # Create a backup of the potentially corrupted database
                    backup_path = f"{db_path}.backup.{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
                    try:
                        shutil.copy2(db_path, backup_path)
                        logger.info(f"Created backup of potentially corrupted database at {backup_path}")
                        # Remove the original file to create a fresh database
                        os.remove(db_path)
                    except OSError as e:
                        logger.error(f"Failed to create backup: {e}")
                        # If we can't create a backup, try to remove the file
                        try:
                            os.remove(db_path)
                            logger.info(f"Removed potentially corrupted database at {db_path}")
                        except OSError as e2:
                            logger.error(f"Failed to remove corrupted database: {e2}")
                            raise RuntimeError(f"Cannot create or access database at {db_path}. Please check file permissions.")
        except Exception as e:
            logger.error(f"Unexpected error during database initialization: {e}")
    
    # Use appropriate SQLite connection string
    connection_string = 'sqlite:///:memory:' if db_path == ':memory:' else f'sqlite:///{db_path}'
    
    # Create engine with appropriate parameters
    # SQLite doesn't support pool_size, max_overflow, or pool_timeout
    engine = create_engine(
        connection_string, 
        connect_args={
            'check_same_thread': False,
        }
    )
    
    try:
        # Create tables if they don't exist
        Base.metadata.create_all(engine)
        logger.info("Database schema created successfully")
    except Exception as e:
        logger.error(f"Error creating database schema: {e}")
        raise
    
    # Create and return session factory
    # Set expire_on_commit=False to prevent objects from being expired after commit
    # This helps prevent "Parent instance is not bound to a Session" errors
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session 