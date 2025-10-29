"""Utilities for describing and loading spritesheet metadata.

The project originally stored spritesheet metadata as two parallel collections
(``frames`` and ``anims``) that had to stay in sync.  The teaching tools we now
use instead emit a single flat list of annotated boxes.  Each entry records the
pixel rectangle along with the entity, animation, and frame number that box
belongs to.  The helpers in this module mirror that JSON structure and make it
easy to slice spritesheets at runtime.

The JSON payloads follow a tiny schema intended to be readable and editable by
hand:

.. code-block:: json

   {
     "image_path": "spritesheet.png",
     "image_size": {"w": 1024, "h": 1536},
     "boxes": [
       {
         "id": 0,
         "rect": {"x": 61, "y": 30, "w": 150, "h": 240},
         "entity_name": "bytebuddy",
         "animation_name": "idle",
         "frame_number": 0
       },
       {
         "id": 1,
         "rect": {"x": 256, "y": 30, "w": 150, "h": 240},
         "entity_name": "bytebuddy",
         "animation_name": "idle",
         "frame_number": 1
       }
     ]
   }

Only the ``boxes`` list is required.  ``image_path`` and ``image_size`` are
carried through when present so external tools can embed references to the
source image.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Tuple
import json

import pygame


@dataclass(slots=True)
class FrameSpec:
    """Pixel bounds of a frame inside a spritesheet."""

    x: int
    y: int
    w: int
    h: int

    @classmethod
    def from_box(cls, box: Iterable[int]) -> "FrameSpec":
        x0, y0, x1, y1 = box
        return cls(x=int(x0), y=int(y0), w=int(x1 - x0), h=int(y1 - y0))

    @classmethod
    def from_mapping(cls, data: Mapping[str, int]) -> "FrameSpec":
        return cls(x=int(data["x"]), y=int(data["y"]), w=int(data["w"]), h=int(data["h"]))

    def to_mapping(self) -> Dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    def to_rect(self) -> pygame.Rect:
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def scaled(self, scale: int) -> "FrameSpec":
        if scale == 1:
            return FrameSpec(self.x, self.y, self.w, self.h)
        return FrameSpec(self.x * scale, self.y * scale, self.w * scale, self.h * scale)


@dataclass(slots=True)
class BoxSpec:
    """A cropped region paired with entity/animation metadata."""

    rect: FrameSpec
    entity_name: str
    animation_name: str
    frame_number: int
    id: int | None = None
    extras: Dict[str, object] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "BoxSpec":
        mapping = dict(data)
        rect = FrameSpec.from_mapping(mapping.pop("rect"))
        entity = str(mapping.pop("entity_name"))
        animation = str(mapping.pop("animation_name"))
        frame_number = int(mapping.pop("frame_number"))
        box_id = mapping.pop("id", None)
        if box_id is not None:
            box_id = int(box_id)
        extras = mapping or None
        return cls(
            rect=rect,
            entity_name=entity,
            animation_name=animation,
            frame_number=frame_number,
            id=box_id,
            extras=extras,
        )

    def to_mapping(self) -> MutableMapping[str, object]:
        data: Dict[str, object] = {
            "rect": self.rect.to_mapping(),
            "entity_name": self.entity_name,
            "animation_name": self.animation_name,
            "frame_number": self.frame_number,
        }
        if self.id is not None:
            data["id"] = self.id
        if self.extras:
            data.update(self.extras)
        return data

    def scaled(self, scale: int) -> "BoxSpec":
        if scale == 1:
            rect = FrameSpec(self.rect.x, self.rect.y, self.rect.w, self.rect.h)
        else:
            rect = self.rect.scaled(scale)
        extras = None
        if self.extras:
            extras = dict(self.extras)
        return BoxSpec(
            rect=rect,
            entity_name=self.entity_name,
            animation_name=self.animation_name,
            frame_number=self.frame_number,
            id=self.id,
            extras=extras,
        )


@dataclass
class SpriteSheetMeta:
    """Structured view of the spritesheet metadata JSON."""

    boxes: List[BoxSpec]
    image_path: str | None = None
    image_size: Tuple[int, int] | None = None

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "SpriteSheetMeta":
        image_path = data.get("image_path")
        image_size_raw = data.get("image_size")
        image_size: Tuple[int, int] | None = None
        if image_size_raw:
            image_size = (int(image_size_raw["w"]), int(image_size_raw["h"]))

        boxes_raw = data.get("boxes", [])
        boxes = [BoxSpec.from_mapping(box) for box in boxes_raw]

        return cls(boxes=boxes, image_path=image_path, image_size=image_size)

    @classmethod
    def load(cls, path: Path | str) -> "SpriteSheetMeta":
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_mapping(data)

    def dump(self, path: Path | str) -> None:
        with open(path, "w") as f:
            json.dump(self.to_mapping(), f, indent=2)

    def to_mapping(self) -> MutableMapping[str, object]:
        data: Dict[str, object] = {
            "boxes": [box.to_mapping() for box in self.boxes],
        }
        if self.image_path is not None:
            data["image_path"] = self.image_path
        if self.image_size is not None:
            data["image_size"] = {"w": self.image_size[0], "h": self.image_size[1]}
        return data

    # Convenience helpers -------------------------------------------------

    def frame_rect(self, index: int) -> pygame.Rect:
        return self.boxes[index].rect.to_rect()

    def frame_slice(self, index: int) -> BoxSpec:
        return self.boxes[index]

    def default_entity_name(self) -> str:
        if not self.boxes:
            raise KeyError("No boxes recorded in metadata")
        return self.boxes[0].entity_name

    def entity_names(self) -> List[str]:
        return sorted({box.entity_name for box in self.boxes})

    def animations_for(self, entity_name: str | None = None) -> Dict[str, List[BoxSpec]]:
        entity = entity_name or self.default_entity_name()
        result: Dict[str, List[BoxSpec]] = {}
        for box in self.boxes:
            if box.entity_name != entity:
                continue
            result.setdefault(box.animation_name, []).append(box)
        for boxes in result.values():
            boxes.sort(key=lambda b: (b.frame_number, b.id if b.id is not None else -1))
        return result

    def animation_boxes(self, animation_name: str, entity_name: str | None = None) -> List[BoxSpec]:
        entity = entity_name or self.default_entity_name()
        matches = [
            box
            for box in self.boxes
            if box.entity_name == entity and box.animation_name == animation_name
        ]
        if not matches:
            raise KeyError(f"No boxes recorded for entity={entity!r} animation={animation_name!r}")
        matches.sort(key=lambda b: (b.frame_number, b.id if b.id is not None else -1))
        return matches

    def copy(self) -> "SpriteSheetMeta":
        boxes = [box.scaled(1) for box in self.boxes]
        return SpriteSheetMeta(boxes=boxes, image_path=self.image_path, image_size=self.image_size)

    def scaled(self, scale: int) -> "SpriteSheetMeta":
        if scale == 1:
            return self.copy()
        boxes = [box.scaled(scale) for box in self.boxes]
        image_size = None
        if self.image_size is not None:
            image_size = (self.image_size[0] * scale, self.image_size[1] * scale)
        return SpriteSheetMeta(boxes=boxes, image_path=self.image_path, image_size=image_size)


class SpriteSheetMetaBuilder:
    """Helper for constructing ``SpriteSheetMeta`` objects programmatically."""

    def __init__(self, *, default_entity: str, tile: int | None = None, padding: int | None = None, cols: int | None = None):
        self.default_entity = default_entity
        self.tile = tile
        self.padding = padding
        self.cols = cols
        self.boxes: List[BoxSpec] = []
        self._frame_counts: Dict[tuple[str, str], int] = {}
        self._next_id = 0
        self.image_path: str | None = None
        self.image_size: Tuple[int, int] | None = None

    def set_image_info(self, *, path: Path | str | None = None, size: Tuple[int, int] | None = None) -> None:
        if path is not None:
            self.image_path = str(path)
        if size is not None:
            self.image_size = (int(size[0]), int(size[1]))

    def grid_box(
        self,
        row: int,
        col: int,
        *,
        tile: int | None = None,
        padding: int | None = None,
    ) -> tuple[int, int, int, int]:
        tile_val = tile if tile is not None else self.tile
        pad_val = padding if padding is not None else self.padding
        if tile_val is None or pad_val is None:
            raise ValueError("grid_box requires tile and padding dimensions")
        x = pad_val + col * (tile_val + pad_val)
        y = pad_val + row * (tile_val + pad_val)
        return (x, y, x + tile_val, y + tile_val)

    def _next_frame_number(self, entity: str, animation: str) -> int:
        key = (entity, animation)
        current = self._frame_counts.get(key, 0)
        self._frame_counts[key] = current + 1
        return current

    def add_box(
        self,
        box: Iterable[int],
        *,
        animation_name: str,
        entity_name: str | None = None,
        frame_number: int | None = None,
        extras: Mapping[str, object] | None = None,
    ) -> BoxSpec:
        entity = entity_name or self.default_entity
        rect = FrameSpec.from_box(box)
        if frame_number is None:
            frame_number = self._next_frame_number(entity, animation_name)
        else:
            key = (entity, animation_name)
            self._frame_counts[key] = max(self._frame_counts.get(key, 0), frame_number + 1)
        extras_dict = dict(extras) if extras else None
        spec = BoxSpec(
            rect=rect,
            entity_name=entity,
            animation_name=animation_name,
            frame_number=frame_number,
            id=self._next_id,
            extras=extras_dict,
        )
        self._next_id += 1
        self.boxes.append(spec)
        return spec

    def add_animation(
        self,
        name: str,
        boxes: Iterable[Iterable[int]],
        *,
        entity_name: str | None = None,
        start_frame: int | None = None,
    ) -> None:
        entity = entity_name or self.default_entity
        frame_number = start_frame
        if frame_number is not None:
            key = (entity, name)
            self._frame_counts[key] = frame_number
        for box in boxes:
            if frame_number is None:
                self.add_box(box, animation_name=name, entity_name=entity)
            else:
                self.add_box(
                    box,
                    animation_name=name,
                    entity_name=entity,
                    frame_number=frame_number,
                )
                frame_number += 1

    def build(self) -> SpriteSheetMeta:
        boxes = [box.scaled(1) for box in self.boxes]
        return SpriteSheetMeta(boxes=boxes, image_path=self.image_path, image_size=self.image_size)
