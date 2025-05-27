import base64
import io
import random
import pygame
import monitoringpy

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
PIPE_SPEED = 3  
PIPE_SPAWN_DISTANCE = 300
GAME_ACTIVE = True
SCORE = 0
HIGH_SCORE = 0
FONT = pygame.font.SysFont("Arial", 30)

# Bird parameters
BIRD_SIZE = 40
bird_rect = pygame.Rect(SCREEN_WIDTH // 3, SCREEN_HEIGHT // 2, BIRD_SIZE, BIRD_SIZE)

# Pipe list
pipes = []

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

def move_pipes():
    global pipes
    pipes_to_remove = []
    for pipe in pipes:
        pipe.x -= PIPE_SPEED
        if pipe.right < 0: # Check if pipe is completely off-screen to the left
            pipes_to_remove.append(pipe)
        
    # Clean up passed_pipes list
    for p in pipes_to_remove:
        pipes.remove(p)

def draw_pipes():
    """Draw all pipes"""
    global pipes
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
    global BIRD_MOVEMENT, GAME_ACTIVE, SCORE, pipes
    bird_rect.y = SCREEN_HEIGHT // 2
    BIRD_MOVEMENT = 0
    pipes.clear()
    GAME_ACTIVE = True
    SCORE = 0

def get_events():
    return pygame.event.get()

def save_screen(m,c,o,r):
    buffer = io.BytesIO()
    pygame.image.save(pygame.display.get_surface(), buffer, "PNG")
    return {"image": base64.encodebytes(buffer.getvalue()).decode('utf-8')}

@monitoringpy.pymonitor(
        ignore=['SCREEN','FONT', 'clock'], 
        return_hooks=[save_screen],
        track=[get_events,create_pipe])
def display_game():
    global GAME_ACTIVE, BIRD_MOVEMENT, pipes, HIGH_SCORE
    for event in get_events():
        if event.type == pygame.QUIT:
            return False
        
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
        
        move_pipes()
        draw_pipes()
        
        # Check collision
        if check_collision(pipes, bird_rect):
            GAME_ACTIVE = False
            HIGH_SCORE = max(HIGH_SCORE, SCORE)
        
        
    else:
        # Game over screen
        game_over_text = FONT.render("Game Over! \nPress SPACE to restart", True, BLACK)
        SCREEN.blit(game_over_text, (SCREEN_WIDTH//2 - 180, SCREEN_HEIGHT//2 - 15))
    
    
    # Update display
    pygame.display.update()
    clock.tick(60) 
    return True


if __name__ == "__main__":
    monitor = monitoringpy.init_monitoring(db_path=":memory:", custom_picklers=["pygame"])
    monitoringpy.start_session("Flappy Bird")
    while display_game():
        pass
    monitoringpy.end_session()
    monitor.export_db("flappy.db")
    pygame.quit()
