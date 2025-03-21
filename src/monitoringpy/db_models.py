from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Table, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# Association tables for function calls
function_call_locals = Table(
    'function_call_locals',
    Base.metadata,
    Column('function_call_id', Integer, ForeignKey('function_calls.id')),
    Column('object_id', String, ForeignKey('objects.id')),
    Column('object_version_id', Integer, ForeignKey('object_versions.id')),
    Column('arg_name', String)
)

function_call_globals = Table(
    'function_call_globals',
    Base.metadata,
    Column('function_call_id', Integer, ForeignKey('function_calls.id')),
    Column('object_id', String, ForeignKey('objects.id')),
    Column('object_version_id', Integer, ForeignKey('object_versions.id')),
    Column('var_name', String)
)

class FunctionCall(Base):
    """Model for storing function call information"""
    __tablename__ = 'function_calls'

    id = Column(Integer, primary_key=True)
    event_type = Column(String)
    function = Column(String)
    file = Column(String)
    line = Column(Integer)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    perf_label = Column(String)
    perf_pkg = Column(Float)
    perf_dram = Column(Float)
    return_object_id = Column(String, ForeignKey('objects.id'))
    return_object_version_id = Column(Integer, ForeignKey('object_versions.id'))

    # Relationships
    locals = relationship('Object', secondary=function_call_locals, backref='function_calls_as_local')
    globals = relationship('Object', secondary=function_call_globals, backref='function_calls_as_global')
    return_object = relationship('Object', foreign_keys=[return_object_id])

class Object(Base):
    """Model for storing object data"""
    __tablename__ = 'objects'

    id = Column(String, primary_key=True)
    type_name = Column(String)
    is_primitive = Column(Boolean, default=False)
    primitive_value = Column(String)
    pickle_data = Column(String)
    object_structure = Column(JSON)

    # Relationships
    attributes = relationship('ObjectAttribute', backref='parent', cascade='all, delete-orphan')
    items = relationship('ObjectItem', backref='parent', cascade='all, delete-orphan')

class ObjectAttribute(Base):
    """Model for storing object attributes"""
    __tablename__ = 'object_attributes'

    id = Column(Integer, primary_key=True)
    parent_id = Column(String, ForeignKey('objects.id'))
    name = Column(String)
    value_id = Column(String, ForeignKey('objects.id'))

class ObjectItem(Base):
    """Model for storing object items (for lists, dicts, etc.)"""
    __tablename__ = 'object_items'

    id = Column(Integer, primary_key=True)
    parent_id = Column(String, ForeignKey('objects.id'))
    key = Column(String)
    value_id = Column(String, ForeignKey('objects.id'))

class ObjectIdentity(Base):
    """Model for tracking object identity across versions"""
    __tablename__ = 'object_identities'

    id = Column(Integer, primary_key=True)
    identity_hash = Column(String, unique=True)
    name = Column(String)
    creation_time = Column(DateTime)
    latest_version_id = Column(String, ForeignKey('objects.id'))

    # Relationships
    versions = relationship('ObjectVersion', backref='identity', cascade='all, delete-orphan')

class ObjectVersion(Base):
    """Model for storing object versions"""
    __tablename__ = 'object_versions'

    id = Column(Integer, primary_key=True)
    identity_id = Column(Integer, ForeignKey('object_identities.id'))
    object_id = Column(String, ForeignKey('objects.id'))
    version_number = Column(Integer)
    timestamp = Column(DateTime)

    # Relationships
    object = relationship('Object', backref='versions') 