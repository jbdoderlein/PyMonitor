from sqlalchemy import Column, String, Text, DateTime, Integer, Float, ForeignKey, create_engine, Table, LargeBinary, Boolean, JSON, inspect
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import json
import pickle
import hashlib
import os
import logging
import sqlite3
import shutil

# Configure logging
logger = logging.getLogger(__name__)

Base = declarative_base()

# Association tables for many-to-many relationships
function_call_locals = Table(
    'function_call_locals',
    Base.metadata,
    Column('function_call_id', Integer, ForeignKey('function_calls.id'), primary_key=True),
    Column('object_id', String, ForeignKey('objects.id'), primary_key=True),
    Column('object_version_id', Integer, ForeignKey('object_versions.id'), nullable=True),  # Reference to specific version
    Column('arg_name', String, primary_key=True)
)

function_call_globals = Table(
    'function_call_globals',
    Base.metadata,
    Column('function_call_id', Integer, ForeignKey('function_calls.id'), primary_key=True),
    Column('object_id', String, ForeignKey('objects.id'), primary_key=True),
    Column('object_version_id', Integer, ForeignKey('object_versions.id'), nullable=True),  # Reference to specific version
    Column('var_name', String, primary_key=True)
)

# New table for object identity tracking
class ObjectIdentity(Base):
    """Model for tracking object identity across versions"""
    __tablename__ = 'object_identities'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing ID
    identity_hash = Column(String, unique=True)  # Stable hash for the object identity
    name = Column(String)  # Object name if available (e.g., variable name)
    creation_time = Column(DateTime, default=datetime.datetime.now)
    latest_version_id = Column(String, ForeignKey('objects.id'), nullable=True)
    
    # Relationships
    versions = relationship("ObjectVersion", back_populates="identity", cascade="all, delete-orphan")
    latest_version = relationship("Object", foreign_keys=[latest_version_id])

# New table for object version tracking
class ObjectVersion(Base):
    """Model for tracking versions of objects"""
    __tablename__ = 'object_versions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing ID
    identity_id = Column(Integer, ForeignKey('object_identities.id'))
    object_id = Column(String, ForeignKey('objects.id'))
    version_number = Column(Integer)
    timestamp = Column(DateTime, default=datetime.datetime.now)
    
    # Relationships
    identity = relationship("ObjectIdentity", back_populates="versions")
    object = relationship("Object", foreign_keys=[object_id])

class Object(Base):
    """Model for storing objects with their structure"""
    __tablename__ = 'objects'
    
    id = Column(String, primary_key=True)  # Hash of the object
    type_name = Column(String)  # Type of the object (e.g., 'list', 'dict', 'CustomClass')
    is_primitive = Column(Boolean, default=False)  # Whether this is a primitive type
    primitive_value = Column(Text, nullable=True)  # For primitive types like int, str, etc.
    object_structure = Column(JSON, nullable=True)  # For structured objects (dict, list, etc.)
    pickle_data = Column(LargeBinary, nullable=True)  # Fallback for complex objects
    
    # Relationships - explicitly specify foreign keys to avoid ambiguity
    attributes = relationship(
        "ObjectAttribute", 
        foreign_keys="[ObjectAttribute.parent_id]",
        back_populates="parent_object", 
        cascade="all, delete-orphan"
    )
    items = relationship(
        "ObjectItem", 
        foreign_keys="[ObjectItem.parent_id]",
        back_populates="parent_object", 
        cascade="all, delete-orphan"
    )
    
    # Function call relationships
    local_in_calls = relationship("FunctionCall", secondary=function_call_locals, back_populates="local_objects")
    global_in_calls = relationship("FunctionCall", secondary=function_call_globals, back_populates="global_objects")
    return_from_calls = relationship("FunctionCall", back_populates="return_object")
    
    # Version relationships
    versions = relationship("ObjectVersion", foreign_keys=[ObjectVersion.object_id], back_populates="object")

class ObjectAttribute(Base):
    """Model for storing object attributes"""
    __tablename__ = 'object_attributes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing ID
    parent_id = Column(String, ForeignKey('objects.id'))
    name = Column(String)  # Attribute name
    value_id = Column(String, ForeignKey('objects.id'))  # Reference to the attribute value
    
    # Relationships - explicitly specify foreign keys to avoid ambiguity
    parent_object = relationship("Object", foreign_keys=[parent_id], back_populates="attributes")
    value_object = relationship("Object", foreign_keys=[value_id])

