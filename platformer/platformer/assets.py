"""
make_bytebuddy_assets.py
Generate a novel pixel-art style spritesheet + tileset and JSON metadata.

- No import-time side effects (safe to import).
- Optional ubelt cache dir; falls back to ~/.cache/platformer or ./assets/.
- SCALE actually scales output and metadata.
- Returns paths + meta; CLI writes files.

Character: "ByteBuddy" — neon-mask robot slime with hover thrusters.
Tile size: 48x48 by default.

Usage (CLI):
    python make_bytebuddy_assets.py --outdir ./assets --scale 1

See Also:
    https://craftpix.net/freebies/?srsltid=AfmBOor5Nm0DD_AL6PvphX5ctl_74W3c7kI29O0WkAOnjGnLD6hhj_m-
    https://github.com/Erotemic/binary_content
    https://opengameart.org/
    https://kenney.nl/
    https://www.piskelapp.com/
"""

from __future__ import annotations
import json
from pathlib import Path
from math import sin, pi

from PIL import Image, ImageDraw
from platformer.sheetmeta import SpriteSheetMeta, SpriteSheetMetaBuilder


url = 'https://i.imgur.com/auhIpW7.png'

# -----------------------------
# Config
# -----------------------------
TILE = 48
SCALE = 1             # 1 = native pixels; 2/3+ to upscale for “chunkier” pixels
PADDING = 2           # gap between frames
COLS = 8              # frames per row before wrapping
BG = (0, 0, 0, 0)     # transparent

ANIMS = {
    "idle": 4,
    "run": 6,
    "jump": 2,
    "fall": 2,
    "attack": 4,
    "hurt": 1,
}

# Color palette
C = {
    "body": (50, 200, 240, 255),     # cyan body
    "outline": (20, 60, 80, 255),
    "visor": (255, 255, 255, 255),   # visor
    "accent": (255, 90, 150, 255),   # fins
    "thruster": (255, 20, 50, 255), # flame <- edit this
    "shadow": (0, 0, 0, 60),
    "saber": (120, 255, 140, 255)
}

# -----------------------------
# Helpers (pure; no I/O)
# -----------------------------
def _new_canvas(cols: int, rows: int, tile=TILE, padding=PADDING) -> Image.Image:
    w = cols * tile + (cols + 1) * padding
    h = rows * tile + (rows + 1) * padding
    return Image.new("RGBA", (w, h), BG)

