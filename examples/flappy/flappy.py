import sys
import random
import monitoringpy
from monitoringpy import pygame

# Initialize pygame
pygame.init()
random.seed(42)

# Screen dimensions
SCREEN_WIDTH = 500
SCREEN_HEIGHT = 700
SCREEN = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Flappy Bird")

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (0, 128, 0)
BLUE = (0, 0, 255)
RED = (255, 0, 0)
BG_COLOR = (135, 206, 235)  # Sky blue

# Game variables
GRAVITY = 0.35
BIRD_MOVEMENT = 0
PIPE_GAP = 200 
PIPE_WIDTH = 100
PIPE_SPEED = 3  # Reduced from 3 to slow down the game
PIPE_SPAWN_DISTANCE = 300  # Minimum horizontal distance between pipe pairs
GAME_ACTIVE = True
SCORE = 0
HIGH_SCORE = 0
FONT = pygame.font.SysFont("Arial", 30)

# Bird parameters
BIRD_SIZE = 40
bird_rect = pygame.Rect(SCREEN_WIDTH // 3, SCREEN_HEIGHT // 2, BIRD_SIZE, BIRD_SIZE)

# Pipe list
pipes = []
# List to track pipes the bird has passed
passed_pipes = []

# Clock object
clock = pygame.time.Clock()

def create_pipe():
    """Create a new pipe pair"""
    # Random position for the gap between top and bottom pipes
    gap_y_pos = random.randint(200, SCREEN_HEIGHT - 200)
    
    # Bottom pipe starts at the gap position and extends to the bottom of the screen
    bottom_pipe = pygame.Rect(SCREEN_WIDTH, gap_y_pos + PIPE_GAP//2, PIPE_WIDTH, SCREEN_HEIGHT - gap_y_pos - PIPE_GAP//2)
    
    # Top pipe starts at the top of the screen and extends to the gap position
    top_pipe = pygame.Rect(SCREEN_WIDTH, 0, PIPE_WIDTH, gap_y_pos - PIPE_GAP//2)
    
    return bottom_pipe, top_pipe

def move_pipes(pipes):
    """Move all pipes to the left and remove pipes/tracking that are off screen"""
    global passed_pipes
    new_pipes = []
    pipes_to_remove_from_tracking = []

    for pipe in pipes:
        pipe.x -= PIPE_SPEED
        if pipe.right < 0: # Check if pipe is completely off-screen to the left
            # Mark this pipe for removal from tracking if it's in passed_pipes
            if pipe in passed_pipes:
                 pipes_to_remove_from_tracking.append(pipe)
        else:
            new_pipes.append(pipe) # Keep pipes still on screen or moving off
    
    # Clean up passed_pipes list
    for p in pipes_to_remove_from_tracking:
        passed_pipes.remove(p)

    return new_pipes

def draw_pipes(pipes):
    """Draw all pipes"""
    for pipe in pipes:
        if pipe.y == 0:  # Top pipe
            pygame.draw.rect(SCREEN, GREEN, pipe)
        else:  # Bottom pipe
            pygame.draw.rect(SCREEN, GREEN, pipe)

def check_collision(pipes, bird_rect):
    """Check if bird collides with pipes or goes off screen"""
    if bird_rect.top <= 0 or bird_rect.bottom >= SCREEN_HEIGHT:
        return True
    
    for pipe in pipes:
        if bird_rect.colliderect(pipe):
            return True
    
    return False

def reset_game():
    """Reset game state"""
    global BIRD_MOVEMENT, GAME_ACTIVE, SCORE, pipes, passed_pipes
    bird_rect.y = SCREEN_HEIGHT // 2
    BIRD_MOVEMENT = 0
    pipes.clear()
    passed_pipes.clear() # Clear the passed pipes list
    GAME_ACTIVE = True
    SCORE = 0

def update_score(pipes, bird_rect):
    """Update score when bird passes through pipes"""
    global SCORE, passed_pipes
    for pipe in pipes:
        # Check only bottom pipes (pipe.y > 0) to score once per pair
        if pipe.y > 0 and pipe.centerx < bird_rect.centerx and pipe not in passed_pipes:
            SCORE += 1 # Increment score by 1 for passing a pipe pair
            passed_pipes.append(pipe) # Add the bottom pipe to the passed list

def display_score():
    """Display current score"""
    score_text = FONT.render(f"Score: {int(SCORE)}", True, BLACK)
    SCREEN.blit(score_text, (10, 10))
    
    high_score_text = FONT.render(f"High Score: {int(HIGH_SCORE)}", True, BLACK)
    SCREEN.blit(high_score_text, (10, 50))

    
@monitoringpy.pymonitor(ignore=['SCREEN', 'FONT', 'clock', 'pygame', 'monitoringpy'], return_hooks=[pygame.capture_buffered_pygame_events])
def display_game():
    global GAME_ACTIVE, BIRD_MOVEMENT, pipes, HIGH_SCORE
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            monitoringpy.end_session()
            monitoringpy.PyMonitoring.get_instance().export_db("flappy.db")
            pygame.quit()
            sys.exit()
        
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and GAME_ACTIVE:
                BIRD_MOVEMENT = -7
            
            if event.key == pygame.K_SPACE and not GAME_ACTIVE:
                reset_game()
    
    # Fill background
    SCREEN.fill(BG_COLOR)
    
    if GAME_ACTIVE:
        # Bird movement
        BIRD_MOVEMENT += GRAVITY
        bird_rect.y = int(bird_rect.y + BIRD_MOVEMENT)
        
        # Draw bird
        pygame.draw.rect(SCREEN, RED, bird_rect, border_radius=10)
        
        # Pipe logic
        if len(pipes) == 0 or pipes[-1].x < SCREEN_WIDTH - PIPE_SPAWN_DISTANCE:
            bottom_pipe, top_pipe = create_pipe()
            pipes.append(bottom_pipe)
            pipes.append(top_pipe)
        
        pipes = move_pipes(pipes)
        draw_pipes(pipes)
        
        # Check collision
        if check_collision(pipes, bird_rect):
            GAME_ACTIVE = False
            HIGH_SCORE = max(HIGH_SCORE, SCORE)
        
        # Update score
        update_score(pipes, bird_rect)
        
    else:
        # Game over screen
        game_over_text = FONT.render("Game Over! Press SPACE to restart", True, BLACK)
        SCREEN.blit(game_over_text, (SCREEN_WIDTH//2 - 180, SCREEN_HEIGHT//2 - 15))
    
    # Display score
    display_score()
    
    # Update display
    pygame.display.update()
    clock.tick(60) 

if __name__ == "__main__":
    monitoringpy.init_monitoring(db_path=":memory:")
    monitoringpy.start_session("Flappy Bird")
    while True:
        display_game()