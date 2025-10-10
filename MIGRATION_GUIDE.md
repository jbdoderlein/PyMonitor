# Migration Guide: PyMonitor → SpaceTimePy

This document provides a comprehensive guide for migrating from PyMonitor/monitoringpy to SpaceTimePy/spacetimepy.

## Overview

The project has been renamed from **PyMonitor** to **SpaceTimePy** to better reflect its purpose and capabilities. This includes:
- Module name change: `monitoringpy` → `spacetimepy`
- Package name change: `pymonitor` → `spacetimepy`
- Main class rename: `PyMonitoring` → `SpaceTimeMonitor`
- New simplified decorator syntax

## Breaking Changes

### 1. Module Import

**Before:**
```python
import monitoringpy
```

**After:**
```python
import spacetimepy
```

### 2. Class Names

The main monitoring class has been renamed:

**Before:**
```python
from monitoringpy import PyMonitoring
monitor = PyMonitoring(db_path="my_data.db")
```

**After:**
```python
from spacetimepy import SpaceTimeMonitor
monitor = SpaceTimeMonitor(db_path="my_data.db")
```

**Note:** For backward compatibility, `PyMonitoring` is still available as an alias to `SpaceTimeMonitor`, but it's recommended to update to the new name.

### 3. Installation

**Before:**
```bash
pip install pymonitor
```

**After:**
```bash
pip install spacetimepy
```

## New Features

### Simplified Decorator Syntax

We've introduced new convenience decorators for a cleaner, more intuitive API:

#### Function-Level Monitoring

**Old Syntax:**
```python
@spacetimepy.pymonitor(mode="function")
def my_function(x, y):
    return x + y
```

**New Syntax:**
```python
@spacetimepy.function
def my_function(x, y):
    return x + y
```

#### Line-Level Monitoring

**Old Syntax:**
```python
@spacetimepy.pymonitor(mode="line")
def process_data(data):
    result = []
    for item in data:
        result.append(item * 2)
    return result
```

**New Syntax:**
```python
@spacetimepy.line
def process_data(data):
    result = []
    for item in data:
        result.append(item * 2)
    return result
```

#### With Options

Both decorators support all the same options as `pymonitor`:

**Old Syntax:**
```python
@spacetimepy.pymonitor(
    mode="function",
    ignore=["temp_data"],
    track=[helper_function],
    return_hooks=[custom_hook]
)
def complex_function(data):
    return helper_function(data)
```

**New Syntax:**
```python
@spacetimepy.function(
    ignore=["temp_data"],
    track=[helper_function],
    return_hooks=[custom_hook]
)
def complex_function(data):
    return helper_function(data)
```

**Note:** The old `@spacetimepy.pymonitor()` syntax is still supported for backward compatibility.

## Complete Migration Example

### Before (PyMonitor/monitoringpy)

```python
import monitoringpy

# Initialize monitoring
monitor = monitoringpy.init_monitoring(db_path="game.db")

# Start session
monitoringpy.start_session("Game Session")

# Function-level monitoring
@monitoringpy.pymonitor(mode="function")
def calculate_score(points, multiplier):
    return points * multiplier

# Line-level monitoring
@monitoringpy.pymonitor(mode="line")
def move_player(player, direction):
    if direction == "up":
        player.y -= 1
    elif direction == "down":
        player.y += 1
    return player

# Run your code
score = calculate_score(100, 2)
player = move_player(player, "up")

# End session
monitoringpy.end_session()
```

### After (SpaceTimePy/spacetimepy)

```python
import spacetimepy

# Initialize monitoring
monitor = spacetimepy.init_monitoring(db_path="game.db")

# Start session
spacetimepy.start_session("Game Session")

# Function-level monitoring (new syntax!)
@spacetimepy.function
def calculate_score(points, multiplier):
    return points * multiplier

# Line-level monitoring (new syntax!)
@spacetimepy.line
def move_player(player, direction):
    if direction == "up":
        player.y -= 1
    elif direction == "down":
        player.y += 1
    return player

# Run your code
score = calculate_score(100, 2)
player = move_player(player, "up")

# End session
spacetimepy.end_session()
```

## API Reference Changes

### Core Functions (No Breaking Changes)

These functions work the same way, just with the new module name:

- `spacetimepy.init_monitoring()` - Initialize the monitoring system
- `spacetimepy.start_session()` - Start a monitoring session
- `spacetimepy.end_session()` - End a monitoring session
- `spacetimepy.session_context()` - Context manager for sessions
- `spacetimepy.disable_recording()` - Temporarily disable recording
- `spacetimepy.enable_recording()` - Re-enable recording
- `spacetimepy.recording_context()` - Context manager for recording control

### Reanimation Functions (No Breaking Changes)

- `spacetimepy.load_execution_data()` - Load execution data
- `spacetimepy.reanimate_function()` - Re-execute a function with stored state
- `spacetimepy.run_with_state()` - Run with specific state
- `spacetimepy.load_snapshot()` - Load a state snapshot
- `spacetimepy.replay_session_from()` - Replay from a session point

### Web Interface (No Breaking Changes)

```python
from spacetimepy.interface import WebExplorer, start_web_explorer

# Start web interface
start_web_explorer('my_session.db', host='127.0.0.1', port=5000)

# Or use the API
from spacetimepy.interface import run_api
run_api('my_session.db', port=8000)
```

### CLI Tools

**Before:**
```bash
web-pymonitor my_session.db
```

**After:**
```bash
web-spacetimepy my_session.db
```

## Backward Compatibility

To ease migration, the following are maintained for backward compatibility:

1. **Class alias:** `PyMonitoring` still works as an alias to `SpaceTimeMonitor`
2. **Old decorator syntax:** `@spacetimepy.pymonitor(mode="function")` still works
3. **All API functions:** All existing functions maintain the same signatures

However, we recommend updating to the new syntax for better clarity and future-proofing your code.

## Migration Checklist

- [ ] Update imports: `monitoringpy` → `spacetimepy`
- [ ] Update class references: `PyMonitoring` → `SpaceTimeMonitor` (optional but recommended)
- [ ] Update decorators to new syntax: `@pymonitor(mode="function")` → `@function` (optional but recommended)
- [ ] Update installation: `pip install spacetimepy`
- [ ] Update CLI commands: `web-pymonitor` → `web-spacetimepy`
- [ ] Test your code to ensure everything works correctly

## Need Help?

If you encounter any issues during migration:

1. Check that all imports are updated
2. Verify the package is installed correctly: `pip show spacetimepy`
3. Review this guide for any missed changes
4. Check the examples in the `examples/` directory for reference implementations

## Summary of Changes

| Component | Old (PyMonitor) | New (SpaceTimePy) |
|-----------|----------------|-------------------|
| Module name | `monitoringpy` | `spacetimepy` |
| Package name | `pymonitor` | `spacetimepy` |
| Main class | `PyMonitoring` | `SpaceTimeMonitor` |
| Function decorator | `@pymonitor(mode="function")` | `@function` |
| Line decorator | `@pymonitor(mode="line")` | `@line` |
| CLI tool | `web-pymonitor` | `web-spacetimepy` |
| Installation | `pip install pymonitor` | `pip install spacetimepy` |

All other APIs remain unchanged.
