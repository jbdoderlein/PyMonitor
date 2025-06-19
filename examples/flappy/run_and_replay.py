#!/usr/bin/env python3
"""
Run Flappy Bird and then launch the replay interface

This script runs the flappy bird game for a limited number of frames
to generate monitoring data, then launches the simple replay interface.
"""

import os
import sys
import subprocess

# Add the src directory to the path to import monitoringpy
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import pygame
import monitoringpy
from flappy import display_game

def run_flappy_limited():
    """Run flappy bird for a limited number of frames"""
    print("Running Flappy Bird for 100 frames to generate monitoring data...")
    
    # Initialize monitoring
    monitor = monitoringpy.init_monitoring(db_path="flappy.db", custom_picklers=["pygame"])
    monitoringpy.start_session("Flappy Bird Limited Run")
    
    while display_game():
        pass
        
    # End session and export
    monitoringpy.end_session()
    monitor.export_db()
    pygame.quit()
    

def launch_replay():
    """Launch the simple replay interface"""
    print("Launching replay interface...")
    
    # Check if database exists
    if not os.path.exists("flappy.db"):
        print("Error: flappy.db not found. Run the game first.")
        return
    
    # Launch the replay script
    script_path = os.path.join(os.path.dirname(__file__), "simple_replay.py")
    subprocess.run([sys.executable, script_path, "flappy.db"])

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Flappy Bird and launch replay")
    parser.add_argument("--skip-game", action="store_true", 
                       help="Skip running the game and go directly to replay")
    args = parser.parse_args()
    
    if not args.skip_game:
        run_flappy_limited()
    
    launch_replay()

if __name__ == "__main__":
    main() 