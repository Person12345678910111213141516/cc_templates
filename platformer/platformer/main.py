# main.py
import sys
import pygame
from platformer.settings import WIDTH, HEIGHT, FPS, TITLE, SKY, GROUND
from platformer.settings import WHITE
from platformer.level import Level
from platformer.sprites import Player


TILE_SIZE = 48

def compute_camera_offset(player_rect, level_size, screen_size, margin=200):
    """
    A simple camera that follows the player but clamps to level bounds.
    margin: how much 'deadzone' around player before camera pans.
    """
    lx, ly = level_size
    sw, sh = screen_size

    # Desired center on player
    target_x = player_rect.centerx - sw // 2
    target_y = player_rect.centery - sh // 2

    # Optional deadzone (smooth panning)
    dx = 0
    if player_rect.centerx < margin:
        dx = margin - player_rect.centerx
    elif player_rect.centerx > (lx - margin):
        dx = (lx - margin) - player_rect.centerx

    dy = 0
    if player_rect.centery < margin:
        dy = margin - player_rect.centery
    elif player_rect.centery > (ly - margin):
        dy = (ly - margin) - player_rect.centery

    target_x -= dx
    target_y -= dy

    # Clamp to level
    target_x = max(0, min(target_x, lx - sw))
    target_y = max(0, min(target_y, ly - sh))

    return pygame.Vector2(target_x, target_y)


def draw_grid(surface, offset, grid=48, color=(255, 255, 255, 30)):
    # lightly draw a grid to help students visualize tiles
    w, h = surface.get_size()
    ox, oy = int(offset.x), int(offset.y)
    grid_color = surface.map_rgb(color[:3])
    for x in range(-ox % grid, w, grid):
        pygame.draw.line(surface, grid_color, (x, 0), (x, h), 1)
    for y in range(-oy % grid, h, grid):
        pygame.draw.line(surface, grid_color, (0, y), (w, y), 1)


def render_view(
    world_surface: pygame.Surface,
    camera_offset: pygame.Vector2,
    view_size: tuple[int, int],
    bg_color=(135, 206, 235, 255),
) -> pygame.Surface:
    """
    Returns a view-sized surface showing the world at camera_offset.
    Handles edges (off-level regions) by filling with bg_color.
    No subsurface OOB errors.
    """
    vw, vh = view_size
    view = pygame.Surface((vw, vh), pygame.SRCALPHA)
    # Fill with sky (or any background)
    view.fill(bg_color)

    # Where we want to place the world onto the view
    dest = pygame.Rect(0, 0, vw, vh)

    # Portion of the world we can actually sample
    src = pygame.Rect(int(camera_offset.x), int(camera_offset.y), vw, vh)
    world_rect = world_surface.get_rect()
    src_clamped = src.clip(world_rect)

    if src_clamped.width > 0 and src_clamped.height > 0:
        # Match destination to the clipped area (shift by how much we were outside)
        dx = src_clamped.x - src.x
        dy = src_clamped.y - src.y
        dest_clamped = dest.move(dx, dy)
        view.blit(world_surface, dest_clamped, src_clamped)

    return view


def compute_camera_offset_zoomaware(
    target_rect: pygame.Rect,
    level_size: tuple[int, int],
    view_size: tuple[int, int],
    zoom: float = 1.0,
    edge_pad: int = 512,
) -> pygame.Vector2:
    """
    Clamp at zoom=1, allow off-level 'peek' when zoomed out (<1),
    and tighter clamp when zoomed in (>1).
    """
    lx, ly = level_size
    vw, vh = view_size

    target_x = target_rect.centerx - vw // 2
    target_y = target_rect.centery - vh // 2

    # When zoom=1, strict clamp to level
    if abs(zoom - 1.0) < 1e-3:
        target_x = max(0, min(target_x, lx - vw))
        target_y = max(0, min(target_y, ly - vh))
    elif zoom < 1.0:
        # zoomed out: allow extra lookaround proportional to how far zoomed out
        pad = int(edge_pad * (1.0 - zoom))
        target_x = max(-pad, min(target_x, lx - vw + pad))
        target_y = max(-pad, min(target_y, ly - vh + pad))
    else:
        # zoomed in: smaller view; keep clamped tighter so we don’t see voids
        target_x = max(0, min(target_x, lx - vw))
        target_y = max(0, min(target_y, ly - vh))

    return pygame.Vector2(target_x, target_y)


