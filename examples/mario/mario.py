import base64
import io
import pygame
import sys
import monitoringpy

# Initialize Pygame
pygame.init()

# Constants
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
PLAYER_WIDTH = 30
PLAYER_HEIGHT = 40

# Game screen and clock
SCREEN = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Simple Mario Platformer")
FONT = pygame.font.Font(None, 36)
clock = pygame.time.Clock()

# Game variables
player_x = 50
player_y = SCREEN_HEIGHT - 100
player_vel_x = 0
player_vel_y = 0
on_ground = False
score = 0

# Platforms
platforms = [
    {'x': 200, 'y': 500, 'width': 150, 'height': 20},
    {'x': 400, 'y': 400, 'width': 100, 'height': 20},
    {'x': 600, 'y': 300, 'width': 120, 'height': 20},
    {'x': 100, 'y': 350, 'width': 80, 'height': 20},
    {'x': 550, 'y': 500, 'width': 100, 'height': 20},
    {'x': 300, 'y': 200, 'width': 150, 'height': 20},
    {'x': 0, 'y': 250, 'width': 80, 'height': 20},
    {'x': 700, 'y': 450, 'width': 100, 'height': 20},
]

# Coins
coins = [
    {'x': 225, 'y': 470, 'collected': False},
    {'x': 430, 'y': 370, 'collected': False},
    {'x': 630, 'y': 270, 'collected': False},
    {'x': 330, 'y': 170, 'collected': False},
    {'x': 580, 'y': 470, 'collected': False},
]

def update_player():
    """Update player position and handle collisions"""
    global player_x, player_y, player_vel_x, player_vel_y, on_ground
    
    # Handle horizontal movement
    keys = get_pressed_keys()
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        player_vel_x = -5  # Player speed
    elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        player_vel_x = 5  # Player speed
    else:
        player_vel_x = 0
        
    # Handle jumping
    if (keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]) and on_ground:
        player_vel_y = -14  # Jump strength
        on_ground = False
        
    # Apply gravity
    player_vel_y += 0.9  # Gravity
    
    # Update position
    player_x += player_vel_x
    player_y += player_vel_y
    
    # Keep player on screen (horizontal boundaries)
    if player_x < 0:
        player_x = 0
    elif player_x + PLAYER_WIDTH > SCREEN_WIDTH:
        player_x = SCREEN_WIDTH - PLAYER_WIDTH
        
    # Check collision with platforms
    on_ground = False
    player_rect = pygame.Rect(player_x, player_y, PLAYER_WIDTH, PLAYER_HEIGHT)
    
    for platform in platforms:
        platform_rect = pygame.Rect(platform['x'], platform['y'], platform['width'], platform['height'])
        
        if player_rect.colliderect(platform_rect):
            # Landing on top of platform
            if player_vel_y > 0 and player_y < platform['y']:
                player_y = platform['y'] - PLAYER_HEIGHT
                player_vel_y = 0
                on_ground = True
            # Hit platform from below
            elif player_vel_y < 0 and player_y > platform['y']:
                player_y = platform['y'] + platform['height']
                player_vel_y = 0
            # Hit platform from the side
            elif player_vel_x > 0:  # Moving right
                player_x = platform['x'] - PLAYER_WIDTH
            elif player_vel_x < 0:  # Moving left
                player_x = platform['x'] + platform['width']
    
    # Ground collision (bottom of screen)
    if player_y + PLAYER_HEIGHT >= SCREEN_HEIGHT:
        player_y = SCREEN_HEIGHT - PLAYER_HEIGHT
        player_vel_y = 0
        on_ground = True

def check_coin_collection():
    """Check if player collects coins"""
    global score
    
    player_rect = pygame.Rect(player_x, player_y, PLAYER_WIDTH, PLAYER_HEIGHT)
    for coin in coins:
        if not coin['collected']:
            coin_rect = pygame.Rect(coin['x'], coin['y'], 20, 20)
            if player_rect.colliderect(coin_rect):
                coin['collected'] = True
                score += 10

