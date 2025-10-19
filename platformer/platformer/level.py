# level.py
import pygame
from platformer.settings import TILE_SIZE

# A simple ASCII tilemap: 'X' = solid, '.' = empty
# Make the level wider than the screen to see scrolling
TILEMAP = [
    "...............................................X",
    "...............................................X",
    "...............................................X",
    "...............................................X",
    "....................XXX........................X",
    "............................XX.................X",
    "..............XXX..............................X",
    "...............................................X",
    "......................XXXX.....................X",
    "............................x..................X",
    "XXXX..........................X................X",
    "....XXXX.........................XXX...........X",
    ".................XXX...........................X",
    ".....................................X.........X",
    "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
]


class Platform(pygame.sprite.Sprite):
    def __init__(self, x, y, w, h, color):
        super().__init__()
        self.image = pygame.Surface((w, h))
        self.image.fill(color)
        # insert hypothetical image here
        # self.image = pygame.image.load("file.png").convert_alpha()
        self.rect = self.image.get_rect(topleft=(x, y))


class Level:
    def __init__(self, platform_color):
        self.platforms = pygame.sprite.Group()
        self.solids = []  # list of rects for collision speed

        for row_idx, row in enumerate(TILEMAP):
            for col_idx, ch in enumerate(row):
                if ch == "X":
                    x = col_idx * TILE_SIZE
                    y = row_idx * TILE_SIZE
                    plat = Platform(x, y, TILE_SIZE, TILE_SIZE, platform_color)
                    self.platforms.add(plat)
                    self.solids.append(plat.rect)

        # Level bounds (for camera clamping)
        width = len(TILEMAP[0]) * TILE_SIZE
        height = len(TILEMAP) * TILE_SIZE
        self.size = (width, height)

    def draw(self, surface, offset):
        # Draw platforms with camera offset
        for p in self.platforms:
            surface.blit(p.image, p.rect.move(-offset.x, -offset.y))
