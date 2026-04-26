from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterator

from .config import FighterPhysics
from .model import (
    STAGE_CEILING,
    STAGE_FLOOR,
    STAGE_LEFT,
    STAGE_RIGHT,
    Action,
    FighterState,
    hit_probability,
    ko_probability,
    random_action,
    random_damage,
)


SUDDEN_DEATH_DAMAGE = 300.0


@dataclass(frozen=True)
class StockTarget:
    """Constraint that pins the simulator to a real fight's outcome.

    For a normal match: winner ends at exactly `winner_stocks_remaining`, loser at 0.
    For sudden death: both fighters get all stocks taken (a double KO on the last
    stock), then both spawn at 1 stock with 300% damage; winner takes the SD KO
    and ends at 1 stock.
    """
    total_stocks: int                 # 1, 3, or 5 from the fight type
    winner_stocks_remaining: int      # 1..total_stocks; for SD pass 1 (the SD stock)
    is_sudden_death: bool

    @classmethod
    def from_match_result(cls, total_stocks: int, winner_match_result: int) -> "StockTarget":
        if winner_match_result == 0:
            return cls(total_stocks=total_stocks, winner_stocks_remaining=1, is_sudden_death=True)
        return cls(
            total_stocks=total_stocks,
            winner_stocks_remaining=int(winner_match_result),
            is_sudden_death=False,
        )


@dataclass
class MatchConfig:
    match_id: str
    fighter_a: FighterPhysics
    fighter_b: FighterPhysics
    winner_name: str                 # must equal fighter_a.name or fighter_b.name
    target: StockTarget
    tick_rate_hz: float = 10.0
    seed: int | None = None


@dataclass
class TickEvent:
    match_id: str
    tick: int
    elapsed_sec: float
    fighter_a: FighterState
    fighter_b: FighterState
    last_event: str | None = None    # "hit", "ko", "double_ko", "sudden_death_start", "match_over"
    phase: str = "normal"            # "normal" or "sudden_death"

    def to_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "tick": self.tick,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "phase": self.phase,
            "fighters": [
                {
                    "name": f.name,
                    "x": round(f.x, 2),
                    "y": round(f.y, 2),
                    "damage": round(f.damage, 1),
                    "stocks": f.stocks,
                    "action": f.last_action.value,
                }
                for f in (self.fighter_a, self.fighter_b)
            ],
            "event": self.last_event,
        }


