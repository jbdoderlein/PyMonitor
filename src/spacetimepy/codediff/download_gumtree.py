#!/usr/bin/env python3
"""
Download GumTree executable from GitHub releases.

This script downloads the GumTree tree-differencing tool from GitHub
and installs it in the appropriate location for the spacetimepy package.
"""

import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# GumTree GitHub repository information
GUMTREE_REPO = "GumTreeDiff/gumtree"
GUMTREE_VERSION = "4.0.0-beta4"  # Latest version

def get_download_url(version=GUMTREE_VERSION):
    """Get the download URL for GumTree."""
    # GumTree release URL pattern - single zip file for all platforms
    base_url = f"https://github.com/{GUMTREE_REPO}/releases/download"
    filename = f"gumtree-{version}.zip"

    return f"{base_url}/v{version}/{filename}"

def download_file(url, dest_path):
    """Download a file from URL to destination path."""
    print(f"Downloading from: {url}")
    print(f"Destination: {dest_path}")

    try:
        # Create a request with User-Agent to avoid GitHub blocking
        request = Request(url, headers={'User-Agent': 'PyMonitor-Installation'})

        with urlopen(request) as response:
            if response.status != 200:
                raise URLError(f"HTTP {response.status}: {response.reason}")

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(dest_path, 'wb') as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        progress = (downloaded / total_size) * 100
                        print(f"\rProgress: {progress:.1f}%", end='', flush=True)

        print(f"\nDownload completed: {dest_path}")
        return True

    except URLError as e:
        print(f"Error downloading file: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

def extract_archive(archive_path, dest_dir):
    """Extract archive to destination directory."""
    print(f"Extracting {archive_path} to {dest_dir}")

    try:
        # Convert Path object to string for endswith check
        archive_str = str(archive_path)

        if archive_str.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(dest_dir)
        elif archive_str.endswith('.tar.gz') or archive_str.endswith('.tgz'):
            with tarfile.open(archive_path, 'r:gz') as tar_ref:
                tar_ref.extractall(dest_dir)
        else:
            raise ValueError(f"Unsupported archive format: {archive_path}")

        print("Extraction completed")
        return True

    except Exception as e:
        print(f"Error extracting archive: {e}")
        return False

def make_executable(file_path):
    """Make a file executable on Unix-like systems."""
    if os.name != 'nt':  # Not Windows
        try:
            current_mode = os.stat(file_path).st_mode
            os.chmod(file_path, current_mode | stat.S_IEXEC)
            print(f"Made executable: {file_path}")
        except Exception as e:
            print(f"Warning: Could not make executable: {e}")

def install_gumtree(install_dir=None):
    """Download and install GumTree executable."""
    if install_dir is None:
        # Default to the gumtree directory relative to this script
        script_dir = Path(__file__).parent
        install_dir = script_dir / "gumtree"
    else:
        install_dir = Path(install_dir)

    # Create installation directory if it doesn't exist
    install_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = install_dir / "bin"
    lib_dir = install_dir / "lib"
    bin_dir.mkdir(exist_ok=True)
    lib_dir.mkdir(exist_ok=True)

    # Check if GumTree is already installed
    gumtree_executable = bin_dir / "gumtree"
    if platform.system() == "Windows":
        gumtree_executable = bin_dir / "gumtree.bat"

    if gumtree_executable.exists():
        print(f"GumTree already installed at: {gumtree_executable}")
        return True

    print("Installing GumTree...")

    # Get download URL
    try:
        download_url = get_download_url()
    except Exception as e:
        print(f"Error determining download URL: {e}")
        return False

    # Create temporary directory for download
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Download the archive
        archive_name = f"gumtree-{GUMTREE_VERSION}.zip"
        archive_path = temp_path / archive_name

        if not download_file(download_url, archive_path):
            print("Failed to download GumTree")
            return False

        # Extract the archive
        extract_dir = temp_path / "extracted"
        extract_dir.mkdir()

        if not extract_archive(archive_path, extract_dir):
            print("Failed to extract GumTree")
            return False

        # Find the GumTree files in the extracted directory
        # The structure might vary, so we need to find the actual files
        extracted_items = list(extract_dir.iterdir())

        if not extracted_items:
            print("No files found in extracted archive")
            return False

        # Look for the main directory (usually named like gumtree-x.x.x)
        main_dir = None
        for item in extracted_items:
            if item.is_dir() and "gumtree" in item.name.lower():
                main_dir = item
                break

        if main_dir is None:
            # If no gumtree directory found, use the first directory
            main_dir = extracted_items[0] if extracted_items[0].is_dir() else extract_dir

        # Copy files to installation directory
        try:
            # Copy bin directory
            src_bin = main_dir / "bin"
            if src_bin.exists():
                shutil.copytree(src_bin, bin_dir, dirs_exist_ok=True)
                print(f"Copied bin directory to {bin_dir}")

            # Copy lib directory
            src_lib = main_dir / "lib"
            if src_lib.exists():
                shutil.copytree(src_lib, lib_dir, dirs_exist_ok=True)
                print(f"Copied lib directory to {lib_dir}")

            # Make the main executable file executable
            for executable_name in ["gumtree", "gumtree.bat"]:
                executable_path = bin_dir / executable_name
                if executable_path.exists():
                    make_executable(executable_path)
                    print(f"GumTree installed successfully at: {executable_path}")
                    return True

            print("Warning: GumTree executable not found in expected location")
            return False

        except Exception as e:
            print(f"Error installing GumTree files: {e}")
            return False

def main():
    """Main entry point for the download script."""
    import argparse

    parser = argparse.ArgumentParser(description="Download and install GumTree")
    parser.add_argument("--install-dir", help="Installation directory")
    parser.add_argument("--version", default=GUMTREE_VERSION, help="GumTree version to download")
    parser.add_argument("--force", action="store_true", help="Force reinstallation")

    args = parser.parse_args()


    # Remove existing installation if force is specified
    if args.force and args.install_dir:
        install_path = Path(args.install_dir)
        if install_path.exists():
            print(f"Removing existing installation at {install_path}")
            shutil.rmtree(install_path)

    # Install GumTree
    success = install_gumtree(args.install_dir)

    if success:
        print("GumTree installation completed successfully!")
        sys.exit(0)
    else:
        print("GumTree installation failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
