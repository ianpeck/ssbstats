from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum

from .config import FighterPhysics


STAGE_LEFT = -100.0
STAGE_RIGHT = 100.0
STAGE_FLOOR = 0.0
STAGE_CEILING = 80.0


class Action(str, Enum):
    IDLE = "idle"
    MOVE = "move"
    ATTACK = "attack"
    DODGE = "dodge"
    RECOVER = "recover"


@dataclass
class FighterState:
    physics: FighterPhysics
    x: float
    y: float
    damage: float = 0.0
    stocks: int = 3
    last_action: Action = Action.IDLE
    last_hit_at_tick: int = -100

    @property
    def name(self) -> str:
        return self.physics.name

    @property
    def alive(self) -> bool:
        return self.stocks > 0

    def reset_after_ko(self, side: int) -> None:
        # side=-1 spawns left of center, +1 spawns right
        self.x = 30.0 * side
        self.y = 50.0
        self.damage = 0.0
        self.last_action = Action.IDLE


def ko_probability(damage: float, weight: int, threshold: float, steepness: float) -> float:
    # Threshold scales by weight: lighter fighters have a lower effective KO%.
    # Pichu should be in danger around 90-110%, Mario around 140-165%, and
    # Bowser around 190-220%. The simulator handles exact final-score guards in
    # match.py, so this function only models stock danger from current percent.
    eff_threshold = threshold * (weight / 100.0)
    return 1.0 / (1.0 + math.exp(-steepness * (damage - eff_threshold)))


def normal_damage_cap(weight: int) -> float:
    """Highest normal-phase visible percent before a stock must resolve.

    The cap is intentionally weight-sensitive: light fighters should not linger
    near 200%, while super-heavies can occasionally survive past it. Sudden
    death is special-cased in match.py and still starts at 300%.
    """
    return max(145.0, min(225.0, 90.0 + weight))


def hit_probability(
    attacker: FighterState,
    defender: FighterState,
    attacker_bias: float,
    tick: int,
) -> float:
    distance = math.hypot(attacker.x - defender.x, attacker.y - defender.y)
    proximity = max(0.0, 1.0 - distance / 30.0)
    defender_factor = 0.4 if defender.last_action == Action.DODGE else 1.0
    cooldown = 0.4 if tick - attacker.last_hit_at_tick < 8 else 1.0
    # Panic-dodge: high-damage fighters become harder to hit (they're playing
    # defensively to avoid the KO). Caps at 60% of base hit chance at 200%+.
    panic_factor = max(0.6, 1.0 - max(0.0, defender.damage - 100.0) * 0.004)
    base = 0.115 * proximity * defender_factor * cooldown * panic_factor
    return min(0.78, base + attacker_bias)


def random_action(rng: random.Random) -> Action:
    return rng.choices(
        [Action.IDLE, Action.MOVE, Action.ATTACK, Action.DODGE, Action.RECOVER],
        weights=[0.33, 0.43, 0.10, 0.09, 0.05],
    )[0]


def random_damage(physics: FighterPhysics, rng: random.Random) -> float:
    lo, hi = physics.damage_range
    return float(rng.randint(lo, hi))
