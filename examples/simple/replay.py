#!/usr/bin/env python3
"""
Demonstration of PyMonitor session replay capabilities.

This script demonstrates:
1. Replaying foo1 with the same context
2. Replaying foo1 while ignoring imbricated_list to show data persistence
3. Replaying complex function sequences with and without mocking get_event
4. Replaying from the middle of a complex function sequence
"""

import sys
import monitoringpy
from monitoringpy.core.reanimation import execute_function_call, replay_session_sequence

def demonstrate_replay_capabilities():
    """Demonstrate various replay capabilities."""
    
    print("=" * 60)
    print("PyMonitor Session Replay Demonstration")
    print("=" * 60)
    
    # Initialize monitoring for new session
    monitor = monitoringpy.init_monitoring(db_path="main.db")
    
    # Get some function call IDs from the database to replay
    # We'll query the database to find the calls we want to replay
    with monitoringpy.core.reanimation.get_db_session("main.db") as session:
        from monitoringpy.core.models import FunctionCall, MonitoringSession
        
        # Find the main session
        main_session = session.query(MonitoringSession).filter_by(name="main").first()
        if not main_session:
            print("❌ No 'main' session found. Please run main.py first!")
            return
        
        print(f"📊 Found session: {main_session.name} (ID: {main_session.id})")
        
        # Get foo1 call
        foo1_call = session.query(FunctionCall).filter(
            FunctionCall.session_id == main_session.id,
            FunctionCall.function == "foo1"
        ).first()
        
        # Get complex_function calls
        complex_calls = session.query(FunctionCall).filter(
            FunctionCall.session_id == main_session.id,
            FunctionCall.function == "complex_function"
        ).all()
        
        if not foo1_call:
            print("❌ No foo1 call found in main session!")
            return
        
        if not complex_calls:
            print("❌ No complex_function calls found in main session!")
            return
        
        print(f"🔍 Found foo1 call (ID: {foo1_call.id})")
        print(f"🔍 Found {len(complex_calls)} complex_function calls")
    
    # Start a new session for replay demonstrations
    replay_session_id = monitor.start_session(
        name="replay_demo", 
        description="Demonstration of replay capabilities"
    )
    print(f"\n🚀 Started replay session (ID: {replay_session_id})")

    # ========================================
    # 1. Replay foo1 with the same context
    # ========================================
    print("\n" + "=" * 40)
    print("1. Replaying foo1 with same context")
    print("=" * 40)
    
    try:
        result1 = execute_function_call(
            str(foo1_call.id), 
            "main.db", 
            enable_monitoring=True
        )
        assert result1 == 346
        print(f"✅ foo1 replay result: {result1}")
    except Exception as e:
        print(f"❌ Error replaying foo1: {e}")
        import traceback
        traceback.print_exc()

    
    # ========================================
    # 2. Replay foo1 ignoring imbricated_list
    # ========================================
    print("\n" + "=" * 40)
    print("2. Replaying foo1 ignoring imbricated_list")
    print("=" * 40)
    
    try:

        result2 = execute_function_call(
            str(foo1_call.id), 
            "main.db", 
            ignore_globals=["imbricated_list"],
            enable_monitoring=True,
            reload_module=False
        )
        assert result2 == 347
        print(f"✅ foo1 replay (ignoring imbricated_list) result: {result2}")
        print("📝 Note: This shows data persistence - the function still works without the ignored variable")
    except Exception as e:
        print(f"❌ Error replaying foo1 with ignored globals: {e}")
        import traceback
        traceback.print_exc()

    # ========================================
    # 3. Replay complex function sequence WITHOUT mocking
    # ========================================
    print("\n" + "=" * 40)
    print("3. Replaying complex function sequence (no mocking)")
    print("=" * 40)
    
    try:
        # Get the first complex_function call to start the sequence
        first_complex_call = complex_calls[0]
        
        result3 = replay_session_sequence(
            first_complex_call.id,
            "main.db",
            enable_monitoring=True
        )
        print(f"✅ Complex sequence replay (no mocking) started with call ID: {result3}")
        print("📝 Note: get_event() will generate new random values")
    except Exception as e:
        print(f"❌ Error replaying complex sequence: {e}")
        import traceback
        traceback.print_exc()
    
    # ========================================
    # 4. Replay complex function sequence WITH mocking
    # ========================================
    print("\n" + "=" * 40)
    print("4. Replaying complex function with get_event mocking")
    print("=" * 40)
    
    try:
        # Replay a single complex function call with mocking
        result4 = execute_function_call(
            str(complex_calls[0].id),
            "main.db",
            mock_function=["get_event"],
            enable_monitoring=True
        )
        # get the last call in the session
        with monitoringpy.core.reanimation.get_db_session("main.db") as session:
            last_call = session.query(FunctionCall).filter_by(session_id=replay_session_id).order_by(FunctionCall.order_in_session.desc()).first()
            assert isinstance(last_call, FunctionCall) and last_call.call_metadata is not None
            assert "custom_return_metric" in last_call.call_metadata
            assert isinstance(complex_calls[0].call_metadata, dict)
            assert "custom_return_metric" in complex_calls[0].call_metadata
            assert last_call.call_metadata["custom_return_metric"] == complex_calls[0].call_metadata["custom_return_metric"]

        print(f"✅ Complex function replay (with mocking) result: {result4}")
        print("📝 Note: get_event() returns the original recorded values")
    except Exception as e:
        print(f"❌ Error replaying complex function with mocking: {e}")
        import traceback
        traceback.print_exc()
    
    # ========================================
    # 5. Explore and replay from middle of sequence
    # ========================================
    print("\n" + "=" * 40)
    print("5. Exploring and replaying from middle of sequence")
    print("=" * 40)
    
    try:
        # Show the complete sequence structure
        with monitoringpy.core.reanimation.get_db_session("main.db") as session:
            # Get all function calls in the session, ordered by execution
            all_calls = session.query(FunctionCall).filter(
                FunctionCall.session_id == main_session.id
            ).order_by(FunctionCall.order_in_session).all()
            
            print(f"\n🔍 Complete execution sequence ({len(all_calls)} calls):")
            print("-" * 50)
            
            complex_call_positions = []
            for i, call in enumerate(all_calls):
                status = ""
                if call.function == "complex_function":
                    complex_call_positions.append((i, call))
                    status = " ← COMPLEX FUNCTION"
                
                print(f"{i+1:2d}. {call.function} (ID: {call.id}, Order: {call.order_in_session}){status}")
            
            print(f"\n🎯 Found {len(complex_call_positions)} complex_function calls:")
            for i, (pos, call) in enumerate(complex_call_positions):
                print(f"   {i+1}. Position {pos+1} - complex_function (ID: {call.id})")
            
            # Choose middle call for replay
            if len(complex_call_positions) < 3:
                print(f"\n⚠️  Only {len(complex_call_positions)} complex calls found. Using the last one for middle replay.")
                middle_pos, middle_call = complex_call_positions[-1]
                middle_index = len(complex_call_positions) - 1
            else:
                middle_index = len(complex_call_positions) // 2
                middle_pos, middle_call = complex_call_positions[middle_index]
            
            print(f"\n🚀 Selected call #{middle_index + 1} for middle replay:")
            print(f"   - Position in sequence: {middle_pos + 1}")
            print(f"   - Function: {middle_call.function}")
            print(f"   - ID: {middle_call.id}")
            print(f"   - Order in session: {middle_call.order_in_session}")
            
            # Show what calls would be replayed in sequence
            remaining_calls = session.query(FunctionCall).filter(
                FunctionCall.session_id == main_session.id,
                FunctionCall.order_in_session >= middle_call.order_in_session
            ).order_by(FunctionCall.order_in_session).all()
            
            print(f"\n📋 Calls that would be replayed (starting from middle):")
            print("-" * 50)
            for i, call in enumerate(remaining_calls[:8]):  # Show first 8
                print(f"{i+1:2d}. {call.function} (ID: {call.id}, Order: {call.order_in_session})")
            
            if len(remaining_calls) > 8:
                print(f"    ... and {len(remaining_calls) - 8} more calls")
        
        # Replay from the middle
        print(f"\n🔄 Replaying sequence starting from middle call (ID: {middle_call.id})...")
        
        result5 = replay_session_sequence(
            middle_call.id,
            "main.db",
            enable_monitoring=True
        )
        print(f"✅ Middle sequence replay started with call ID: {result5}")
        print("📝 Note: This replays from the middle, not from the beginning")
        
    except Exception as e:
        print(f"❌ Error exploring/replaying from middle: {e}")
        import traceback
        traceback.print_exc()
    
    # ========================================
    # 6. Show session summary
    # ========================================
    print("\n" + "=" * 40)
    print("6. Replay Session Summary")
    print("=" * 40)
    
    # End the replay session
    monitor.end_session()
    
    # Show what was recorded in the replay session
    with monitoringpy.core.reanimation.get_db_session("main.db") as session:
        replay_session = session.query(MonitoringSession).filter_by(id=replay_session_id).first()
        if replay_session:
            replay_calls = session.query(FunctionCall).filter_by(session_id=replay_session_id).all()
            print(f"📊 Replay session recorded {len(replay_calls)} new function calls:")
            for call in replay_calls:
                print(f"   - {call.function} (ID: {call.id}, Parent: {call.parent_call_id})")
    
    print("\n" + "=" * 60)
    print("🎉 Replay demonstration completed!")
    print("💡 Check main.db to see both original and replayed executions")
    print("=" * 60)

if __name__ == "__main__":
    demonstrate_replay_capabilities()
