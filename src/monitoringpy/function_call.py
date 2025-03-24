from typing import Dict, Any, Optional, TypedDict, List, Union
from sqlalchemy.orm import Session
import datetime
import inspect
from .representation import ObjectManager
from .models import StoredObject, FunctionCall, StackSnapshot

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

class FunctionCallTracker:
    """Track function calls and their context using object manager for efficient storage"""
    
    def __init__(self, session: Session) -> None:
        self.session = session
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

    def capture_call(self, func_name: str, locals_dict: Dict[str, Any], globals_dict: Dict[str, Any]) -> str:
        """
        Capture a function call with its local and global context.
        Returns the function call ID.
        """
        # Get caller frame info
        frame = inspect.currentframe()
        if frame:
            frame = frame.f_back  # Get the caller's frame
        
        # Store local and global variables
        locals_refs = self._store_variables(locals_dict)
        globals_refs = self._store_variables(globals_dict)

        # Create function call record
        call = FunctionCall(
            function=func_name,
            file=frame.f_code.co_filename if frame else None,
            line=frame.f_lineno if frame else None,
            start_time=datetime.datetime.now(),
            locals_refs=locals_refs,
            globals_refs=globals_refs
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
        Raises ValueError if call_id doesn't exist.
        """
        call = self.session.query(FunctionCall).filter(FunctionCall.id == int(call_id)).first()
        if not call:
            raise ValueError(f"Function call {call_id} not found")

        # Resolve local variables - store references, not values
        locals_dict = {}
        for name, ref in call.locals_refs.items():
            # Store the reference, not the resolved value
            locals_dict[name] = ref

        # Resolve global variables - store references, not values
        globals_dict = {}
        for name, ref in call.globals_refs.items():
            # Store the reference, not the resolved value
            globals_dict[name] = ref

        # Store return value reference, not the resolved value
        return_value = call.return_ref

        # Get energy data from call_metadata if available
        energy_data = call.call_metadata.get('energy_data') if call.call_metadata else None

        return FunctionCallInfo(
            function=call.function,
            file=call.file,
            line=call.line,
            start_time=call.start_time,
            end_time=call.end_time,
            locals=locals_dict,
            globals=globals_dict,
            return_value=return_value,
            energy_data=energy_data
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
            
            # Create new snapshot
            snapshot = StackSnapshot(
                function_call_id=int(call_id),
                line_number=line_number,
                locals_refs=locals_dict,
                globals_refs=globals_dict
            )
            
            self.session.add(snapshot)
            self.session.flush()  # This will assign an ID to the snapshot
            
            # Check if this is the first snapshot for this call
            if call.first_snapshot_id is None:
                # This is the first snapshot
                call.first_snapshot_id = snapshot.id
            else:
                # Get the last snapshot and link them
                last_snapshot = (self.session.query(StackSnapshot)
                               .filter(StackSnapshot.function_call_id == int(call_id))
                               .filter(StackSnapshot.next_snapshot_id.is_(None))
                               .first())
                if last_snapshot:
                    last_snapshot.next_snapshot_id = snapshot.id
                    snapshot.previous_snapshot_id = last_snapshot.id
            
            self.session.commit()
            return snapshot
            
        except Exception as e:
            self.session.rollback()
            raise ValueError(f"Failed to create stack snapshot: {e}") 