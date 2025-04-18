from typing import Dict, Any, Optional, TypedDict, List, Union
from sqlalchemy.orm import Session
import datetime
import inspect
from .representation import ObjectManager
from .models import StoredObject, FunctionCall, StackSnapshot, CodeDefinition
from sqlalchemy import text

class FunctionCallInfo(TypedDict):
    """Type definition for function call information"""
    function: str
    file: Optional[str]
    line: Optional[int]
    start_time: datetime.datetime
    end_time: Optional[datetime.datetime]
    locals: Dict[str, Any]
    globals: Dict[str, Any]
    return_value: Optional[Any]
    energy_data: Optional[Dict[str, Any]]
    code_definition_id: Optional[str]
    code_version_id: Optional[int]
    code: Optional[Dict[str, Any]]  # Contains code content, module_path, and type

class FunctionCallTracker:
    """Track function calls and their context using object manager for efficient storage"""
    
    def __init__(self, session: Session, monitor=None) -> None:
        self.session = session
        self.monitor = monitor
        self.object_manager = ObjectManager(session)
        self.call_history = []
        self.current_call = None

    def _store_variables(self, variables: Dict[str, Any]) -> Dict[str, str]:
        """Store variables and return a dictionary of variable names to object references"""
        refs = {}
        for name, value in variables.items():
            # Skip special variables and functions
            if name.startswith('__') or callable(value):
                continue
            try:
                # Store the value and get its reference
                ref = self.object_manager.store(value)
                # Always store the reference, not the value
                refs[name] = ref
            except Exception as e:
                # Log warning but continue if we can't store a variable
                print(f"Warning: Could not store variable {name}: {e}")
        return refs

    def capture_call(self, func_name: str, locals_dict: Dict[str, Any], globals_dict: Dict[str, Any], 
                    code_definition_id: Optional[str] = None, code_version_id: Optional[int] = None,
                    file_name: Optional[str] = None, line_number: Optional[int] = None) -> str:
        """
        Capture a function call with its local and global context.
        Returns the function call ID.
        """
        # Store local and global variables
        locals_refs = self._store_variables(locals_dict)
        globals_refs = self._store_variables(globals_dict)

        # Create function call record
        call = FunctionCall(
            function=func_name,
            file=file_name,
            line=line_number,
            start_time=datetime.datetime.now(),
            locals_refs=locals_refs,
            globals_refs=globals_refs,
            code_definition_id=code_definition_id,
            code_version_id=code_version_id
        )
        
        self.session.add(call)
        self.session.flush()
        return str(call.id)

    def capture_return(self, call_id: str, return_value: Any) -> None:
        """
        Capture the return value of a function call.
        Raises ValueError if call_id doesn't exist.
        """
        # Get the function call
        call = self.session.query(FunctionCall).filter(FunctionCall.id == int(call_id)).first()
        if not call:
            raise ValueError(f"Function call {call_id} not found")

        # Store return value
        try:
            return_ref = self.object_manager.store(return_value)
            call.return_ref = return_ref
            call.end_time = datetime.datetime.now()
            self.session.commit()
        except Exception as e:
            print(f"Warning: Could not store return value: {e}")
            self.session.rollback()

    def get_call(self, call_id: str) -> FunctionCallInfo:
        """
        Get all information about a function call.
        Returns references to stored objects, not the actual values.
        Use object_manager.rehydrate() to get actual values.
        
        Raises ValueError if call_id doesn't exist.
        """
        call = self.session.query(FunctionCall).filter(FunctionCall.id == int(call_id)).first()
        if not call:
            raise ValueError(f"Function call {call_id} not found")

        # Get the stored references
        locals_dict = call.locals_refs if call.locals_refs else {}
        globals_dict = call.globals_refs if call.globals_refs else {}
        return_value = call.return_ref

        # Get energy data from call_metadata if available
        energy_data = call.call_metadata.get('energy_data') if call.call_metadata else None

        # Get code information if available
        code = None
        if call.code_definition_id:
            try:
                sql = text("SELECT * FROM code_definitions WHERE id = :id")
                result = self.session.execute(sql, {"id": call.code_definition_id})
                row = result.fetchone()
                if row:
                    code = {
                        'content': row.code_content,
                        'module_path': row.module_path,
                        'type': row.type
                    }
            except Exception as e:
                print(f"Error retrieving code definition for {call.code_definition_id}: {e}")

        return FunctionCallInfo(
            function=call.function,
            file=call.file,
            line=call.line,
            start_time=call.start_time,
            end_time=call.end_time,
            locals=locals_dict,
            globals=globals_dict,
            return_value=return_value,
            energy_data=energy_data,
            code_definition_id=call.code_definition_id,
            code_version_id=call.code_version_id,
            code=code
        )

    def get_call_history(self, function_name: Optional[str] = None) -> List[str]:
        """
        Get the history of function calls, optionally filtered by function name.
        Returns a list of call IDs.
        """
        query = self.session.query(FunctionCall)
        if function_name:
            query = query.filter(FunctionCall.function == function_name)
        calls = query.order_by(FunctionCall.start_time.asc()).all()
        return [str(call.id) for call in calls]

    def get_functions_with_traces(self) -> List[Dict[str, Any]]:
        """
        Get a list of functions that have stack traces.
        Returns a list of dictionaries containing:
        - id: function call ID
        - function: function name
        - trace_count: number of stack snapshots
        - file: file path
        - line: line number
        - first_occurrence: timestamp of first call
        - last_occurrence: timestamp of last call
        """
        try:
            # Use SQL to get a list of functions with their trace counts and other info
            sql_str = """
                SELECT 
                    f.id,
                    f.function,
                    COUNT(s.id) as trace_count,
                    f.file,
                    f.line,
                    MIN(f.start_time) as first_occurrence,
                    MAX(f.start_time) as last_occurrence
                FROM 
                    function_calls f
                LEFT JOIN 
                    stack_snapshots s ON f.id = s.function_call_id
                GROUP BY 
                    f.function, f.file, f.line
                HAVING 
                    COUNT(s.id) > 0
                ORDER BY 
                    f.function
            """
            
            sql = text(sql_str)
            result = self.session.execute(sql)
            functions = []
            
            for row in result:
                functions.append({
                    "id": str(row.id),
                    "function": row.function,
                    "trace_count": row.trace_count,
                    "file": row.file,
                    "line": row.line,
                    "first_occurrence": row.first_occurrence,
                    "last_occurrence": row.last_occurrence
                })
                
            return functions
        except Exception as e:
            print(f"Error getting functions with traces: {e}")
            return []
    
    def get_function_traces(self, function_id: Union[str, int]) -> List[Dict[str, Any]]:
        """
        Get all traces for a specific function call ID.
        Returns a list of dictionaries containing trace details.
        """
        try:
            # Convert function_id to int if it's a string
            if isinstance(function_id, str):
                try:
                    function_id = int(function_id)
                except ValueError:
                    print(f"Error: Invalid function ID: {function_id}")
                    return []
            
            # Get the function call
            function_call = self.session.query(FunctionCall).filter(FunctionCall.id == function_id).first()
            if not function_call:
                print(f"Error: Function call {function_id} not found")
                return []
            
            # Get all stack snapshots for this function call
            snapshots = self.session.query(StackSnapshot).filter(
                StackSnapshot.function_call_id == function_id
            ).order_by(StackSnapshot.timestamp.asc()).all()
            
            # Get code information if available
            code = None
            if function_call.code_definition_id:
                try:
                    code_definition = self.session.query(CodeDefinition).filter(
                        CodeDefinition.id == function_call.code_definition_id
                    ).first()
                    
                    if code_definition:
                        code = {
                            'content': code_definition.code_content,
                            'module_path': code_definition.module_path,
                            'type': code_definition.type,
                            'name': code_definition.name
                        }
                except Exception as e:
                    print(f"Error retrieving code definition: {e}")
            
            traces = []
            for snapshot in snapshots:
                # Convert datetime to string to avoid serialization issues
                start_time_str = function_call.start_time.isoformat() if function_call.start_time else None
                end_time_str = function_call.end_time.isoformat() if function_call.end_time else None
                
                trace_data = {
                    "id": str(snapshot.id),
                    "function": function_call.function,
                    "file": function_call.file,
                    "line": snapshot.line_number,
                    "time": start_time_str,
                    "end_time": end_time_str,
                    "snapshot_id": str(snapshot.id),
                    "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
                    "call_metadata": function_call.call_metadata,
                    "locals_refs": snapshot.locals_refs,
                    "globals_refs": snapshot.globals_refs,
                    "previous_snapshot_id": str(snapshot.previous_snapshot_id) if snapshot.previous_snapshot_id else None,
                    "next_snapshot_id": str(snapshot.next_snapshot_id) if snapshot.next_snapshot_id else None
                }
                
                # Add code information if available
                if code:
                    trace_data["code"] = code
                
                # Add code version ID if available
                if function_call.code_version_id:
                    trace_data["code_version_id"] = function_call.code_version_id
                
                traces.append(trace_data)
                
            return traces
        except Exception as e:
            print(f"Error getting function traces: {e}")
            return []

    def update_metadata(self, call_id: str, metadata: dict) -> None:
        """Update the metadata for a function call.
        
        Args:
            call_id: The ID of the function call to update
            metadata: Dictionary containing metadata to store
        """
        try:
            call = self.session.query(FunctionCall).filter_by(id=call_id).first()
            if call:
                # If there's existing metadata, merge it with the new data
                if call.call_metadata:
                    call.call_metadata.update(metadata)
                else:
                    call.call_metadata = metadata
                self.session.commit()
        except Exception as e:
            print(f"Error updating metadata for call {call_id}: {e}")
            self.session.rollback()

    def create_stack_snapshot(self, call_id: str, line_number: int, locals_dict: Dict[str, str], globals_dict: Dict[str, str]) -> StackSnapshot:
        """
        Create a new stack snapshot for a function call at a specific line.
        
        Args:
            call_id: The ID of the function call
            line_number: The line number where the snapshot was taken
            locals_dict: Dictionary of local variable references
            globals_dict: Dictionary of global variable references
            
        Returns:
            The created StackSnapshot object
        """
        try:
            # Get the function call
            call = self.session.query(FunctionCall).filter(FunctionCall.id == int(call_id)).first()
            if not call:
                raise ValueError(f"Function call {call_id} not found")

            # Get the latest snapshot for this call
            latest_snapshot = self.session.query(StackSnapshot).filter(
                StackSnapshot.function_call_id == int(call_id)
            ).order_by(StackSnapshot.timestamp.desc()).first()
            
            # Create the new snapshot
            snapshot = StackSnapshot(
                function_call_id=int(call_id),
                line_number=line_number,
                locals_refs=locals_dict,
                globals_refs=globals_dict,
                previous_snapshot_id=latest_snapshot.id if latest_snapshot else None
            )
            
            # Add to session and commit
            self.session.add(snapshot)
            self.session.flush()
            
            # Update the next reference on the previous snapshot
            if latest_snapshot:
                latest_snapshot.next_snapshot_id = snapshot.id
            
            # If this is the first snapshot, update the function call's reference to it
            if not call.first_snapshot_id:
                call.first_snapshot_id = snapshot.id
            
            self.session.commit()
            return snapshot
            
        except Exception as e:
            self.session.rollback()
            print(f"Error creating stack snapshot: {e}")
            raise

    def delete_call(self, call_id: str) -> bool:
        """
        Delete a function call and all associated stack snapshots.
        
        Args:
            call_id: The ID of the function call to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert string ID to integer if needed
            try:
                id_int = int(call_id)
            except ValueError:
                print(f"Error: Invalid function call ID: {call_id}")
                return False
            
            # Get the function call
            call = self.session.query(FunctionCall).filter(FunctionCall.id == id_int).first()
            if not call:
                print(f"Error: Function call {call_id} not found")
                return False
            
            # Delete all stack snapshots associated with this function call
            snapshots = self.session.query(StackSnapshot).filter(StackSnapshot.function_call_id == id_int).all()
            for snapshot in snapshots:
                self.session.delete(snapshot)
            
            # Delete the function call itself
            self.session.delete(call)
            
            # Commit the changes
            self.session.commit()
            return True
            
        except Exception as e:
            print(f"Error deleting function call {call_id}: {e}")
            self.session.rollback()
            return False


def delete_function_execution(function_execution_id: str, db_path: str) -> bool:
    """
    Delete a function execution and its associated stack trace from the database.
    
    This function removes all data related to a specific function execution, including:
    - The function call record
    - All stack snapshots associated with the function call
    - Any references to stored objects (the objects themselves remain if used elsewhere)
    
    Args:
        function_execution_id: The ID of the function execution to delete
        db_path: Path to the database file containing the function execution data
        
    Returns:
        True if the function was successfully deleted, False otherwise
        
    Example:
        ```python
        from monitoringpy.core.function_call import delete_function_execution
        
        # Delete a function execution
        success = delete_function_execution("123", "monitoring.db")
        if success:
            print("Function execution deleted successfully")
        else:
            print("Failed to delete function execution")
        ```
    """
    from .models import init_db
    
    # Initialize database connection
    Session = init_db(db_path)
    session = Session()
    
    try:
        tracker = FunctionCallTracker(session)
        result = tracker.delete_call(function_execution_id)
        return result
    finally:
        # Close the session
        session.close() 