def _draw_bytebuddy(draw: ImageDraw.ImageDraw, box, phase=0.0, action="idle"):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2

    # Hover offset for liveliness
    hover = int(2 * sin(phase * 2 * pi))
    y0h = y0 + hover
    y1h = y1 + hover

    # Body
    body_rect = [x0 + 6, y0h + 10, x1 - 6, y1h - 6]
    draw.rounded_rectangle(body_rect, radius=14, fill=C["body"], outline=C["outline"], width=2)

    # Fins (left/right) - wiggle on run/attack
    fin_y = (body_rect[1] + body_rect[3]) // 2
    wiggle = int(4 * sin(phase * 2 * pi)) if action in ("run", "attack") else 0
    # Left fin
    draw.polygon([
        (body_rect[0] - 6, fin_y - 6 + wiggle),
        (body_rect[0] + 2, fin_y),
        (body_rect[0] - 6, fin_y + 6 - wiggle),
    ], fill=C["accent"])
    # Right fin
    draw.polygon([
        (body_rect[2] + 6, fin_y - 6 - wiggle),
        (body_rect[2] - 2, fin_y),
        (body_rect[2] + 6, fin_y + 6 + wiggle),
    ], fill=C["accent"])

    # Visor
    visor_rect = [cx - 10, y0h + 16, cx + 10, y0h + 24]
    draw.rounded_rectangle(visor_rect, radius=4, fill=C["visor"], outline=C["outline"], width=1)

    if action == "hurt":
        # X_X
        draw.line((visor_rect[0]+2,  visor_rect[1]+1, visor_rect[0]+8,  visor_rect[1]+7),  fill=C["outline"], width=2)
        draw.line((visor_rect[0]+8,  visor_rect[1]+1, visor_rect[0]+2,  visor_rect[1]+7),  fill=C["outline"], width=2)
        draw.line((visor_rect[2]-8,  visor_rect[1]+1, visor_rect[2]-2,  visor_rect[1]+7),  fill=C["outline"], width=2)
        draw.line((visor_rect[2]-2,  visor_rect[1]+1, visor_rect[2]-8,  visor_rect[1]+7),  fill=C["outline"], width=2)
    else:
        # Friendly pixels
        draw.rectangle([visor_rect[0]+3, visor_rect[1]+3, visor_rect[0]+6, visor_rect[1]+6], fill=C["outline"])
        draw.rectangle([visor_rect[2]-6, visor_rect[1]+3, visor_rect[2]-3, visor_rect[1]+6], fill=C["outline"])

    # Thrusters on jump/fall
    if action in ("jump", "fall"):
        flame_y = body_rect[3] + 1
        for dx in (-6, 6):
            draw.polygon([
                (cx + dx - 3, flame_y),
                (cx + dx + 3, flame_y),
                (cx + dx, flame_y + 8 + (2 if action == "fall" else 0)) #but also not on the ground
            ], fill=C["thruster"])

    # Attack swipe
    if action == "attack":
        arc_box = [cx - 4, y0h + 6, cx + 30, y0h + 30]
        draw.arc(arc_box, start=300, end=30, fill=C["saber"], width=3)

    # Shadow
    draw.ellipse([cx - 10, y1 - 8, cx + 10, y1 - 4], fill=C["shadow"])

def _build_character_sheet(tile=TILE, padding=PADDING, cols=COLS, anims=ANIMS):
    """Return PIL image + ``SpriteSheetMeta`` (no file I/O)."""
    total_frames = sum(anims.values())
    rows = (total_frames + cols - 1) // cols
    sheet = _new_canvas(cols=cols, rows=rows, tile=tile, padding=padding)
    draw = ImageDraw.Draw(sheet)

    builder = SpriteSheetMetaBuilder(tile=tile, padding=padding, cols=cols,
                                     default_entity="bytebuddy")

    r = c = 0
    for anim_name, count in anims.items():
        boxes = []
        for i in range(count):
            box = builder.grid_box(r, c)
            phase = i / max(count, 1)
            _draw_bytebuddy(draw, box, phase=phase, action=anim_name)
            boxes.append(box)
            c += 1
            if c >= cols:
                c = 0
                r += 1
        builder.add_animation(anim_name, boxes)
    builder.set_image_info(size=sheet.size)
    return sheet, builder.build()

