from collections.abc import Callable


def do_jump(func_name: str, line: int):
    """
    Jump to a specific line in a function.
    """
    import importlib
    import inspect

    import pydevd  # type: ignore
    stack = inspect.stack()
    frame_index = 0
    while stack[frame_index].function != func_name:
        frame_index += 1
    _info = stack[frame_index]
    module = inspect.getmodule(_info.frame)
    if module is None:
        raise Exception("Module is None")
    importlib.reload(module)
    t = pydevd.threadingCurrentThread()
    if t is not None:
        info = t.additional_info
        info.pydev_original_step_cmd = pydevd.CMD_SET_NEXT_STATEMENT
        info.pydev_step_cmd = pydevd.CMD_SET_NEXT_STATEMENT
        info.pydev_step_stop = None
        info.pydev_next_line = int(line)
        info.pydev_func_name = _info.function
        info.pydev_message = str(line)
        info.pydev_smart_parent_offset = -1
        info.pydev_smart_child_offset = -1
        info.pydev_state = pydevd.STATE_RUN
        info.update_stepping_info()

def inject_do_jump(f: Callable):
    f.__globals__["_do_jump"] = do_jump
