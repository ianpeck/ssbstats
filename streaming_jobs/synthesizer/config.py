from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class KoCurve:
    threshold: float
    steepness: float


@dataclass(frozen=True)
class FighterPhysics:
    name: str
    weight: int
    damage_range: tuple[int, int]
    fall_speed: float
    starting_stocks: int
    ko_curve: KoCurve


def load_physics(config_path: Path) -> dict[str, FighterPhysics]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    defaults = raw.get("defaults", {}) or {}
    fighters_raw = raw.get("fighters", {}) or {}

    def _build(name: str, override: dict | None) -> FighterPhysics:
        merged = {**defaults, **(override or {})}
        ko = {**(defaults.get("ko_curve") or {}), **((override or {}).get("ko_curve") or {})}
        damage_range = tuple(merged.get("damage_range", [2, 25]))
        return FighterPhysics(
            name=name,
            weight=int(merged["weight"]),
            damage_range=(int(damage_range[0]), int(damage_range[1])),
            fall_speed=float(merged.get("fall_speed", 1.0)),
            starting_stocks=int(merged.get("starting_stocks", 3)),
            ko_curve=KoCurve(
                threshold=float(ko.get("threshold", 100)),
                steepness=float(ko.get("steepness", 0.05)),
            ),
        )

    return {name: _build(name, override) for name, override in fighters_raw.items()}