class ObjectItem(Base):
    """Model for storing collection items (list items, dict values, etc.)"""
    __tablename__ = 'object_items'
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # Auto-incrementing ID
    parent_id = Column(String, ForeignKey('objects.id'))
    key = Column(String)  # Key (for dicts) or index (for lists)
    value_id = Column(String, ForeignKey('objects.id'))  # Reference to the item value
    
    # Relationships - explicitly specify foreign keys to avoid ambiguity
    parent_object = relationship("Object", foreign_keys=[parent_id], back_populates="items")
    value_object = relationship("Object", foreign_keys=[value_id])

class FunctionCall(Base):
    __tablename__ = 'function_calls'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String)
    file = Column(String)
    function = Column(String)
    line = Column(Integer)
    start_time = Column(DateTime)
    end_time = Column(DateTime, nullable=True)
    
    # Return value - direct relationship
    return_object_id = Column(String, ForeignKey('objects.id'), nullable=True)
    return_object_version_id = Column(Integer, ForeignKey('object_versions.id'), nullable=True)  # Reference to specific version
    
    # Performance metrics if pyRAPL is enabled
    perf_label = Column(String, nullable=True)
    perf_pkg = Column(Float, nullable=True)
    perf_dram = Column(Float, nullable=True)
    
    # Relationships - maintain separation between locals and globals
    local_objects = relationship("Object", secondary=function_call_locals, back_populates="local_in_calls")
    global_objects = relationship("Object", secondary=function_call_globals, back_populates="global_in_calls")
    return_object = relationship("Object", foreign_keys=[return_object_id], back_populates="return_from_calls")
    return_object_version = relationship("ObjectVersion", foreign_keys=[return_object_version_id])

def migrate_database_schema(engine):
    """
    Check if the database schema matches the models and perform migrations if needed.
    
    Args:
        engine: SQLAlchemy engine
        
    Returns:
        bool: True if migration was successful, False otherwise
    """
    try:
        inspector = inspect(engine)
        
        # Check if function_calls table exists and has the required columns
        if 'function_calls' in inspector.get_table_names():
            function_calls_columns = [col['name'] for col in inspector.get_columns('function_calls')]
            
            # Check if return_object_id column exists
            if 'return_object_id' not in function_calls_columns:
                logger.warning("Database schema is outdated: missing return_object_id column")
                
                # Add the missing column
                with engine.connect() as conn:
                    conn.execute("ALTER TABLE function_calls ADD COLUMN return_object_id VARCHAR REFERENCES objects(id)")
                    logger.info("Added return_object_id column to function_calls table")
        
        # Check other tables and columns as needed
        # ...
        
        return True
    except Exception as e:
        logger.error(f"Error during schema migration: {e}")
        return False

def init_db(db_path):
    """Initialize the database and return session factory"""
    # Ensure we have an absolute path
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
    
    # Use a standard SQLite connection string with absolute path
    engine = create_engine(
        f'sqlite:///{db_path}', 
        connect_args={
            'check_same_thread': False,
            'timeout': 60  # Increase SQLite timeout to 60 seconds (default is 5)
        },
        # Increase pool size and overflow to handle more connections
        pool_size=20,  # Default is 5
        max_overflow=20,  # Default is 10
        pool_timeout=60,  # Default is 30
        pool_recycle=1800  # Recycle connections after 30 minutes
    )
    
    try:
        # Create tables if they don't exist
        Base.metadata.create_all(engine)
        logger.info("Database schema created successfully")
        
        # Check if we need to migrate the schema
        if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
            if migrate_database_schema(engine):
                logger.info("Database schema migration completed successfully")
            else:
                logger.warning("Database schema migration failed")
    except Exception as e:
        logger.error(f"Error creating database schema: {e}")
        raise
    
    # Create and return session factory
    # Set expire_on_commit=False to prevent objects from being expired after commit
    # This helps prevent "Parent instance is not bound to a Session" errors
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return Session 