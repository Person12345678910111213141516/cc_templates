# settings.py
import pygame

# Window
WIDTH, HEIGHT = 960*2, 540*2
FPS = 60
TITLE = "Pygame Platformer Starter"

# Physics
GRAVITY = 0.5  # pixels/frame^2
JUMP_VEL = -12  # initial jump velocity
DASH_VEL = 75
MOVE_SPEED = 5  # horizontal speed

COYOTE_TIME = 0.12        # seconds after leaving ground where jump still works
JUMP_BUFFER_TIME = 0.12   # seconds to remember a recent jump press
DASH_BUFFER_TIME = 0.2

# Colors
WHITE = pygame.Color(255, 255, 255)
BLACK = pygame.Color(0, 0, 0)
SKY = pygame.Color(135, 206, 235)
GROUND = pygame.Color(60, 60, 80)
PLAYER_COLOR = pygame.Color(255, 100, 100)
PLATFORM_COLOR = pygame.Color(80, 180, 120)

# Tiles
TILE_SIZE = 48
