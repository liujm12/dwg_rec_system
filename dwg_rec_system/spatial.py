from __future__ import annotations

import math
from typing import Any

BBox = dict[str, float]


def normalize_bbox(raw: dict[str, Any] | None) -> BBox | None:
    if not raw:
        return None
    try:
        bbox = {
            "min_x": float(raw["min_x"]),
            "min_y": float(raw["min_y"]),
            "max_x": float(raw["max_x"]),
            "max_y": float(raw["max_y"]),
        }
    except (KeyError, TypeError, ValueError):
        return None
    return bbox if is_valid_bbox(bbox) else None


def is_valid_bbox(bbox: dict[str, Any] | None) -> bool:
    if not bbox:
        return False
    try:
        min_x = float(bbox["min_x"])
        min_y = float(bbox["min_y"])
        max_x = float(bbox["max_x"])
        max_y = float(bbox["max_y"])
    except (KeyError, TypeError, ValueError):
        return False
    return max_x > min_x and max_y > min_y


def bbox_area(bbox: dict[str, Any] | None) -> float:
    normalized = normalize_bbox(bbox)
    if not normalized:
        return 0.0
    return round((normalized["max_x"] - normalized["min_x"]) * (normalized["max_y"] - normalized["min_y"]), 6)


def bbox_intersection(a: dict[str, Any] | None, b: dict[str, Any] | None) -> BBox | None:
    first = normalize_bbox(a)
    second = normalize_bbox(b)
    if not first or not second:
        return None
    intersection = {
        "min_x": max(first["min_x"], second["min_x"]),
        "min_y": max(first["min_y"], second["min_y"]),
        "max_x": min(first["max_x"], second["max_x"]),
        "max_y": min(first["max_y"], second["max_y"]),
    }
    return intersection if is_valid_bbox(intersection) else None


def containment_ratio(container: dict[str, Any] | None, contained: dict[str, Any] | None) -> float:
    contained_area = bbox_area(contained)
    if contained_area <= 0:
        return 0.0
    intersection_area = bbox_area(bbox_intersection(container, contained))
    return round(intersection_area / contained_area, 6)


def overlap_ratios(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, float]:
    first_area = bbox_area(a)
    second_area = bbox_area(b)
    intersection_area = bbox_area(bbox_intersection(a, b))
    return {
        "overlap_area": intersection_area,
        "source_overlap_ratio": round(intersection_area / first_area, 6) if first_area > 0 else 0.0,
        "target_overlap_ratio": round(intersection_area / second_area, 6) if second_area > 0 else 0.0,
    }


def bbox_center(bbox: dict[str, Any] | None) -> tuple[float, float] | None:
    normalized = normalize_bbox(bbox)
    if not normalized:
        return None
    return (
        (normalized["min_x"] + normalized["max_x"]) / 2,
        (normalized["min_y"] + normalized["max_y"]) / 2,
    )


def bbox_center_distance(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    first = bbox_center(a)
    second = bbox_center(b)
    if not first or not second:
        return None
    return round(math.dist(first, second), 6)