def reset_game():
    """Reset game to initial state"""
    global player_x, player_y, player_vel_x, player_vel_y, on_ground, score
    
    player_x = 50
    player_y = SCREEN_HEIGHT - 100
    player_vel_x = 0
    player_vel_y = 0
    on_ground = False
    score = 0
    
    for coin in coins:
        coin['collected'] = False

def save_screen(m, c, o, r):
    """Save the current screen as a base64 encoded image"""
    buffer = io.BytesIO()
    pygame.image.save(pygame.display.get_surface(), buffer, "PNG")
    return {"image": base64.encodebytes(buffer.getvalue()).decode('utf-8')}

def get_events():
    """Get pygame events"""
    return pygame.event.get()

def get_pressed_keys():
    """Get pygame key pressed states"""
    return pygame.key.get_pressed()

@monitoringpy.pymonitor(
    ignore=['SCREEN', 'FONT', 'clock'], 
    return_hooks=[save_screen],
    track=[get_events, get_pressed_keys]
)
def display_game():
    """Main game loop function that is monitored"""
    # Handle events
    for event in get_events():
        if event.type == pygame.QUIT:
            return False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            elif event.key == pygame.K_r:
                # Reset game
                reset_game()
    
    # Update game state
    update_player()
    check_coin_collection()
    
    # Draw everything
    # Fill background
    SCREEN.fill((135, 206, 235))  # Sky blue
    
    # Draw platforms
    for platform in platforms:
        pygame.draw.rect(SCREEN, (139, 69, 19),  # Brown color
                       (platform['x'], platform['y'], platform['width'], platform['height']))
        # Add some texture to platforms
        pygame.draw.rect(SCREEN, (0, 0, 0),  # Black border
                       (platform['x'], platform['y'], platform['width'], platform['height']), 2)
    
    # Draw ground
    pygame.draw.rect(SCREEN, (0, 255, 0), (0, SCREEN_HEIGHT - 20, SCREEN_WIDTH, 20))  # Green ground
    
    # Draw coins
    for coin in coins:
        if not coin['collected']:
            pygame.draw.circle(SCREEN, (255, 255, 0), (coin['x'] + 10, coin['y'] + 10), 8)  # Yellow coin
            pygame.draw.circle(SCREEN, (0, 0, 0), (coin['x'] + 10, coin['y'] + 10), 8, 2)  # Black coin border
    
    # Draw player
    pygame.draw.rect(SCREEN, (255, 0, 0), (player_x, player_y, PLAYER_WIDTH, PLAYER_HEIGHT))  # Red player
    # Draw simple face
    pygame.draw.circle(SCREEN, (0, 0, 0), (int(player_x + PLAYER_WIDTH * 0.3), int(player_y + PLAYER_HEIGHT * 0.3)), 3)  # Black eye
    pygame.draw.circle(SCREEN, (0, 0, 0), (int(player_x + PLAYER_WIDTH * 0.7), int(player_y + PLAYER_HEIGHT * 0.3)), 3)  # Black eye
    
    # Draw score
    score_text = FONT.render(f"Score: {score}", True, (0, 0, 0))  # Black text
    SCREEN.blit(score_text, (10, 10))
    
    # Draw instructions
    if score == 0:
        instructions = [
            "Use ARROW KEYS or WASD to move",
            "SPACE/UP/W to jump",
            "Collect yellow coins!",
            "Press R to reset, ESC to quit"
        ]
        for i, instruction in enumerate(instructions):
            text = FONT.render(instruction, True, (0, 0, 0))  # Black text
            SCREEN.blit(text, (10, 50 + i * 30))
    
    # Draw win message
    if score >= 50:
        win_text = FONT.render("YOU WIN! Press R to play again", True, (0, 255, 0))  # Green text
        text_rect = win_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
        pygame.draw.rect(SCREEN, (255, 255, 255), text_rect.inflate(20, 10))  # White background
        SCREEN.blit(win_text, text_rect)
    
    pygame.display.flip()
    clock.tick(60)  # 60 FPS
    return True

if __name__ == "__main__":
    monitor = monitoringpy.init_monitoring(db_path="mario.db", custom_picklers=["pygame"])
    monitoringpy.start_session("Mario Platformer")
    while display_game():
        pass
    monitoringpy.end_session()
    pygame.quit() 