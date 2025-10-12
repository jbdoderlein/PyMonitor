import ctypes
import inspect
import sys

import bytecode
import pydevd
from bytecode.instr import Instr

from spacetimepy.codediff.graph_generator import generate_line_mapping_from_string


def change_f_back(f_up, f_down):
    """Change the f_back of a frame (f_up) to a different frame (f_down)"""

    class PyFrameObject(ctypes.Structure):
        _fields_ = [("ob_refcnt", ctypes.c_ssize_t),
                    ("ob_type", ctypes.c_void_p),
                    ("f_back", ctypes.py_object)]

    raw_c_frame = ctypes.cast(id(f_up), ctypes.POINTER(PyFrameObject))
    raw_c_frame.contents.f_back = f_down  # now c() thinks it was called directly by a()
    # Confirm
    assert f_up.f_back is f_down

def hotline(f_to_patch):
    """
    This function patch a function to enable hotswap to line level
    How to use :
    - add decorator @hotline to the function you want to patch
    - when in the debugger and want to update current function frame code :
        - call _ahs_reload()
        - continue execution
        - call _ahs_correct_jump()

    Assumptions :
    - the function is not recursive
    - there is a breakpoint on the first line of the function

    Side effect :
    - debugger set line function set all unitialised variable to None, maybe fixable
    - variable/function with _ahs_ prefix are used internally by the hotline system (visible in globals)
    """
    def _ahs_reload(line_number=None):
        # get the current line of the frame
        stack = inspect.stack()
        frame_index = 0
        while stack[frame_index].function != f_to_patch.__name__:
            frame_index += 1
        _info = stack[frame_index]
        _ahs_line = _info.lineno
        # get the line to jump
        if line_number is not None:
            f_to_patch._ahs_deroute = line_number
        else:
            f_to_patch._ahs_deroute = f_to_patch._ahs_get_line_to_jump(_ahs_line)
        # Optionnal : make the goto here
        t = pydevd.threadingCurrentThread()
        if t is not None:
            info = t.additional_info # type: ignore
            info.pydev_original_step_cmd = pydevd.CMD_SET_NEXT_STATEMENT
            info.pydev_step_cmd = pydevd.CMD_SET_NEXT_STATEMENT
            info.pydev_step_stop = None
            info.pydev_next_line = int(f_to_patch._ahs_first_line)
            info.pydev_func_name = f_to_patch.__name__
            info.pydev_message = str(f_to_patch._ahs_first_line)
            info.pydev_smart_parent_offset = -1
            info.pydev_smart_child_offset = -1
            info.pydev_state = pydevd.STATE_RUN
            info.update_stepping_info()

    def _ahs_get_line_to_jump(before_line):
        # get the source code of the function
        old_source_code = f_to_patch._ahs_current_frame_source_code
        new_source_code = inspect.getsource(f_to_patch)
        f_to_patch._ahs_current_frame_source_code = new_source_code
        old_to_new,_,changed = generate_line_mapping_from_string(old_source_code, new_source_code)
        first_line = f_to_patch.__code__.co_firstlineno

        return old_to_new[before_line-first_line+1]+first_line-1


    def _ahs_correct_jump():
        stack = inspect.stack()
        frame_index = 0
        while stack[frame_index].function != f_to_patch.__name__:
            frame_index += 1
        frame = stack[frame_index].frame
        # Load locals
        for k,v in f_to_patch._ahs_last_frame_locals.items():
            frame.f_locals[k] = v
        # Load f_back
        change_f_back(frame, f_to_patch._ahs_last_frame_fback)
        # step to the correct line
        t = pydevd.threadingCurrentThread()
        info = t.additional_info
        info.pydev_original_step_cmd = pydevd.CMD_SET_NEXT_STATEMENT
        info.pydev_step_cmd = pydevd.CMD_SET_NEXT_STATEMENT
        info.pydev_step_stop = None
        info.pydev_next_line = int(f_to_patch._ahs_line_to_jump)
        info.pydev_func_name = f_to_patch.__name__
        info.pydev_message = str(f_to_patch._ahs_line_to_jump)
        info.pydev_smart_parent_offset = -1
        info.pydev_smart_child_offset = -1
        info.pydev_state = pydevd.STATE_RUN
        info.update_stepping_info()

    def _ahs_injected_part():
        import importlib
        import inspect
        nonlocal f_to_patch
        _ahs_frame = inspect.stack()[1]
        _ahs_function = getattr(inspect.getmodule(_ahs_frame.frame), _ahs_frame.function)
        if hasattr(_ahs_function, "_ahs_deroute"):  # The user want to reload code. Branch triggered by _ash_reload
            # Reload the module and function from source
            line_to_jump = _ahs_function._ahs_deroute # we save here because we loose it on reload
            ahs_call_arguments : inspect.ArgInfo | None = getattr(_ahs_function, "_ahs_call_arguments", None)
            # For spacetimepy compability
            event_before = sys.monitoring.get_local_events(sys.monitoring.PROFILER_ID,_ahs_function.__code__)
            _ahs_function = getattr(importlib.reload(inspect.getmodule(_ahs_frame.frame)), _ahs_frame.function) # type: ignore
            f_to_patch = _ahs_function
            if event_before != 0:
                sys.monitoring.set_local_events(sys.monitoring.PROFILER_ID,_ahs_function.__code__,event_before)
            # From the reload version, patch bytecode for correct jump and locals
            for n in ["__pydevd_ret_val_dict"]:
                if n in _ahs_frame.frame.f_locals:
                    del _ahs_frame.frame.f_locals[n]
            _ahs_function._ahs_last_frame_locals = _ahs_frame.frame.f_locals
            _ahs_function._ahs_line_to_jump = line_to_jump
            _ahs_function._ahs_last_frame_fback = _ahs_frame.frame.f_back
            fargs = {}
            if ahs_call_arguments:
                args, varargs, varkw, locals_ = ahs_call_arguments
                for a in args:
                    if a in locals_:
                        fargs[a] = locals_[a]
                if varargs is not None and varargs in locals_:
                    fargs[varargs] = locals_[varargs]
                if varkw is not None and varkw in locals_:
                    fargs[varkw] = locals_[varkw]
            _ahs_function(**fargs)  # re-call the function to create a new frame
        else:  # Normal function call, capture locals and f_back for future use
            _ahs_function._ahs_call_arguments = inspect.getargvalues(_ahs_frame.frame)


    # == Bytecode Injection ==
    bt = bytecode.Bytecode.from_code(f_to_patch.__code__)
    # find first line after resume
    for i, instr in enumerate(bt):
        if instr.name == "RESUME":
            resume_idx = i
            break
    assert resume_idx is not None, "No resume found in bytecode"
    first_line_after_resume = bt[resume_idx+1].lineno

    to_insert = [
        Instr("LOAD_GLOBAL", (True, "_ahs_injected_part"), lineno=first_line_after_resume),
        Instr("CALL", 0, lineno=first_line_after_resume),
        Instr("POP_TOP", lineno=first_line_after_resume)
    ]
    for instr in to_insert[::-1]:
        bt.insert(resume_idx+1, instr)

    f_to_patch._ahs_first_line = first_line_after_resume
    f_to_patch.__code__ = bt.to_code()

    f_to_patch.__globals__["_ahs_injected_part"] = _ahs_injected_part
    f_to_patch.__globals__["_ahs_reload"] = _ahs_reload # here we use global since it must be callable without any reference to self
    f_to_patch.__globals__["_ahs_correct_jump"] = _ahs_correct_jump
    f_to_patch._ahs_get_line_to_jump = _ahs_get_line_to_jump

    # Get source code of the function
    source_code = inspect.getsource(f_to_patch)
    f_to_patch._ahs_current_frame_source_code = source_code
    return f_to_patch
