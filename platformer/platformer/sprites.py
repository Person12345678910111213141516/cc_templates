# sprites.py (Player class)
import pygame
from .settings import (
    PLAYER_COLOR, MOVE_SPEED, GRAVITY, JUMP_VEL, TILE_SIZE,
    COYOTE_TIME, JUMP_BUFFER_TIME
)
from .anim import AnimSprite
from .assets import SpriteSheet, get_default_paths

# flip to False to use colored rectangles
# USE_SPRITES = False
USE_SPRITES = True


class Player(pygame.sprite.Sprite):
    def __init__(self, start_pos):
        super().__init__()
        # physics body (rect only; visual can be different size if you prefer)
        self.rect = pygame.Rect(start_pos[0], start_pos[1],
                                int(TILE_SIZE * 0.8), int(TILE_SIZE * 0.9))
        self.pos = pygame.Vector2(self.rect.topleft)
        self.vel = pygame.Vector2(0, 0)
        self.on_ground = False

        # jump helpers
        self.coyote_timer = 0.0
        self.jump_buffer_timer = 0.0
        self.jumps = 0

        # visuals
        self.visual = None
        if USE_SPRITES:
            paths = get_default_paths()
            sheet = SpriteSheet(paths["sheet"], paths["meta"])
            anims = {
                "idle":   sheet.anim_surfs("idle"),
                "run":    sheet.anim_surfs("run"),
                "jump":   sheet.anim_surfs("jump"),
                "fall":   sheet.anim_surfs("fall"),
                "attack": sheet.anim_surfs("attack"),
                "hurt":   sheet.anim_surfs("hurt"),
            }
            self.visual = AnimSprite(anims, pos=self.rect.topleft, fps=10)
        else:
            self.image = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
            self.image.fill(PLAYER_COLOR)

    # ---------- input & movement ----------
    def handle_input(self, keys):
        self.vel.x = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.vel.x = -MOVE_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vel.x = MOVE_SPEED

    def queue_jump(self):
        """Record a jump press; will fire when allowed (buffered)."""
        self.jump_buffer_timer = JUMP_BUFFER_TIME

    def _do_jump(self):
        self.vel.y = JUMP_VEL
        self.on_ground = False
        self.coyote_timer = 0.0
        self.jump_buffer_timer = 0.0

    def apply_gravity(self):
        self.vel.y += GRAVITY

    def move_and_collide(self, solids):
        # Horizontal
        self.pos.x += self.vel.x
        self.rect.x = int(self.pos.x)
        hits = [r for r in solids if self.rect.colliderect(r)]
        for r in hits:
            if self.vel.x > 0:
                self.rect.right = r.left
            elif self.vel.x < 0:
                self.rect.left = r.right
            self.pos.x = self.rect.x

        # Vertical
        self.pos.y += self.vel.y
        self.rect.y = int(self.pos.y)
        hits = [r for r in solids if self.rect.colliderect(r)]
        self.on_ground = False
        for r in hits:
            if self.vel.y > 0:
                self.rect.bottom = r.top
                self.on_ground = True
                self.vel.y = 0
                self.jumps = 0
            elif self.vel.y < 0:
                self.rect.top = r.bottom
                self.vel.y = 0
            self.pos.y = self.rect.y

        if self.on_ground:
            self.coyote_timer = COYOTE_TIME

    # ---------- main update ----------
    def update(self, keys, solids, dt):
        # tick timers
        if self.coyote_timer > 0:
            self.coyote_timer -= dt
        if self.jump_buffer_timer > 0:
            self.jump_buffer_timer -= dt

        self.handle_input(keys)
        self.apply_gravity()
        self.move_and_collide(solids)

        # consume buffered jump if allowed
        if (self.jump_buffer_timer > 0) and (self.on_ground or self.coyote_timer > 0 or self.jumps < 2):
            self._do_jump()
            self.jumps += 1

        # visuals
        if self.visual:
            if not self.on_ground:
                state = "jump" if self.vel.y < 0 else "fall"
            elif abs(self.vel.x) > 0.1:
                state = "run"
            else:
                state = "idle"
            if not state == "fall":
                self.visual.set(state)
            self.visual.rect.topleft = self.rect.topleft
            self.visual.update(dt, flip=(self.vel.x < 0))