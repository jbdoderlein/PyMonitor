"""
GumTree utility functions for PyMonitor.

This module provides utility functions for managing the GumTree executable,
including automatic download when needed.
"""

import platform
import subprocess
import sys
from pathlib import Path


def get_gumtree_path() -> str | None:
    """
    Get the path to the GumTree executable.
    
    Returns:
        str: Path to the GumTree executable, or None if not found and download failed.
    """
    # Path to the GumTree installation directory
    gumtree_dir = Path(__file__).parent / "gumtree"

    # Determine the executable name based on platform
    if platform.system() == "Windows":
        executable_name = "gumtree.bat"
    else:
        executable_name = "gumtree"

    gumtree_executable = gumtree_dir / "bin" / executable_name

    # Check if GumTree is already installed
    if gumtree_executable.exists():
        return str(gumtree_executable)

    # Try to download GumTree
    print("PyMonitor: GumTree not found, attempting to download...")

    if _download_gumtree():
        if gumtree_executable.exists():
            return str(gumtree_executable)

    print("PyMonitor: Failed to download GumTree. Code diff functionality will not be available.")
    return None


def _download_gumtree() -> bool:
    """
    Download GumTree executable.
    
    Returns:
        bool: True if download was successful, False otherwise.
    """
    # Path to the download script
    download_script = Path(__file__).parent / "download_gumtree.py"

    if not download_script.exists():
        print(f"PyMonitor: GumTree download script not found at {download_script}")
        return False

    # Path to the GumTree installation directory
    gumtree_dir = Path(__file__).parent / "gumtree"

    try:
        # Run the download script
        result = subprocess.run(
            [sys.executable, str(download_script), "--install-dir", str(gumtree_dir)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )

        if result.returncode == 0:
            print("PyMonitor: GumTree download completed successfully")
            return True
        print(f"PyMonitor: GumTree download failed with return code {result.returncode}")
        if result.stderr:
            print(f"Error: {result.stderr}")
        return False

    except subprocess.TimeoutExpired:
        print("PyMonitor: GumTree download timed out")
        return False
    except Exception as e:
        print(f"PyMonitor: Error downloading GumTree: {e}")
        return False


def check_gumtree_available() -> bool:
    """
    Check if GumTree is available for use.
    
    Returns:
        bool: True if GumTree is available, False otherwise.
    """
    gumtree_path = get_gumtree_path()
    return gumtree_path is not None


def ensure_gumtree_available() -> str:
    """
    Ensure GumTree is available and return its path.
    
    Returns:
        str: Path to the GumTree executable.
        
    Raises:
        RuntimeError: If GumTree cannot be found or downloaded.
    """
    gumtree_path = get_gumtree_path()

    if gumtree_path is None:
        raise RuntimeError(
            "GumTree executable not found and could not be downloaded. "
            "Please install GumTree manually or check your internet connection."
        )

    return gumtree_path