def run_match(cfg: MatchConfig) -> Iterator[TickEvent]:
    """Simulate a Smash match constrained to a known final score."""
    if cfg.winner_name not in (cfg.fighter_a.name, cfg.fighter_b.name):
        raise ValueError(f"winner_name {cfg.winner_name!r} must match one of the fighters")

    target = cfg.target
    rng = random.Random(cfg.seed)

    fa = FighterState(physics=cfg.fighter_a, x=-30.0, y=50.0, stocks=target.total_stocks)
    fb = FighterState(physics=cfg.fighter_b, x=30.0, y=50.0, stocks=target.total_stocks)
    winner = fa if fa.name == cfg.winner_name else fb
    loser = fb if winner is fa else fa

    # Death targets in the *normal* phase (before any sudden death):
    if target.is_sudden_death:
        winner_normal_deaths = target.total_stocks - 1   # both end normal play at 1 stock
        loser_normal_deaths = target.total_stocks - 1
    else:
        winner_normal_deaths = target.total_stocks - target.winner_stocks_remaining
        loser_normal_deaths = target.total_stocks        # loser ends at 0 stocks

    winner_deaths = 0
    loser_deaths = 0
    sd_phase = False
    # Adaptive bias: whichever fighter is "behind" on their target death count
    # gets a small advantage. This keeps the simulation converging without making
    # the winner feel dominant when they shouldn't be.
    base_bias = 0.13
    # Per-match KO multiplier — biased by score closeness. In real Smash, 3-0
    # stomps are quick (loser barely lands hits, dies at low %) while close
    # 3-2s drag (both fighters trade at high %, more stock exchanges). SD is
    # treated as MORE close than 3-2 since reaching SD requires the equivalent
    # of a 3-2 path (both reach 1 stock) PLUS the SD finish on top.
    if target.is_sudden_death:
        closeness = 1.5
    else:
        closeness = (target.total_stocks - target.winner_stocks_remaining) / target.total_stocks
    # closeness=0 (3-0): mult ~ 0.55..0.75  (stomp, ~1.5-2.5min)
    # closeness=0.33 (3-1): mult ~ 0.68..0.88
    # closeness=0.67 (3-2): mult ~ 0.82..1.02 (close grind)
    # closeness=1.5 (SD):  mult ~ 1.15..1.35 (longest — 3-2 + SD finish)
    match_ko_mult = 0.55 + closeness * 0.40 + rng.random() * 0.20
    tick_period = 1.0 / cfg.tick_rate_hz
    hard_cap_ticks = int(15 * 60 * cfg.tick_rate_hz)   # 15 minutes — safety net

    def emit(last_event: str | None = None) -> TickEvent:
        return TickEvent(
            match_id=cfg.match_id,
            tick=tick,
            elapsed_sec=tick * tick_period,
            fighter_a=fa,
            fighter_b=fb,
            last_event=last_event,
            phase="sudden_death" if sd_phase else "normal",
        )

    tick = 0
    while tick < hard_cap_ticks:
        # --- Sudden death trigger: both fighters at 1 stock, SD-flagged match ---
        if target.is_sudden_death and not sd_phase and winner.stocks == 1 and loser.stocks == 1:
            # Dramatic double KO: both fighters' last stocks taken simultaneously
            winner.stocks = 0
            loser.stocks = 0
            yield emit(last_event="double_ko")
            tick += 1
            # SD setup: both back to 1 stock at 300%, recentered
            winner.stocks = 1
            loser.stocks = 1
            winner.damage = SUDDEN_DEATH_DAMAGE
            loser.damage = SUDDEN_DEATH_DAMAGE
            winner.x, winner.y = -30.0, 50.0
            loser.x, loser.y = 30.0, 50.0
            sd_phase = True
            yield emit(last_event="sudden_death_start")
            tick += 1
            continue

        last_event: str | None = None

        # --- Pick actions ---
        # In the late-game bias phase, force the fighter that can actually
        # progress the match to attack. Without this, the simulation can stall
        # when winner-attacks-protected-loser-final-stock has no effect.
        force_attack_for = None
        elapsed_for_ramp_pre = tick * tick_period
        if elapsed_for_ramp_pre > 240:  # past 4 min — close out aggressively
            if sd_phase:
                force_attack_for = winner
            else:
                wr_remaining = winner_normal_deaths - winner_deaths
                lr_remaining = loser_normal_deaths - loser_deaths
                if loser.stocks == 1 and wr_remaining > 0:
                    # Loser final-stock-protected until winner takes more deaths
                    force_attack_for = loser
                elif lr_remaining > 0:
                    # Loser still has deaths to take — winner attacks
                    force_attack_for = winner
                else:
                    force_attack_for = winner

        for f in (fa, fb):
            if f is force_attack_for:
                f.last_action = Action.ATTACK
            else:
                f.last_action = random_action(rng)
            if f.last_action == Action.MOVE:
                opp = fb if f is fa else fa
                step = 2.0 if opp.x > f.x else -2.0
                f.x = max(STAGE_LEFT, min(STAGE_RIGHT, f.x + step + rng.uniform(-1, 1)))
                f.y = max(STAGE_FLOOR, min(STAGE_CEILING, f.y + rng.uniform(-1, 1)))

        # Compute who needs the bias this tick. In SD it's always the winner.
        # In normal phase, give it to whichever side has more deaths-still-to-take.
        if sd_phase:
            biased_attacker = winner
        else:
            winner_remaining = winner_normal_deaths - winner_deaths
            loser_remaining = loser_normal_deaths - loser_deaths
            if loser_remaining > winner_remaining:
                biased_attacker = winner          # need more loser KOs
            elif winner_remaining > loser_remaining:
                biased_attacker = loser           # need more winner KOs
            else:
                biased_attacker = winner          # balanced — slight winner default

        # Progressive bias ramp — push convergence after 4.5 min so most matches
        # finish by 6 min, but allow gentle drag through the 4-6 min bucket.
        elapsed_for_ramp = tick * tick_period
        if elapsed_for_ramp > 360:        # past 6 min — hard convergence
            current_bias = 0.55
        elif elapsed_for_ramp > 300:      # 5-6 min
            current_bias = 0.35
        elif elapsed_for_ramp > 270:      # 4.5-5 min
            current_bias = 0.22
        else:
            current_bias = base_bias

        # --- Resolve attacks ---
        for attacker, defender in ((fa, fb), (fb, fa)):
            if attacker.last_action != Action.ATTACK:
                continue
            bias = current_bias if attacker is biased_attacker else 0.0
            if rng.random() >= hit_probability(attacker, defender, bias, tick):
                continue

            defender.damage += random_damage(attacker.physics, rng)
            attacker.last_hit_at_tick = tick
            last_event = "hit"

            ko_prob = ko_probability(
                defender.damage,
                defender.physics.weight,
                defender.physics.ko_curve.threshold * match_ko_mult,
                defender.physics.ko_curve.steepness,
            )
            if rng.random() >= ko_prob:
                continue

            # --- KO safeguards: enforce the historical final score exactly ---
            if sd_phase:
                # In SD, only one stock matters: winner can never lose, loser dies once.
                if defender is winner:
                    continue
            else:
                if defender is winner:
                    if winner_deaths >= winner_normal_deaths:
                        continue   # winner has already taken all the deaths they're allowed
                else:
                    # defender is loser
                    if target.is_sudden_death:
                        # Don't let either fighter reach 0 stocks until both are at 1
                        if loser.stocks == 1 and winner.stocks > 1:
                            continue
                    else:
                        # Don't let loser take their final stock before winner reaches their deaths
                        if loser.stocks == 1 and winner_deaths < winner_normal_deaths:
                            continue

            # Apply the KO
            defender.stocks -= 1
            if defender is winner:
                winner_deaths += 1
            else:
                loser_deaths += 1
            last_event = "ko"

            if defender.stocks > 0:
                side = -1 if defender is fa else 1
                defender.reset_after_ko(side)

        yield emit(last_event=last_event)
        tick += 1

        # --- Match end: loser at 0 stocks ---
        if loser.stocks == 0:
            yield emit(last_event="match_over")
            return

    # Hit the 15-minute hard cap without a natural finish — extremely rare random
    # stall. Force the result so the broadcast still ends cleanly.
    loser.stocks = 0
    yield emit(last_event="match_over")
