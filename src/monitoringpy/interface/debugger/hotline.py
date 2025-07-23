import inspect

import bytecode
import pydevd
from bytecode.instr import Instr


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
    def _ahs_reload():
        # get the current line of the frame
        stack = inspect.stack()
        frame_index = 0
        while stack[frame_index].function != f_to_patch.__name__:
            frame_index += 1
        _info = stack[frame_index]
        _ahs_line = _info.lineno
        # get the line to jump
        f_to_patch._ahs_deroute = f_to_patch._ahs_get_line_to_jump(_ahs_line)
        # Optionnal : make the goto here
        t = pydevd.threadingCurrentThread()
        if t is not None:
            info = t.additional_info
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
        # get the line to jump
        line_to_jump = before_line # TODO : implement the algorithm
        return line_to_jump

    def _ahs_correct_jump():
        stack = inspect.stack()
        frame_index = 0
        while stack[frame_index].function != f_to_patch.__name__:
            frame_index += 1
        frame = stack[frame_index].frame
        for k,v in f_to_patch._ahs_last_frame_locals.items():
            frame.f_locals[k] = v
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
        _ahs_frame = inspect.stack()[1]
        _ahs_function = getattr(inspect.getmodule(_ahs_frame.frame), _ahs_frame.function)
        if hasattr(_ahs_function, "_ahs_deroute"):  # The user want to reload code. Branch triggered by _ash_reload
            # Reload the module and function from source
            line_to_jump = _ahs_function._ahs_deroute # we save here because we loose it on reload
            _ahs_function = getattr(importlib.reload(inspect.getmodule(_ahs_frame.frame)), _ahs_frame.function)
            # From the reload version, patch bytecode for correct jump and locals
            _ahs_function._ahs_last_frame_locals = _ahs_frame.frame.f_locals
            _ahs_function._ahs_line_to_jump = line_to_jump
            return _ahs_function() # TODO : propagate the return value
        return
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
