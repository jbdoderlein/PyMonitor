"""
Setup script for PyMonitor package.

This setup.py works alongside pyproject.toml to handle custom installation
tasks like downloading external dependencies.
"""

import os
import sys
import subprocess
from pathlib import Path
from setuptools import setup
from setuptools.command.develop import develop
from setuptools.command.install import install


class PostInstallCommand(install):
    """Custom installation command that downloads GumTree after installation."""
    
    def run(self):
        # Run the normal installation
        install.run(self)
        
        # Run post-install tasks
        self.execute_post_install()
        
    def execute_post_install(self):
        """Execute post-installation tasks."""
        print("PyMonitor: Running post-installation tasks...")
        
        # Find the package installation directory
        package_dir = None
        for path in sys.path:
            potential_dir = Path(path) / "monitoringpy"
            if potential_dir.exists():
                package_dir = potential_dir
                break
        
        if not package_dir:
            print("PyMonitor: Could not find installation directory, skipping GumTree download")
            return
            
        # Path to the download script
        download_script = package_dir / "codediff" / "download_gumtree.py"
        
        if not download_script.exists():
            print(f"PyMonitor: GumTree download script not found at {download_script}")
            return
            
        # Path to the GumTree installation directory
        gumtree_dir = package_dir / "codediff" / "gumtree"
        
        # Check if GumTree is already installed
        gumtree_executable = gumtree_dir / "bin" / "gumtree"
        if sys.platform == "win32":
            gumtree_executable = gumtree_dir / "bin" / "gumtree.bat"
            
        if gumtree_executable.exists():
            print("PyMonitor: GumTree already installed")
            return
            
        print("PyMonitor: Downloading GumTree...")
        
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
            else:
                print(f"PyMonitor: GumTree download failed, but installation continues")
                print("PyMonitor: GumTree will be downloaded on first use")
                
        except subprocess.TimeoutExpired:
            print("PyMonitor: GumTree download timed out")
            print("PyMonitor: GumTree will be downloaded on first use")
        except Exception as e:
            print(f"PyMonitor: Error downloading GumTree: {e}")
            print("PyMonitor: GumTree will be downloaded on first use")


class PostDevelopCommand(develop):
    """Custom development installation command."""
    
    def run(self):
        # Run the normal development installation
        develop.run(self)
        
        # Run post-install tasks
        self.execute_post_install()
        
    def execute_post_install(self):
        """Execute post-installation tasks for development install."""
        print("PyMonitor: Running post-installation tasks for development install...")
        
        # For development installs, the source directory structure is different
        # The script should be in the source directory
        script_dir = Path(__file__).parent
        download_script = script_dir / "src" / "monitoringpy" / "codediff" / "download_gumtree.py"
        
        if not download_script.exists():
            print(f"PyMonitor: GumTree download script not found at {download_script}")
            return
            
        # Path to the GumTree installation directory
        gumtree_dir = script_dir / "src" / "monitoringpy" / "codediff" / "gumtree"
        
        # Check if GumTree is already installed
        gumtree_executable = gumtree_dir / "bin" / "gumtree"
        if sys.platform == "win32":
            gumtree_executable = gumtree_dir / "bin" / "gumtree.bat"
            
        if gumtree_executable.exists():
            print("PyMonitor: GumTree already installed")
            return
            
        print("PyMonitor: Downloading GumTree...")
        
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
            else:
                print(f"PyMonitor: GumTree download failed, but installation continues")
                print("PyMonitor: GumTree will be downloaded on first use")
                
        except subprocess.TimeoutExpired:
            print("PyMonitor: GumTree download timed out")
            print("PyMonitor: GumTree will be downloaded on first use")
        except Exception as e:
            print(f"PyMonitor: Error downloading GumTree: {e}")
            print("PyMonitor: GumTree will be downloaded on first use")


# Setup configuration
if __name__ == "__main__":
    setup(
        cmdclass={
            'install': PostInstallCommand,
            'develop': PostDevelopCommand,
        },
    ) 