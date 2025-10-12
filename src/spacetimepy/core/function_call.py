import logging
import traceback
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .models import CodeDefinition, FunctionCall, StackSnapshot
from .representation import ObjectManager, PickleConfig

logger = logging.getLogger(__name__)


class FunctionCallRepository:
    """Repository for querying and managing function call data"""

    def __init__(self, session: Session, pickle_config: PickleConfig | None = None) -> None:
        self.session = session
        self.object_manager = ObjectManager(session, pickle_config=pickle_config)

    def get_call(self, call_id: str | int) -> FunctionCall | None:
        """
        Get a function call by ID.
        Returns the FunctionCall model instance or None if not found.
        """
        try:
            call_id_int = int(call_id) if isinstance(call_id, str) else call_id
            return self.session.get(FunctionCall, call_id_int)
        except (ValueError, TypeError):
            logger.error(f"Invalid call ID: {call_id}")
            return None

    def get_call_with_code(self, call_id: str | int) -> dict[str, Any] | None:
        """
        Get a function call with its code definition information.
        Returns a dictionary with call data and code info, or None if not found.
        """
        call = self.get_call(call_id)
        if not call:
            return None

        result = call.to_dict()

        # Get code information if available
        code = None
        if call.code_definition_id is not None:
            try:
                sql = text("SELECT * FROM code_definitions WHERE id = :id")
                result_row = self.session.execute(sql, {"id": call.code_definition_id})
                row = result_row.fetchone()
                if row:
                    code = {
                        'content': row.code_content,
                        'module_path': row.module_path,
                        'type': row.type,
                        'name': row.name,
                        'first_line_no': row.first_line_no
                    }
            except Exception as e:
                logger.error(f"Error retrieving code definition for {call.code_definition_id}: {e}")

        result["code"] = code
        return result

    def get_call_history(self, function_name: str | None = None) -> list[int]:
        """
        Get the history of function calls, optionally filtered by function name.
        Returns a list of call IDs.
        """
        query = self.session.query(FunctionCall)
        if function_name:
            query = query.filter(FunctionCall.function == function_name)
        calls = query.order_by(FunctionCall.start_time.asc()).all()
        return [call.id for call in calls]

    def get_functions_with_traces(self) -> list[dict[str, Any]]:
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
            # Use SQLAlchemy ORM to build the query
            query = self.session.query(
                FunctionCall.id,
                FunctionCall.function,
                func.count(StackSnapshot.id).label('trace_count'),
                FunctionCall.file,
                FunctionCall.line,
                func.min(FunctionCall.start_time).label('first_occurrence'),
                func.max(FunctionCall.start_time).label('last_occurrence')
            ).outerjoin(
                StackSnapshot, FunctionCall.id == StackSnapshot.function_call_id
            ).group_by(
                FunctionCall.function, FunctionCall.file, FunctionCall.line
            ).having(
                func.count(StackSnapshot.id) > 0
            ).order_by(
                FunctionCall.function
            )

            functions = []
            for row in query.all():
                functions.append({
                    "id": row.id,
                    "function": row.function,
                    "trace_count": row.trace_count,
                    "file": row.file,
                    "line": row.line,
                    "first_occurrence": row.first_occurrence,
                    "last_occurrence": row.last_occurrence
                })

            return functions
        except Exception as e:
            logger.error(f"Error getting functions with traces: {e}")
            return []

    def get_function_traces(self, function_id: str | int) -> list[dict[str, Any]]:
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
                    logger.error(f"Invalid function ID: {function_id}")
                    return []

            # Get the function call
            function_call = self.session.get(FunctionCall, function_id)
            if not function_call:
                logger.error(f"Function call {function_id} not found")
                return []

            # Get all stack snapshots for this function call
            snapshots = self.session.query(StackSnapshot).filter(
                StackSnapshot.function_call_id == function_id
            ).order_by(StackSnapshot.order_in_call.asc()).all()

            # Get code information if available
            code = None
            if function_call.code_definition_id is not None:
                try:
                    code_definition = self.session.query(CodeDefinition).filter(
                        CodeDefinition.id == function_call.code_definition_id
                    ).first()

                    if code_definition:
                        first_line_no = code_definition.first_line_no if code_definition.first_line_no is not None else function_call.line
                        code = {
                            'content': code_definition.code_content,
                            'module_path': code_definition.module_path,
                            'type': code_definition.type,
                            'name': code_definition.name,
                            'first_line_no': first_line_no
                        }
                except Exception as e:
                    logger.error(f"Error retrieving code definition: {e}")

            traces = []
            for snapshot in snapshots:
                # Convert datetime to string to avoid serialization issues
                start_time_str = function_call.start_time.isoformat() if function_call.start_time is not None else None
                end_time_str = function_call.end_time.isoformat() if function_call.end_time is not None else None

                # Get previous snapshot using model method
                prev_snapshot = snapshot.get_previous_snapshot(self.session)

                # Create trace data with proper handling of all attributes
                locals_refs_dict = snapshot.locals_refs or {}
                globals_refs_dict = snapshot.globals_refs or {}

                trace_data = {
                    "id": str(snapshot.id),
                    "function": function_call.function,
                    "file": function_call.file,
                    "line": snapshot.line_number,
                    "time": start_time_str,
                    "end_time": end_time_str,
                    "snapshot_id": str(snapshot.id),
                    "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp is not None else None,
                    "call_metadata": function_call.call_metadata,
                    "locals_refs": locals_refs_dict,
                    "globals_refs": globals_refs_dict,
                    "previous_snapshot_id": str(prev_snapshot.id) if prev_snapshot else None,
                    "next_snapshot_id": str(snapshot.next_snapshot_id) if snapshot.next_snapshot_id is not None else None,
                    "order_in_call": snapshot.order_in_call,
                    "is_first_in_call": snapshot.is_first_in_call,
                    "is_last_in_call": snapshot.is_last_in_call
                }

                # Add code information if available
                if code:
                    trace_data["code"] = code

                # Add code definition ID if available
                if function_call.code_definition_id is not None:
                    trace_data["code_definition_id"] = str(function_call.code_definition_id)

                traces.append(trace_data)

            return traces
        except Exception as e:
            logger.error(f"Error getting function traces: {e}")
            logger.error(traceback.format_exc())
            return []

    def update_metadata(self, call_id: str | int, metadata: dict) -> bool:
        """Update the metadata for a function call.

        Args:
            call_id: The ID of the function call to update
            metadata: Dictionary containing metadata to store

        Returns:
            True if successful, False otherwise
        """
        try:
            call = self.get_call(call_id)
            if call:
                # If there's existing metadata, merge it with the new data
                if call.call_metadata:
                    # Create a new dict to avoid modifying the original
                    updated_metadata = dict(call.call_metadata)
                    updated_metadata.update(metadata)
                    call.call_metadata = updated_metadata
                else:
                    call.call_metadata = metadata
                self.session.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating metadata for call {call_id}: {e}")
            self.session.rollback()
            return False

    def delete_call(self, call_id: str | int) -> bool:
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
                id_int = int(call_id) if isinstance(call_id, str) else call_id
            except ValueError:
                logger.error(f"Invalid function call ID: {call_id}")
                return False

            # Get the function call
            call = self.session.get(FunctionCall, id_int)
            if not call:
                logger.error(f"Function call {call_id} not found")
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
            logger.error(f"Error deleting function call {call_id}: {e}")
            self.session.rollback()
            return False