def _build_tileset(tile=TILE, padding=PADDING):
    """Return PIL image (no file I/O)."""
    tiles_across = 8
    rows = 2
    img = _new_canvas(tiles_across, rows, tile=tile, padding=padding)
    d = ImageDraw.Draw(img)

    def tile_box(r, c):
        x = padding + c * (tile + padding)
        y = padding + r * (tile + padding)
        return (x, y, x + tile, y + tile)

    # Row 0: terrain
    # Grass
    b = tile_box(0, 0)
    d.rectangle([b[0], b[1] + 10, b[2], b[3]], fill=(120, 80, 40, 255))     # dirt
    d.rectangle([b[0], b[1] + 4, b[2], b[1] + 14], fill=(90, 200, 90, 255)) # grass cap
    # Dirt
    b = tile_box(0, 1)
    d.rectangle([b[0], b[1], b[2], b[3]], fill=(140, 100, 60, 255))
    # Stone
    b = tile_box(0, 2)
    d.rectangle([b[0], b[1], b[2], b[3]], fill=(110, 120, 130, 255))
    # Metal platform
    b = tile_box(0, 3)
    d.rectangle([b[0], b[1] + 6, b[2], b[3] - 6], fill=(60, 80, 110, 255), outline=(20, 30, 50, 255), width=2)

    # Spikes
    b = tile_box(0, 4)
    for i in range(0, tile, 12):
        d.polygon([(b[0] + i, b[3]), (b[0] + i + 6, b[1] + 10), (b[0] + i + 12, b[3])],
                  fill=(230, 230, 240, 255), outline=(70, 70, 90, 255))

    # Row 1: collectibles & UI
    # Coin
    b = tile_box(1, 0)
    d.ellipse([b[0] + 8, b[1] + 8, b[2] - 8, b[3] - 8], fill=(255, 220, 80, 255),
              outline=(160, 130, 40, 255), width=2)
    # Gem
    b = tile_box(1, 1)
    d.polygon([(b[0]+tile//2, b[1]+6), (b[2]-8, b[1]+tile//2), (b[0]+tile//2, b[3]-6), (b[0]+8, b[1]+tile//2)],
              fill=(120, 230, 255, 255), outline=(40, 100, 130, 255), width=2)
    # Heart
    b = tile_box(1, 2)
    d.polygon([(b[0]+8, b[1]+18), (b[0]+tile//2, b[3]-10), (b[2]-8, b[1]+18),
               (b[2]-14, b[1]+8), (b[0]+tile//2, b[1]+14), (b[0]+14, b[1]+8)],
              fill=(255, 90, 120, 255), outline=(160, 40, 70, 255), width=2)
    # Key
    b = tile_box(1, 3)
    d.ellipse([b[0]+8, b[1]+8, b[0]+24, b[1]+24], outline=(200, 180, 80, 255), width=3)
    d.rectangle([b[0]+24, b[1]+16, b[2]-8, b[1]+20], fill=(200, 180, 80, 255))

    # Debug colored squares
    colors = [(80,160,255,255), (120,220,120,255), (230,120,120,255), (200,200,80,255)]
    for i, col in enumerate(colors):
        b = tile_box(1, 4+i)
        d.rectangle([b[0], b[1], b[2], b[3]], fill=col)

    return img

def _scale_image_and_meta(img: Image.Image, meta: SpriteSheetMeta | None, scale: int):
    """Nearest-neighbor scale; update frame coords if meta provided."""
    if scale == 1:
        return img, meta.copy() if meta else None
    w, h = img.size
    img2 = img.resize((w * scale, h * scale), resample=Image.NEAREST)
    if meta:
        meta = meta.scaled(scale)
    return img2, meta

# -----------------------------
# Public API (safe to import)
# -----------------------------
def generate_assets(out_dir: str | Path | None = None, *, scale: int = SCALE):
    """
    Generate spritesheet, tileset, and meta JSON into `out_dir`.
    Returns dict with paths, sizes, and meta.
    """

    try:
        # Optional; used only to pick a cache path if no --outdir is given.
        import ubelt as ub  # type: ignore
    except Exception:  # pragma: no cover - optional dep
        ub = None

    if out_dir is None:
        if ub is not None:
            out_dir = ub.Path.appdir("platformer").ensuredir()
        else:
            # Fallback: ~/.cache/platformer or ./assets
            home_cache = Path.home() / ".cache" / "platformer"
            out_dir = home_cache if home_cache.parent.exists() else Path("./assets")
            out_dir.mkdir(parents=True, exist_ok=True)

    out_dir = Path(out_dir)

    # Build images & meta in-memory
    sheet_img, meta = _build_character_sheet()
    tiles_img = _build_tileset()

    # Apply scaling
    sheet_img, meta = _scale_image_and_meta(sheet_img, meta, scale)
    tiles_img, _ = _scale_image_and_meta(tiles_img, None, scale)

    # Write files
    sheet_path = out_dir / "bytebuddy_spritesheet.png"
    meta_path  = out_dir / "bytebuddy_meta.json"
    tiles_path = out_dir / "bytebuddy_tileset.png"

    sheet_img.save(sheet_path, "PNG")
    tiles_img.save(tiles_path, "PNG")
    if meta is not None:
        meta.dump(meta_path)
    else:  # pragma: no cover - defensive; generator always returns meta
        with open(meta_path, "w") as f:
            json.dump({}, f, indent=2)

    return {
        "sheet_path": str(sheet_path),
        "meta_path": str(meta_path),
        "tiles_path": str(tiles_path),
        "sheet_size": sheet_img.size,
        "tiles_size": tiles_img.size,
        "meta": meta.to_mapping() if meta else {},
    }

# -----------------------------
# CLI (only runs when executed)
# -----------------------------

# platformer/assets.py
import json, os, pygame  # NOQA
from pathlib import Path  # NOQA
import ubelt as ub  # NOQA


ASSET_DIR = Path(__file__).parent / "assets"
ASSET_DIR = ub.Path.appdir("platformer").ensuredir()


class SpriteSheet:
    """Loads a spritesheet + meta."""

    def __init__(self, image_path, meta_path):
        self.image = pygame.image.load(image_path).convert_alpha()
        self.meta = SpriteSheetMeta.load(meta_path)
        # self.cols = self.meta.cols
        # self.pad = self.meta.padding
        # if default_entity is None:
        try:
            default_entity = self.meta.default_entity_name()
        except KeyError:
            default_entity = None
        self.default_entity = default_entity

    def frame_rect(self, idx):
        return self.meta.frame_rect(idx)

    def frame_surf(self, idx):
        r = self.frame_rect(idx)
        s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        s.blit(self.image, (0, 0), r)
        return s

    def _representative_box_size(self, entity_name: str | None = None) -> tuple[int, int]:
        for box in self.meta.boxes:
            if entity_name is None or box.entity_name == entity_name:
                rect = box.rect
                return rect.w, rect.h
        return (64, 64)

    def anim_surfs(self, name, *, entity_name: str | None = None):
        entity = entity_name or self.default_entity
        try:
            boxes = self.meta.animation_boxes(name, entity_name=entity)
        except KeyError:
            return self._placeholder_surfaces(entity_name=entity, animation_name=name)
        return [self._surface_from_rect(box.rect.to_rect()) for box in boxes]

    def _surface_from_rect(self, rect: pygame.Rect) -> pygame.Surface:
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.blit(self.image, (0, 0), rect)
        return surf

    def _placeholder_surfaces(
        self,
        *,
        entity_name: str | None,
        animation_name: str,
    ) -> list[pygame.Surface]:
        """Return a loud magenta frame when metadata is missing."""
        import warnings

        size = self._representative_box_size(entity_name)
        surf = pygame.Surface(size, pygame.SRCALPHA)
        surf.fill((255, 0, 255))
        rect = surf.get_rect()
        pygame.draw.rect(surf, (0, 0, 0), rect, 2)
        pygame.draw.line(surf, (0, 0, 0), rect.topleft, rect.bottomright, 2)
        pygame.draw.line(surf, (0, 0, 0), rect.topright, rect.bottomleft, 2)

        label = f"{entity_name or 'entity'}:{animation_name}"
        warnings.warn(
            "Missing spritesheet boxes for %s; using placeholder surface instead" % label
        )
        return [surf]


def get_default_paths():
    paths = {
        "sheet":  ASSET_DIR / "bytebuddy_spritesheet.png",
        "meta":   ASSET_DIR / "bytebuddy_meta.json",
        "tiles":  ASSET_DIR / "bytebuddy_tileset.png",
    }
    print(f'paths={paths}')
    return  paths


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Generate ByteBuddy spritesheet/tileset.")
    ap.add_argument("--outdir", type=str, default=None, help="Where to write assets")
    ap.add_argument("--scale", type=int, default=SCALE, help="Integer scale factor (1=original)")
    args = ap.parse_args()
    result = generate_assets(args.outdir, scale=max(1, int(args.scale)))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
