"""Haul planner: which observed exhibits fit a bag, a clock, and a job size.

Pure and deterministic: no model call, no store lock, no clock. The same
exhibits and constraints always give the same plan, so the live Mastermind
panel, the reveal, and a Defender Report rendered next week agree to the cent.

Inputs per exhibit:
  weight_lb     pounds. The vision model's estimate for that exact model when
                it gave one, else a per-category default. Either way an
                estimate, and labeled with its source.
  grab_seconds  modeled time to lift and stow it (category default).
  risk_points   how conspicuous carrying it is (category default).
None of these is a measurement or a probability of detection.

Objective: maximize the nominal appraisal value of the bag without going over
the bag's weight, the time on the job, or the job's risk budget. Ties go to
lower total risk, then less time, then less weight, then the lowest exhibit
numbers, so the answer never depends on dict order.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass

OBJECTIVE = (
    "maximize nominal appraisal value within the bag weight, the time, and the job's risk budget; "
    "ties go to lower risk, then less time, then less weight, then lower exhibit numbers"
)

# Category keyword -> (weight_lb, grab_seconds, risk_points). The first
# keyword that starts a word of the exhibit's category wins ("headphones"
# matches headphone; "smart watch" does not match art).
CATEGORY_DEFAULTS: tuple[tuple[str, tuple[float, int, int]], ...] = (
    ("watch", (0.4, 5, 1)),
    ("jewel", (0.3, 5, 1)),
    ("ring", (0.1, 4, 1)),
    ("necklace", (0.2, 5, 1)),
    ("phone", (0.5, 4, 1)),
    ("smartphone", (0.5, 4, 1)),
    ("badge", (0.1, 3, 1)),
    ("card", (0.1, 3, 1)),
    ("wallet", (0.3, 3, 1)),
    ("headphone", (0.7, 6, 1)),
    ("headset", (0.8, 6, 1)),
    ("earbud", (0.1, 4, 1)),
    ("camera", (1.8, 8, 2)),
    ("lens", (1.5, 6, 1)),
    ("book", (1.5, 6, 1)),
    ("tablet", (1.3, 6, 1)),
    ("laptop", (4.5, 10, 2)),
    ("console", (8.0, 12, 2)),
    ("guitar", (9.0, 20, 4)),
    ("lamp", (6.0, 15, 2)),
    ("bag", (3.0, 8, 2)),
    ("art", (12.0, 30, 4)),
    ("painting", (12.0, 30, 4)),
    ("sculpture", (15.0, 30, 4)),
    ("monitor", (12.0, 35, 4)),
    ("tv", (30.0, 40, 5)),
    ("television", (30.0, 40, 5)),
)
# Unknown categories get the conservative (heavy, slow, conspicuous) row.
UNKNOWN_DEFAULT = (10.0, 20, 3)
# Categories that are information, not loot: never selected.
NOT_LOOT = ("exit",)

# Job size. A small job stays quiet: a tight risk budget, and nothing that
# draws a second look on the way out. A big score takes anything that fits.
LEVELS = {
    "small": {"label": "Small job", "risk_points": 6, "max_item_risk": 2,
              "blurb": "quiet: a tight risk budget, nothing conspicuous"},
    "big": {"label": "Big score", "risk_points": 20, "max_item_risk": None,
            "blurb": "loud: anything that fits the bag and the clock"},
}

# Defender Report scenarios: one ordinary backpack and a crew that wants to
# stay unremarkable, at three clocks.
DEFAULT_BAG_LB = 25.0
DEFAULT_RISK_POINTS = 8
SCENARIO_SECONDS = (30, 60, 120)

# Exhaustive search up to this many candidates and this many search nodes;
# past either, the best plan found is returned and labeled "bounded".
EXACT_LIMIT = 40
NODE_BUDGET = 250_000


# One sentence per exclusion code, shared by the live panel and the report.
REASONS = {
    "not_loot": "information, not loot: exits are never taken",
    "no_value": "no appraised value",
    "secured": "owner what-if: marked secured",
    "moved": "owner what-if: moved out of the observed display area",
    "not_considered": "outside the {limit} most valuable candidates the planner weighs",
    "too_conspicuous": "too conspicuous for a small job ({risk} risk; the limit is {max_item_risk} per item)",
    "exceeds_weight": "{weight} lb on its own; the bag holds {bag} lb",
    "exceeds_time": "needs {grab}s on its own; the clock is {time}s",
    "exceeds_risk": "{risk} risk points on its own; the job allows {cap_risk}",
    "excluded": "excluded by the crew",
    "no_room": "fits on its own, but not beside what's already collected",
    "outranked": ("fits on its own ({weight} lb, {grab}s, {risk} risk) but the bag is worth more "
                  "without it"),
}
SHORT_REASONS = {
    "not_loot": "not loot", "no_value": "no value", "secured": "secured", "moved": "moved",
    "not_considered": "not weighed", "too_conspicuous": "too loud", "exceeds_weight": "too heavy",
    "exceeds_time": "too slow", "exceeds_risk": "too risky", "outranked": "outranked",
    "excluded": "excluded", "no_room": "no room",
}


@dataclass(frozen=True)
class Constraints:
    time_s: int
    bag_lb: float = DEFAULT_BAG_LB
    risk_points: int = DEFAULT_RISK_POINTS
    max_item_risk: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def for_level(level: str, bag_lb: float, time_s: int) -> Constraints:
    spec = LEVELS[level]
    return Constraints(int(time_s), float(bag_lb), spec["risk_points"], spec["max_item_risk"])


def attributes(category: str, weight_lb=None) -> dict:
    """Planning attributes for an exhibit, and where each came from."""
    cat = (category or "").strip().lower()
    row, source = UNKNOWN_DEFAULT, "unknown-category default (conservative)"
    for word, values in CATEGORY_DEFAULTS:
        if re.search(rf"\b{word}", cat):
            row, source = values, f"category default ({word})"
            break
    weight, secs, risk = row
    weight_source = source
    if clean_weight(weight_lb) is not None:
        weight, weight_source = clean_weight(weight_lb), "vision-model estimate"
    return {"weight_lb": weight, "grab_seconds": secs, "risk_points": risk,
            "weight_source": weight_source, "attr_source": source}


def clean_weight(raw) -> float | None:
    """Pounds, finite, positive, and no heavier than a person could lift."""
    if isinstance(raw, bool):
        return None                     # JSON true is not "1 lb"
    try:
        w = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(w) or w <= 0 or w > 500:
        return None
    return round(w, 2)


def is_loot(category: str) -> bool:
    return (category or "").strip().lower() not in NOT_LOOT


def plan(exhibits: list[dict], constraints: Constraints,
         unavailable: dict[int, str] | None = None,
         collected: set[int] | None = None) -> dict:
    """Select exhibits for one bag/clock/job.

    exhibits: dicts with n, value_usd, category, weight_lb, grab_seconds,
    risk_points. unavailable: {n: reason} for exhibits the caller has taken
    off the table (an owner what-if: "secured", "moved"; the crew's
    "excluded"). collected: exhibits already in the bag for real. They are
    always selected and spend the budget first; the rest is planned around
    them. If they alone overflow a budget, the plan says so in "conflict".
    """
    unavailable = unavailable or {}
    collected = set(collected or ()) - set(unavailable)
    c = constraints
    cap_w = _tenths(c.bag_lb)
    excluded: dict[int, str] = {}
    candidates = []
    forced = []
    for ex in sorted(exhibits, key=lambda e: e["n"]):
        n = ex["n"]
        if n in collected:
            forced.append(ex)
        elif n in unavailable:
            excluded[n] = unavailable[n]
        elif not is_loot(ex.get("category", "")):
            excluded[n] = "not_loot"
        elif _cents(ex) <= 0:
            excluded[n] = "no_value"
        elif c.max_item_risk is not None and ex["risk_points"] > c.max_item_risk:
            excluded[n] = "too_conspicuous"
        elif _tenths(ex["weight_lb"]) > cap_w:
            excluded[n] = "exceeds_weight"
        elif ex["grab_seconds"] > c.time_s:
            excluded[n] = "exceeds_time"
        elif ex["risk_points"] > c.risk_points:
            excluded[n] = "exceeds_risk"
        else:
            candidates.append(ex)

    algorithm = "exact"
    if len(candidates) > EXACT_LIMIT:
        algorithm = "bounded"
        ranked = sorted(candidates, key=lambda e: (-_cents(e), e["n"]))
        for ex in ranked[EXACT_LIMIT:]:
            excluded[ex["n"]] = "not_considered"
        candidates = ranked[:EXACT_LIMIT]

    # What the collected exhibits already spend, and what that leaves.
    left_w = cap_w - sum(_tenths(ex["weight_lb"]) for ex in forced)
    left_t = c.time_s - sum(ex["grab_seconds"] for ex in forced)
    left_r = c.risk_points - sum(ex["risk_points"] for ex in forced)
    conflict = [name for name, left in (("bag", left_w), ("clock", left_t), ("risk", left_r)) if left < 0]
    base = tuple(ex["n"] for ex in forced)
    if conflict:
        chosen, complete = base, True
    else:
        chosen, complete = _search(candidates, (left_w, left_t, left_r), base)
    if not complete:
        algorithm = "bounded"
    by_n = {ex["n"]: ex for ex in candidates + forced}
    for ex in candidates:
        if ex["n"] not in chosen:
            fits_beside = (not conflict and _tenths(ex["weight_lb"]) <= left_w
                           and ex["grab_seconds"] <= left_t and ex["risk_points"] <= left_r)
            excluded[ex["n"]] = "outranked" if fits_beside or not forced else "no_room"
    picked = [by_n[n] for n in chosen]
    return {
        "objective": OBJECTIVE,
        "algorithm": algorithm,
        "constraints": c.as_dict(),
        "collected": list(base),
        "conflict": conflict,
        "selected": list(chosen),
        "excluded": [{"n": n, "reason": excluded[n]} for n in sorted(excluded)],
        "totals": {
            "value_usd": round(sum(_cents(ex) for ex in picked) / 100, 2),
            "weight_lb": round(sum(_tenths(ex["weight_lb"]) for ex in picked) / 10, 1),
            "grab_seconds": sum(ex["grab_seconds"] for ex in picked),
            "risk_points": sum(ex["risk_points"] for ex in picked),
        },
    }


def _cents(ex: dict) -> int:
    return int(round(float(ex.get("value_usd") or 0) * 100))


def _tenths(lb) -> int:
    """Weights compare in tenths of a pound, rounded up: a bag never overfills on rounding."""
    return int(math.ceil(round(float(lb) * 10, 6)))


def _search(candidates: list[dict], caps: tuple[int, int, int],
            base: tuple[int, ...] = ()) -> tuple[tuple[int, ...], bool]:
    """Exact branch and bound. Returns (exhibit numbers ascending, proven).

    Items go in by value per pound. The bound is the smallest of three
    fractional fills (by weight, by time, by risk) over the items still to
    decide; each relaxes the other two budgets, so none undercuts the true
    best. Ties are explored, not pruned, so the tie-break order holds.
    """
    items = sorted(
        ({"n": ex["n"], "v": _cents(ex), "w": max(1, _tenths(ex["weight_lb"])),
          "t": max(1, ex["grab_seconds"]), "r": max(1, ex["risk_points"])} for ex in candidates),
        key=lambda it: (-it["v"] / it["w"], it["n"]),
    )
    cap_w, cap_t, cap_r = caps
    best = tuple(sorted(base))           # nothing added beyond what's collected
    best_key = (0, 0, 0, 0, best)
    nodes = 0
    complete = True
    count = len(items)
    # For each depth, the undecided items in value-density order per budget.
    orders = {res: [sorted(items[i:], key=lambda it, res=res: -it["v"] / it[res]) for i in range(count + 1)]
              for res in ("w", "t", "r")}

    def fill(order, res, left) -> float:
        total = 0.0
        for it in order:
            if it[res] <= left:
                left -= it[res]
                total += it["v"]
            else:
                return total + it["v"] * left / it[res]
        return total

    def bound(i: int, w_left: int, t_left: int, r_left: int) -> float:
        return min(fill(orders["w"][i], "w", w_left), fill(orders["t"][i], "t", t_left),
                   fill(orders["r"][i], "r", r_left))

    def visit(i, v, w, t, r, chosen):
        nonlocal best_key, best, nodes, complete
        nodes += 1
        if nodes > NODE_BUDGET:
            complete = False
            return
        picked = tuple(sorted(base + tuple(chosen)))
        key = (-v, r, t, w, picked)
        if key < best_key:
            best_key, best = key, picked
        if i == count or v + bound(i, cap_w - w, cap_t - t, cap_r - r) < -best_key[0]:
            return
        it = items[i]
        if w + it["w"] <= cap_w and t + it["t"] <= cap_t and r + it["r"] <= cap_r:
            chosen.append(it["n"])
            visit(i + 1, v + it["v"], w + it["w"], t + it["t"], r + it["r"], chosen)
            chosen.pop()
        visit(i + 1, v, w, t, r, chosen)

    visit(0, 0, 0, 0, 0, [])
    return best, complete


def reason_text(reason: str, item: dict, c: Constraints) -> str:
    return REASONS.get(reason, reason).format(
        limit=EXACT_LIMIT, weight=f"{float(item['weight_lb']):g}", grab=item["grab_seconds"],
        risk=item["risk_points"], time=c.time_s, bag=f"{float(c.bag_lb):g}",
        cap_risk=c.risk_points, max_item_risk=c.max_item_risk)