def main():
    camera_zoom = 1.0
    ZOOM_STEP = 0.9
    MIN_ZOOM = 0.4
    MAX_ZOOM = 3.0
    EDGE_PAD = 512

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    level = Level(platform_color=(80, 180, 120))
    player = Player(start_pos=(100, 100))

    # Build a canvas larger than the level so we can draw offscreen content
    world_w, world_h = level.size
    universe_w = world_w + EDGE_PAD * 2
    universe_h = world_h + EDGE_PAD * 2
    universe_surface = pygame.Surface((universe_w, universe_h), pygame.SRCALPHA)

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_SPACE, pygame.K_w, pygame.K_UP):
                    player.queue_jump()
                elif event.key in (pygame.K_s, pygame.K_DOWN):
                    player.queue_dash()
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    camera_zoom = max(MIN_ZOOM, camera_zoom * ZOOM_STEP)
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                    camera_zoom = min(MAX_ZOOM, camera_zoom / ZOOM_STEP)

        keys = pygame.key.get_pressed()
        player.update(keys, level.solids, dt)

        # Determine viewport size based on zoom
        view_w = int(screen.get_width() / camera_zoom)
        view_h = int(screen.get_height() / camera_zoom)

        # Compute offset with conditional clamp
        camera_offset_world = compute_camera_offset_zoomaware(
            player.rect,
            level.size,
            (view_w, view_h),
            zoom=camera_zoom,
            edge_pad=EDGE_PAD,
        )

        # Draw world to buffer
        # Convert WORLD camera offset to UNIVERSE coords by adding EDGE_PAD
        camera_offset_universe = pygame.Vector2(
            camera_offset_world.x + EDGE_PAD,
            camera_offset_world.y + EDGE_PAD
        )

        # Draw world (level + player) into the UNIVERSE canvas
        universe_surface.fill(SKY)  # fill off-level space with sky
        # Level.draw subtracts the given offset: pass negative to place level at +EDGE_PAD
        level.draw(universe_surface, pygame.Vector2(-EDGE_PAD, -EDGE_PAD))
        # Grid in universe coords so it scrolls/zooms with the world
        draw_grid(
            universe_surface,
            pygame.Vector2(-EDGE_PAD, -EDGE_PAD),
            grid=TILE_SIZE,
            color=(255, 255, 255, 40),
        )
        # Player in universe coords
        if player.visual:
            universe_surface.blit(
                player.visual.image,
                (EDGE_PAD + player.rect.x, EDGE_PAD + player.rect.y),
            )
        else:
            pygame.draw.rect(
                universe_surface,
                (255, 100, 100),
                pygame.Rect(EDGE_PAD + player.rect.x, EDGE_PAD + player.rect.y, player.rect.w, player.rect.h),
            )

        # Safe render + scale to screen
        view = render_view(universe_surface, camera_offset_universe, (view_w, view_h), bg_color=SKY)
        scaled_view = pygame.transform.scale(view, screen.get_size())
        screen.blit(scaled_view, (0, 0))

        # HUD
        font = pygame.font.SysFont(None, 24)
        screen.blit(
            font.render("Arrows/A-D move, Space/W/Up jump", True, WHITE), (12, 10)
            
        )
        screen.blit(
            font.render(
                f"Zoom: {camera_zoom:.2f}  EdgePad: {EDGE_PAD}, Zoom: {camera_zoom:.2f}",
                True,
                WHITE,
            ),
            (12, 34),
        )

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
