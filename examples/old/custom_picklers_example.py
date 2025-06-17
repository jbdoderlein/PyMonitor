"""
Example demonstrating the use of custom picklers with PyMonitor.

This example shows how to use PyMonitor with custom picklers for Pygame objects.
"""

import pygame
import time
import random
from monitoringpy.core import init_monitoring, pymonitor

# Initialize Pygame
pygame.init()

# Initialize monitoring with custom picklers for pygame
monitor = init_monitoring(
    db_path="pygame_example.db",
    custom_picklers=['pygame']
)

@pymonitor
def create_rect(x, y, width, height, color):
    """Create a pygame Rect with the given dimensions and color."""
    rect = pygame.Rect(x, y, width, height)
    return rect, color

@pymonitor
def draw_rect(surface, rect, color):
    """Draw a rectangle on the surface."""
    pygame.draw.rect(surface, color, rect)
    return surface

@pymonitor
def game_loop():
    """Main game loop."""
    # Create a window
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("PyMonitor Pygame Example")
    
    # Create background
    background = pygame.Surface(screen.get_size())
    background.fill((0, 0, 0))
    
    # Create some rectangles
    rects = []
    for i in range(5):
        x = random.randint(0, 700)
        y = random.randint(0, 500)
        width = random.randint(50, 150)
        height = random.randint(50, 150)
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        rect, color = create_rect(x, y, width, height, color)
        rects.append((rect, color))
    
    # Game loop
    running = True
    clock = pygame.time.Clock()
    frame_count = 0
    
    while running and frame_count < 100:  # Limit to 100 frames for the example
        # Process events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        # Clear screen
        screen.blit(background, (0, 0))
        
        # Draw rectangles
        for rect, color in rects:
            screen = draw_rect(screen, rect, color)
            
            # Move rectangles
            rect.x += random.randint(-5, 5)
            rect.y += random.randint(-5, 5)
            
            # Keep within bounds
            if rect.left < 0:
                rect.left = 0
            if rect.right > 800:
                rect.right = 800
            if rect.top < 0:
                rect.top = 0
            if rect.bottom > 600:
                rect.bottom = 600
        
        # Update display
        pygame.display.flip()
        
        # Control frame rate
        clock.tick(30)
        frame_count += 1
    
    # Clean up
    pygame.quit()
    return "Game loop completed"

if __name__ == "__main__":
    # Run the game
    result = game_loop()
    print(result)
    
    # Print information about the monitoring
    print("Monitoring data has been recorded")
    print("You can now view the monitoring data, including pickled Pygame objects")
    print("The examples include objects like pygame.Rect, pygame.Surface, and pygame.Color")
    
    # Generate a report
    print("\nTo view the monitoring results, run:")
    print("from monitoringpy.interface.web import app")
    print("app.run()") 