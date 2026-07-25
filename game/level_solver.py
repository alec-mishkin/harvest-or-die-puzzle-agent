#!/usr/bin/env python3
"""
Standalone minimum-turns solver for the "bunny/harvest" game.

This is a from-scratch, standalone re-implementation (no game code imported or
modified) of the exact turn-resolution rules found in:
    Assets/Scripts/Game_Master.cs
    Assets/Scripts/Prey.cs / Animal.cs / Predator.cs
    Assets/Scripts/plant_plot.cs / slime_plot.cs
    Assets/Scripts/Predator_Master.cs / Pathfinding.cs / Grid_Generator.cs
    Assets/Scripts/Animal_Generator.cs
    Assets/Scripts/Score_and_Timer.cs

It parses a level CSV + a Level_Stats .asset file the same (buggy) way the
game does, then does a breadth-first search over (harvest choice, move
direction) turns to find the minimum number of MOVES (only moves cost a
turn; harvesting is free) needed to reach the win condition: every scored
cell on the board is a Plant of a single color (0 holes, 0 off-color
plants).

Known fidelity notes / deliberately-reproduced engine quirks (see README):
  1. Load_Level(string) drops the LAST TWO rows of the CSV (an actual bug in
     Game_Master.cs the level authors work around by padding levels with two
     filler rows). We replicate that here.
  2. Check_If_Fruit_In_Grid() checks plant_type_color on EVERY cell
     (including walls/ground/spawn tiles), and those tiles never have their
     color explicitly set -> they default to enum value 0 = PLANT_TYPE_COLOR.Red.
     This means "is Red still on the board" always reports True. We reproduce
     this exactly.
  3. Hole regrowth safety window: because the death check on arrival runs
     BEFORE that cycle's growth phase, a tile harvested while dwelling at
     turn T is only safe to step on again once you're dwelling at turn T+2
     (i.e. your 3rd move after harvesting it). Implemented via literal phase
     ordering (harvest -> move -> predator turn -> growth), not a hand-derived
     formula, specifically to avoid getting this subtle timing wrong.
  4. Predators decide their NEXT move's target at the end of the current
     cycle (or at spawn time), so they always move toward where the bunny
     WAS one cycle ago, not where it currently is. A freshly-spawned predator
     doesn't move on its spawn cycle (it only computes its first target).
  5. Predator A* pathing applies a large one-time cost penalty against
     stepping onto a not-about-to-regrow Hole, and a smaller one against a
     tile already claimed by another predator this cycle -- but ONLY for the
     immediate first hop out of its current tile (Pathfinding.cs
     Get_Environmental_Cost is only added when currentNode == startNode).
  6. Score_and_Timer.Calculate_Percentage() excludes the LAST row and LAST
     column of the grid from scoring (an off-by-one the devs left in).
  7. One real non-determinism: Predator_Master.Find_Closest_Movement()
     shuffles tied candidate moves with UnityEngine.Random before picking.
     There is no fixed seed anywhere in the project, so this cannot be
     replayed exactly from outside Unity. We break ties using stable
     "natural" offset order (no shuffle) and print a warning if a genuine
     tie is ever hit during the solve, since that's the one place a real
     playthrough could diverge from this tool's predicted predator move.

Not modeled (not present in level_14, will raise a clear error if hit):
  dual-color alternating tiles (br/rb/by/ry/yb/yr), random-color tiles
  (P / CP), and the tutorial `Condition` gating system.
"""
from __future__ import annotations

import argparse
import itertools
import random
import re
import sys
from collections import deque
from dataclasses import dataclass, field, replace
from enum import IntEnum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------
# Constants confirmed from the Unity scene / prefabs (not per-level data):
#   Assets/Scenes/Levels/Tutorial_Levels/Iphone_Portrait_Level.unity
#     Game_Master.always_die_over_hole      = 1
#     Game_Master.slime_spawns_kill         = 0
#     Animal_Generator.max_change_turn      = 2
#     Animal_Generator.generate_on_first_turn = 1  -- a ONE-SHOT rule, independent of the
#       normal max_change_turn timer: Update() readies a predator on the very first frame
#       (turn_count still 0, before any move), consuming the flag permanently. That predator
#       then actually spawns (per slime_plot.check_to_generate's usual "turn_count -
#       turn_readied > 0" rule) right after the player's FIRST move, i.e. at turn 1, not
#       later as the max_change_turn timer alone would produce. Confirmed against a real
#       playthrough of level_14 (2026-07-07): the spawn tile is readied from turn 0 and the
#       slime appears after move 1.
#   Assets/prefabs/Grid_Points/*.prefab
#     plant_plot.change_max_length = 2  (uniform across all grid_point prefab versions)
# --------------------------------------------------------------------------
LEVELS_DIR = Path(__file__).resolve().parent / "levels"
DEFAULT_LEVEL = LEVELS_DIR / "level_14.csv"
DEFAULT_STATS = LEVELS_DIR / "level_14_stats.asset"


ALWAYS_DIE_OVER_HOLE = True
SLIME_SPAWNS_KILL = False
MAX_CHANGE_TURN = 2
CHANGE_MAX_LENGTH = 2
GENERATE_ON_FIRST_TURN = True

ORTHOGONAL_OFFSETS = [(1, 0), (-1, 0), (0, 1), (0, -1)]  # exact order from Predator_Master.cs
DIAGONAL_OFFSETS = [(1, 1), (-1, 1), (1, -1), (-1, -1)]


class Color(IntEnum):
    RED = 0
    BLUE = 1
    PURPLE = 2
    YELLOW = 3
    NONE = 4


COLOR_LETTER = {Color.RED: "r", Color.BLUE: "b", Color.PURPLE: "pu", Color.YELLOW: "y", Color.NONE: "-"}


class CT(IntEnum):
    """Cell type, mirrors PLANT_TYPE enum."""
    HOLE = 0
    GROUND = 1
    BUSH = 2
    PLANT = 3
    SPAWN = 4
    DIAGONAL_SPAWN = 5
    EMPTY = 6  # PLANT_TYPE.Empty -- walls / not-walkable


# --------------------------------------------------------------------------
# Level parsing
# --------------------------------------------------------------------------

def parse_level_csv(path: Path) -> List[List[str]]:
    """Replicates Game_Master.Load_Level(string) exactly, including its bug
    of dropping the last two rows of the file. Returns rows indexed
    [row_from_top][col], i.e. rows[0] is the TOP row of the file.
    """
    text = path.read_text(encoding="utf-8-sig")  # utf-8-sig strips a BOM, matching StreamReader defaults
    raw_rows = text.split("\n")
    n_rows = len(raw_rows) - 1 - 1  # the exact (buggy) Game_Master.cs formula
    if n_rows <= 0:
        raise ValueError(f"{path}: not enough rows after replicating the Load_Level row-drop bug")
    n_cols = len(raw_rows[0].split(","))
    rows = []
    for i in range(n_rows):
        cols = raw_rows[i].split(",")
        cols = [c.rstrip("\r") for c in cols]
        if len(cols) != n_cols:
            raise ValueError(f"{path}: row {i} has {len(cols)} cols, expected {n_cols}")
        rows.append(cols)
    return rows  # rows[0] = top of file


def parse_stats_asset(path: Path) -> Dict[str, str]:
    """Very small line-based parser for the flat scalar fields of a
    Level_Stats .asset YAML file (Assets/Scripts/Level_Stats.cs). Only pulls
    the fields the solver needs; does not attempt the nested `conditions`
    list (see module docstring: Condition gating is not modeled).
    """
    text = path.read_text(encoding="utf-8")
    fields: Dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^  ([a-zA-Z_0-9]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key not in fields:  # keep first occurrence (top-level, not nested under conditions)
                fields[key] = val
        if line.strip() == "conditions:" or line.startswith("  conditions:"):
            break  # stop before the nested conditions list
    return fields


def parse_vec2(s: str) -> Tuple[int, int]:
    m = re.match(r"\{x:\s*(-?\d+(?:\.\d+)?),\s*y:\s*(-?\d+(?:\.\d+)?)\}", s)
    if not m:
        raise ValueError(f"could not parse Vector2 from {s!r}")
    return int(float(m.group(1))), int(float(m.group(2)))


# --------------------------------------------------------------------------
# Static (never-changing) board description, built once from the CSV.
# --------------------------------------------------------------------------

@dataclass
class StaticCell:
    base_type: CT           # what this tile always is, ignoring Plant<->Hole toggling
    fixed_color: Color       # for BUSH: its real color. For everything else non-plant: Color.RED
                              # (the "default(enum)==0" quirk -- see note #2 above)
    walkable: bool           # Node.walkable; true for everything except EMPTY, never changes


@dataclass
class Level:
    width: int
    height: int
    static_cells: Dict[Tuple[int, int], StaticCell]
    plant_cells: List[Tuple[int, int]]     # cells that start as PLANT_TYPE.Plant (the only ones that can become holes)
    plant_initial_color: Dict[Tuple[int, int], Color]
    spawn_points: List[Tuple[int, int, bool]]  # (x, y, is_diagonal), in the order the grid generator scans them
    prey_start: Tuple[int, int]
    stored_seed_start: Color
    turn_limit: int
    minimum_spawn_turn: int
    generation_limit: int          # number_of_predators
    n_generated: int                # predators_generated (per wave)
    level_name: str


TOKEN_TABLE = {
    # token -> (CT, Color or None)
    "C": (CT.EMPTY, Color.RED), "c": (CT.EMPTY, Color.RED),
    "d": (CT.GROUND, Color.RED),
    "S": (CT.SPAWN, Color.RED),
    "DS": (CT.DIAGONAL_SPAWN, Color.RED),
    "B": (CT.BUSH, Color.BLUE), "R": (CT.BUSH, Color.RED), "Y": (CT.BUSH, Color.YELLOW),
    "b": (CT.PLANT, Color.BLUE), "r": (CT.PLANT, Color.RED),
    "y": (CT.PLANT, Color.YELLOW), "pu": (CT.PLANT, Color.PURPLE),
}
UNSUPPORTED_TOKENS = {"P", "CP", "br", "rb", "by", "ry", "yb", "yr"}


def build_level(csv_path: Path, stats_path: Path) -> Level:
    rows = parse_level_csv(csv_path)  # rows[0] = top of file (highest y)
    n_rows = len(rows)
    n_cols = len(rows[0])
    stats = parse_stats_asset(stats_path)

    static_cells: Dict[Tuple[int, int], StaticCell] = {}
    plant_cells: List[Tuple[int, int]] = []
    plant_initial_color: Dict[Tuple[int, int], Color] = {}
    spawn_points: List[Tuple[int, int, bool]] = []

    # Game_Master.Load_Level stores string_grid[j, n_rows - i - 1] = column j of file-row i.
    # i.e. y = n_rows - i - 1, so file-row 0 (top) becomes the highest y.
    for i in range(n_rows):
        y = n_rows - i - 1
        for x in range(n_cols):
            token = rows[i][x]
            if token in UNSUPPORTED_TOKENS:
                raise NotImplementedError(
                    f"Level token {token!r} at csv-row {i}, col {x} is not supported by this solver "
                    f"(random-color / dual-color tiles aren't modeled). See module docstring."
                )
            if token not in TOKEN_TABLE:
                ct, color = CT.EMPTY, Color.RED  # matches build_plant_plot's final `else` fallback
            else:
                ct, color = TOKEN_TABLE[token]

            if ct == CT.PLANT:
                plant_cells.append((x, y))
                plant_initial_color[(x, y)] = color
                # Plant cells are dynamic; still register a static placeholder for walkability.
                static_cells[(x, y)] = StaticCell(CT.PLANT, Color.RED, True)
            else:
                walkable = ct != CT.EMPTY
                static_cells[(x, y)] = StaticCell(ct, color, walkable)
                if ct in (CT.SPAWN, CT.DIAGONAL_SPAWN):
                    spawn_points.append((x, y, ct == CT.DIAGONAL_SPAWN))

    # Generate_Grid's spawn point registration order is column-major (x outer, y inner);
    # our scan above is row-major top-to-bottom, so re-sort into the real order.
    spawn_points.sort(key=lambda p: (p[0], p[1]))

    prey_start = parse_vec2(stats["prey_spawn_position"])
    stored_seed_start = Color(int(stats["stored_plant_seed_type_color"]))

    return Level(
        width=n_cols, height=n_rows,
        static_cells=static_cells,
        plant_cells=plant_cells,
        plant_initial_color=plant_initial_color,
        spawn_points=spawn_points,
        prey_start=prey_start,
        stored_seed_start=stored_seed_start,
        turn_limit=int(stats["turn_limit"]),
        minimum_spawn_turn=int(stats["minimum_spawn_turn"]),
        generation_limit=int(stats["number_of_predators"]),
        n_generated=int(stats["predators_generated"]),
        level_name=stats.get("level_name", csv_path.name),
    )


# --------------------------------------------------------------------------
# Predator spawn/respawn bookkeeping (Animal_Generator.Update + slime_plot
# ready/generate) now lives on Sim._generator_step, called once per resolve_turn
# cycle -- see the State.gen_* fields and Sim._generator_step below. This has
# to be path-aware (not a precomputed, path-independent schedule) because
# Predator.Die() decrements generation_count, which can re-arm the periodic
# timer after a death -- a respawn is just that timer firing again.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Mutable per-search-state board + predator representation.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PredatorState:
    alive: bool
    pos: Tuple[int, int]
    diagonal: bool
    pending_target: Optional[Tuple[int, int]]  # decided at end of previous cycle; None on its present/idle cycle
    facing: Tuple[int, int]
    # [GROUND TRUTH, per RULES.md + turn0-4 log replay]: a predator's FIRST move
    # after any spawn/respawn targets the bunny's position at the READY turn,
    # not wherever the bunny currently is. awaiting_first_move stays True from
    # the "present" cycle until that first move's target has been computed
    # (using first_move_goal); every move after that uses the normal live
    # one-cycle-lag bunny position.
    awaiting_first_move: bool
    first_move_goal: Optional[Tuple[int, int]]


@dataclass(frozen=True)
class State:
    turn: int
    bunny: Tuple[int, int]
    bunny_facing: Tuple[int, int]
    seed: Color
    # plants: tuple aligned with level.plant_cells, each = (is_hole, color, hole_counter)
    plants: Tuple[Tuple[bool, int, int], ...]
    predators: Tuple[PredatorState, ...]
    # Animal_Generator bookkeeping. This has to live in the path-dependent State
    # (not a precomputed, path-independent schedule) because Predator.Die()
    # decrements gen_count, which can re-arm the normal periodic spawn timer --
    # i.e. respawns are just the ordinary mechanism firing again after a death,
    # not a separate special case. See RULES.md.
    gen_old_turn_count: int
    gen_count: int
    gen_readied_slimes: int
    gen_spawn_plot: int
    gen_first_turn_pending: bool  # the generate_on_first_turn one-shot flag, not yet consumed
    # per spawn point (aligned with level.spawn_points): None, or (turn_readied, bunny_pos_at_ready)
    readied: Tuple[Optional[Tuple[int, Tuple[int, int]]], ...]


class Sim:
    """Holds a Level plus precomputed lookup tables, and all the pure
    transition functions that operate on State. One Sim per level."""

    def __init__(self, level: Level, max_turn: int):
        self.level = level
        self.plant_index = {pos: i for i, pos in enumerate(level.plant_cells)}

        # scoring excludes the last row and last column (Score_and_Timer.cs quirk)
        self.scored_cells = {
            (x, y) for (x, y) in level.static_cells
            if x < level.width - 1 and y < level.height - 1
        }
        self.tie_count = 0       # incremented whenever a genuine predator-move tie is hit
        self.warn_ties = False   # set True to print each tie as it happens (see _find_closest_movement)

    # -- initial state ---------------------------------------------------
    def initial_state(self) -> State:
        plants = tuple((False, int(self.level.plant_initial_color[pos]), 0) for pos in self.level.plant_cells)
        n_spawns = len(self.level.spawn_points)
        readied: List[Optional[Tuple[int, Tuple[int, int]]]] = [None] * n_spawns
        gen_spawn_plot = 0
        gen_readied_slimes = 0
        first_turn_pending = GENERATE_ON_FIRST_TURN
        # generate_on_first_turn is a one-shot that fires on the very first
        # evaluation (turn 0), before any move -- so it's resolved here, not
        # inside resolve_turn's per-cycle tick.
        if first_turn_pending and n_spawns > 0 and self.level.generation_limit > 0:
            idx = gen_spawn_plot % n_spawns
            first_turn_pending = False
            if self.level.minimum_spawn_turn <= 0:
                readied[idx] = (0, self.level.prey_start)
                gen_readied_slimes += 1
            gen_spawn_plot = (gen_spawn_plot + 1) % n_spawns

        return State(
            turn=0,
            bunny=self.level.prey_start,
            bunny_facing=(0, 1),
            seed=self.level.stored_seed_start,
            plants=plants,
            predators=tuple(),
            gen_old_turn_count=0,
            gen_count=0,
            gen_readied_slimes=gen_readied_slimes,
            gen_spawn_plot=gen_spawn_plot,
            gen_first_turn_pending=first_turn_pending,
            readied=tuple(readied),
        )

    def _generator_step(self, s: State, turn: int, bunny_pos: Tuple[int, int]):
        """One tick of Animal_Generator.Update() + slime_plot.check_to_generate(),
        run once per resolve_turn cycle using the POST-move turn/bunny position.
        Three independent checks (not if/else), in this exact order, matching
        the C# source. Returns (new_gen_fields..., newly_present) where
        newly_present is [(spawn_idx, ready_bunny_pos), ...] for spawn points
        that become instantiated (present) this tick."""
        n_spawns = len(self.level.spawn_points)
        readied = list(s.readied)
        gen_old_turn_count = s.gen_old_turn_count
        gen_count = s.gen_count
        gen_readied_slimes = s.gen_readied_slimes
        gen_spawn_plot = s.gen_spawn_plot
        first_turn_pending = s.gen_first_turn_pending
        newly_present: List[Tuple[int, Tuple[int, int]]] = []

        if n_spawns == 0 or self.level.generation_limit == 0:
            return gen_old_turn_count, gen_count, gen_readied_slimes, gen_spawn_plot, tuple(readied), \
                first_turn_pending, newly_present

        # 1) slime_plot.check_to_generate(): readied strictly before `turn` becomes present now.
        for idx in range(n_spawns):
            r = readied[idx]
            if r is not None and turn - r[0] > 0:
                newly_present.append((idx, r[1]))
                readied[idx] = None
                gen_count += 1
                gen_readied_slimes -= 1

        # 2a) freeze once the limit is (or will be) reached
        if gen_count + gen_readied_slimes == self.level.generation_limit:
            gen_old_turn_count = turn
        # 2b) one-shot generate_on_first_turn (normally already consumed at turn 0;
        #     kept here too in case minimum_spawn_turn>0 delayed its actual readying)
        if first_turn_pending:
            if gen_count < self.level.generation_limit:
                idx = gen_spawn_plot % n_spawns
                first_turn_pending = False
                if self.level.minimum_spawn_turn <= turn:
                    readied[idx] = (turn, bunny_pos)
                    gen_readied_slimes += 1
                gen_spawn_plot = (gen_spawn_plot + 1) % n_spawns
        # 2c) normal periodic timer -- this is what actually fires a respawn,
        #     since Predator.Die() decrements gen_count and re-arms this check.
        if turn >= 1 and gen_old_turn_count <= (turn - MAX_CHANGE_TURN):
            for _ in range(self.level.n_generated):
                if gen_count < self.level.generation_limit:
                    idx = gen_spawn_plot % n_spawns
                    if self.level.minimum_spawn_turn <= turn:
                        readied[idx] = (turn, bunny_pos)
                        gen_readied_slimes += 1
                    gen_spawn_plot = (gen_spawn_plot + 1) % n_spawns
                    gen_old_turn_count = turn

        return gen_old_turn_count, gen_count, gen_readied_slimes, gen_spawn_plot, tuple(readied), \
            first_turn_pending, newly_present

    # -- cell queries ------------------------------------------------------
    def cell_type(self, s: State, pos: Tuple[int, int]) -> CT:
        idx = self.plant_index.get(pos)
        if idx is not None:
            is_hole, _color, _counter = s.plants[idx]
            return CT.HOLE if is_hole else CT.PLANT
        return self.level.static_cells[pos].base_type

    def cell_color(self, s: State, pos: Tuple[int, int]) -> Color:
        idx = self.plant_index.get(pos)
        if idx is not None:
            _is_hole, color, _counter = s.plants[idx]
            return Color(color)
        return self.level.static_cells[pos].fixed_color

    def hole_counter(self, s: State, pos: Tuple[int, int]) -> Optional[int]:
        idx = self.plant_index.get(pos)
        if idx is None:
            return None
        is_hole, _color, counter = s.plants[idx]
        return counter if is_hole else None

    def walkable_static(self, pos: Tuple[int, int]) -> bool:
        cell = self.level.static_cells.get(pos)
        return cell is not None and cell.walkable

    def in_bounds(self, pos: Tuple[int, int]) -> bool:
        x, y = pos
        return 0 <= x < self.level.width and 0 <= y < self.level.height

    def is_about_to_grow(self, s: State, pos: Tuple[int, int], context: str) -> bool:
        """Port of Predator_Master.Is_Plant_About_To_Grow. Only meaningful
        when the cell is currently a Hole; caller must check that first."""
        counter = self.hole_counter(s, pos)
        assert counter is not None
        threshold = 1 if context == "predator_turn" else CHANGE_MAX_LENGTH  # Prey_Turn branch ignores offset
        return counter >= threshold

    def check_if_not_hole(self, s: State, pos: Tuple[int, int], context: str) -> bool:
        if self.cell_type(s, pos) == CT.HOLE:
            return self.is_about_to_grow(s, pos, context)
        return True

    def check_if_fruit_in_grid(self, s: State, color: Color) -> bool:
        """Port of Animal.Check_If_Fruit_In_Grid: checks plant_type_color on
        EVERY cell, including walls/ground/spawn (whose color always
        defaults to Color.RED, since it's never explicitly assigned --
        see module docstring quirk #2)."""
        for pos in self.level.static_cells:
            if self.cell_color(s, pos) == color:
                return True
        return False

    # -- win condition -----------------------------------------------------
    def check_win(self, s: State) -> bool:
        counts = [0, 0, 0, 0]  # red, blue, purple, yellow
        holes = 0
        total = 0
        for pos in self.scored_cells:
            ct = self.cell_type(s, pos)
            if ct == CT.HOLE:
                holes += 1
                total += 1
            elif ct == CT.PLANT:
                counts[int(self.cell_color(s, pos))] += 1
                total += 1
        if total == 0:
            return False
        return holes == 0 and max(counts) == total

    # -- search heuristic ----------------------------------------------------
    @staticmethod
    def _mst_weight(points: List[Tuple[int, int]]) -> int:
        """Prim's MST over Manhattan distances. The shortest walk visiting a
        set of points starting from points[0] is always >= this MST's total
        weight (removing one edge from any Hamiltonian path gives a spanning
        tree, and MST is the lightest spanning tree) -- a standard admissible
        TSP-path lower bound. Manhattan distance is itself always <= true
        grid-walking distance, so this stays admissible even though it
        ignores walls/other obstacles."""
        if len(points) <= 1:
            return 0
        in_tree = [False] * len(points)
        dist = [10 ** 9] * len(points)
        dist[0] = 0
        total = 0
        for _ in range(len(points)):
            u = min((i for i in range(len(points)) if not in_tree[i]), key=lambda i: dist[i])
            in_tree[u] = True
            total += dist[u]
            for v in range(len(points)):
                if not in_tree[v]:
                    d = abs(points[u][0] - points[v][0]) + abs(points[u][1] - points[v][1])
                    if d < dist[v]:
                        dist[v] = d
        return total

    def min_blob_heuristic(self, s: State) -> int:
        """Scalar wrapper around _heuristic_detail for callers (the exact
        A* solver, monte_carlo_solve) that just need the admissible bound."""
        h, _raw, _blobs = self._heuristic_detail(s)
        return h

    def _heuristic_detail(self, s: State) -> Tuple[int, int, int]:
        """Returns (h, raw, blobs): h is the admissible lower bound on
        remaining MOVES (see below); raw is the same computation WITHOUT the
        final-wait floor; blobs is the number of distinct off-target-color
        regions still needing a harvest. raw turned out to be a BAD beam tie-
        break (harvesting the last blob makes raw temporarily worse, since a
        fresh hole_wait appears, even though true remaining cost is
        unchanged -- it starved out the branches that actually commit to
        finishing). blobs doesn't have that problem: it strictly decreases
        the moment a blob is actually harvested, so beam_search_solve uses it
        (not raw) as the tie-break. Combines two independent lower bounds and
        takes the max (still
        admissible, tighter than either alone):
        independent lower bounds and taking the max (still admissible,
        tighter than either alone):

        (1) Only one harvest is allowed per dwell (the dwell right after
            each move, plus the initial one before any move), so clearing B
            distinct off-target-color blobs needs at least B dwells, i.e.
            at least B-1 more moves.
        (2) The bunny must physically walk to at least one cell of every
            remaining blob; the shortest such tour is lower-bounded by the
            MST over {bunny position} + {one representative cell per blob}
            using Manhattan distance (see _mst_weight).

        We don't know which color the level will end up unified to, so take
        the minimum over each candidate target color -- that keeps this a
        valid lower bound no matter which color the true solution picks.

        (3) check_win() requires ZERO active Hole cells, regardless of what
            color they'll regrow as, and growth only advances one step per
            move (never faster) -- so if any hole still has counter=0 it
            takes at least 2 more moves before it can vanish, and counter=1
            takes at least 1 more. This is what actually gates "0 blobs left
            but board not yet won" states, which otherwise look identical to
            a real win to bounds (1)/(2) alone."""
        hole_wait = self._hole_wait(s)
        best = None
        for target in (Color.RED, Color.BLUE, Color.PURPLE, Color.YELLOW):
            candidate = self._heuristic_for_target(s, target, hole_wait)
            if best is None or candidate[0] < best[0]:
                best = candidate
        h, raw, blobs_best = best or (0, 0, 0)
        return max(0, h), max(0, raw), blobs_best

    def _hole_wait(self, s: State) -> int:
        hole_wait = 0
        for pos in self.level.plant_cells:
            counter = self.hole_counter(s, pos)
            if counter is not None:
                hole_wait = max(hole_wait, CHANGE_MAX_LENGTH - counter)
        return hole_wait

    def _heuristic_for_target(self, s: State, target: Color, hole_wait: int) -> Tuple[int, int, int]:
        """(h, raw, blobs) computed against ONE specific target color (see
        _heuristic_detail for what each means)."""
        seen = set()
        reps: List[Tuple[int, int]] = [s.bunny]
        for pos in self.level.plant_cells:
            if pos in seen:
                continue
            if self.cell_type(s, pos) != CT.PLANT or self.cell_color(s, pos) == target:
                continue
            reps.append(pos)
            stack = [pos]
            seen.add(pos)
            while stack:
                px, py = stack.pop()
                for npos in ((px - 1, py), (px, py + 1), (px + 1, py), (px, py - 1)):
                    if npos in seen or npos not in self.plant_index:
                        continue
                    if self.cell_type(s, npos) != CT.PLANT or self.cell_color(s, npos) == target:
                        continue
                    seen.add(npos)
                    stack.append(npos)
        blobs = len(reps) - 1
        raw_c = max(blobs - 1, self._mst_weight(reps), hole_wait)
        # Even in the best case (already adjacent, harvest for free right
        # now), that harvest turns the last blob into a Hole, and
        # check_win() requires zero active holes -- so CHANGE_MAX_LENGTH
        # more moves are unavoidable whenever any blob remains at all.
        # Without this, a "1 blob left, standing right next to it" state
        # scores the same (h=0) as an actual win, and committing the
        # harvest makes h go UP (once that hole is active), which starved
        # beam search of any incentive to ever pull the trigger.
        final_wait = CHANGE_MAX_LENGTH if blobs > 0 else 0
        h_c = max(raw_c, final_wait)
        return max(0, h_c), max(0, raw_c), blobs

    def _heuristic_committed(self, s: State) -> Tuple[int, int, int]:
        """Like _heuristic_detail, but for beam-ranking use: once a seed is
        held, ANY harvest from here to the end will regrow as that seed's
        color (until the next harvest changes it) -- so the real "cheapest
        remaining color" isn't a free choice, it's whatever's already held.
        Evaluating the free min-over-colors bound here let the beam thrash
        between different target colors turn to turn instead of committing,
        since switching targets looks just as cheap as staying the course.
        Only falls back to the free choice when no seed is held (nothing
        committed yet)."""
        hole_wait = self._hole_wait(s)
        if s.seed != Color.NONE:
            return self._heuristic_for_target(s, s.seed, hole_wait)
        best = None
        for target in (Color.RED, Color.BLUE, Color.PURPLE, Color.YELLOW):
            candidate = self._heuristic_for_target(s, target, hole_wait)
            if best is None or candidate[0] < best[0]:
                best = candidate
        return best or (0, 0, 0)

    def _approach_and_safety(self, s: State) -> float:
        """Beam-ranking-only tie-break (not used by the admissible heuristic
        or exact solve() -- kept separate so as not to slow those down).
        Added 2026-07-13 after Level_16.csv/level_17_stats got permanently
        stuck at blobs=1: a pure distance-from-predator tie-break (danger())
        always outranks any state that hasn't yet reduced h/blobs, even one
        that's one necessary step closer to a multi-turn approach the real
        solve requires -- so the beam only ever explored "stay safe and
        idle" branches and never accumulated the approach sequence needed
        to reach the last blob (which real gameplay also requires baiting
        predators onto holes to clear, per the user 2026-07-13). Returns a
        single combined score (lower = better): distance to the nearest
        cell of the CHEAPEST remaining off-target-color blob (reward
        closing in on the work) minus distance to the nearest alive
        predator (still reward safety, just no longer at the total expense
        of progress)."""
        best_blobs = None
        best_reps: List[Tuple[int, int]] = []
        for target in (Color.RED, Color.BLUE, Color.PURPLE, Color.YELLOW):
            seen = set()
            reps: List[Tuple[int, int]] = []
            for pos in self.level.plant_cells:
                if pos in seen:
                    continue
                if self.cell_type(s, pos) != CT.PLANT or self.cell_color(s, pos) == target:
                    continue
                reps.append(pos)
                stack = [pos]
                seen.add(pos)
                while stack:
                    px, py = stack.pop()
                    for npos in ((px - 1, py), (px, py + 1), (px + 1, py), (px, py - 1)):
                        if npos in seen or npos not in self.plant_index:
                            continue
                        if self.cell_type(s, npos) != CT.PLANT or self.cell_color(s, npos) == target:
                            continue
                        seen.add(npos)
                        stack.append(npos)
            if best_blobs is None or len(reps) < best_blobs:
                best_blobs = len(reps)
                best_reps = reps
        nearest_work = 0 if not best_reps else min(
            abs(p[0] - s.bunny[0]) + abs(p[1] - s.bunny[1]) for p in best_reps)
        alive = [p for p in s.predators if p.alive]
        safety = min((abs(p.pos[0] - s.bunny[0]) + abs(p.pos[1] - s.bunny[1]) for p in alive), default=99)
        return nearest_work - safety

    # -- harvesting ----------------------------------------------------------
    def apply_harvest(self, s: State, target: Tuple[int, int]) -> Optional[State]:
        if self.cell_type(s, target) != CT.PLANT:
            return None  # not currently a live plant (hole/bush/etc.) -> no-op, not worth searching
        old_color = self.cell_color(s, target)

        # flood fill: 4-connected PLANT cells matching old_color
        plants = list(s.plants)
        seen = set()
        stack = [target]
        blob = []
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            idx = self.plant_index.get(p)
            if idx is None:
                continue
            is_hole, color, _counter = plants[idx]
            if is_hole or Color(color) != old_color:
                continue
            blob.append(idx)
            px, py = p
            for npos in ((px - 1, py), (px, py + 1), (px + 1, py), (px, py - 1)):
                if npos not in seen:
                    stack.append(npos)

        # [RETRACTED 2026-07-08: a "multi-cell blob regrows one turn later"
        # theory was tried here based on one Level_14 log, but three
        # independent blobs (two 2-cell, one 3-cell) in a Level_16 log all
        # regrew on the plain change_max_length schedule with no extra
        # delay -- the original anomaly was most likely a data problem in
        # that Level_14 log, not a real game rule. Regrowth timing does NOT
        # depend on blob size; every hole (any blob size) follows the same
        # schedule below.]
        new_color = s.seed if s.seed != Color.NONE else old_color
        for idx in blob:
            plants[idx] = (True, int(new_color), 0)
        s2 = replace(s, plants=tuple(plants))

        # Prey.Harvest(): stored seed becomes the just-harvested color, then
        # immediately clears back to None if that color no longer exists
        # anywhere on the board (subject to the Red-default quirk above).
        new_seed = old_color
        if not self.check_if_fruit_in_grid(s2, old_color):
            new_seed = Color.NONE
        return replace(s2, seed=new_seed)

    # -- predator pathing ----------------------------------------------------
    # GetOrthogonalNeighbours' exact scan order (Grid_Generator.cs): Left, Down, Up, Right.
    _ORTHO_NEIGHBOR_ORDER = [(-1, 0), (0, -1), (0, 1), (1, 0)]

    def _environmental_cost(self, s: State, pos: Tuple[int, int], context: str, taken) -> int:
        """Pathfinding.cs Get_Environmental_Cost -- only ever added to the
        hCost of the start node's direct neighbors."""
        if self.cell_type(s, pos) == CT.HOLE:
            return 0 if self.is_about_to_grow(s, pos, context) else 1000
        return 100 if pos in taken else 0

    def astar_first_step(self, s: State, start: Tuple[int, int], target: Tuple[int, int],
                          context: str, taken) -> Optional[Tuple[int, int]]:
        """Port of Pathfinding.Find_Path + Retrace_Path, returning just the
        first step (grid_generator.path[0]) or None if no path exists."""
        if start == target:
            return None

        class Node:
            __slots__ = ("g", "h", "parent")

            def __init__(self):
                self.g = 0
                self.h = 0
                self.parent = None

            @property
            def f(self):
                return self.g + self.h

        nodes: Dict[Tuple[int, int], Node] = {}

        def get(pos):
            n = nodes.get(pos)
            if n is None:
                n = Node()
                nodes[pos] = n
            return n

        open_list: List[Tuple[int, int]] = [start]
        open_set = {start}
        closed = set()
        get(start)  # ensure it exists (g=h=0, matching the C# default(int) node fields)

        while open_list:
            current = open_list[0]
            current_node = get(current)
            for cand in open_list[1:]:
                cnode = get(cand)
                if cnode.f < current_node.f or (cnode.f == current_node.f and cnode.h < current_node.h):
                    current, current_node = cand, cnode
            open_list.remove(current)
            open_set.discard(current)
            closed.add(current)

            if current == target:
                path = []
                c = current
                while c != start:
                    path.append(c)
                    c = nodes[c].parent
                path.reverse()
                return path[0] if path else None

            cx, cy = current
            for dx, dy in self._ORTHO_NEIGHBOR_ORDER:
                npos = (cx + dx, cy + dy)
                if not self.in_bounds(npos) or not self.walkable_static(npos):
                    continue
                if npos in closed:
                    continue
                new_g = current_node.g + 1  # Get_Distance is always 1 for orthogonal-adjacent cells
                nnode = get(npos)
                if new_g < nnode.g or npos not in open_set:
                    nnode.g = new_g
                    nnode.h = abs(npos[0] - target[0]) + abs(npos[1] - target[1])
                    if current == start:
                        nnode.h += self._environmental_cost(s, npos, context, taken)
                    nnode.parent = current
                    if npos not in open_set:
                        open_list.append(npos)
                        open_set.add(npos)
        return None  # no path found

    def generate_move(self, s: State, pred_pos: Tuple[int, int], offsets, context: str,
                       bunny_pos: Tuple[int, int], taken, ignore_holes: bool = False) -> Tuple[int, int]:
        """Port of Predator_Master.Generate_Move, simplified per RULES.md
        (ground-truth, log-validated): restrict to safe (non-deadly-hole)
        neighbors not already claimed by another predator this cycle, then
        pick the one closest to the bunny by squared distance, ties broken
        by neighbor order. No facing-direction refinement -- confirmed
        against real logs that the extra "facing_positions" tier from the
        raw Predator_Master.cs reading isn't part of the actual behavior.
        Tie-breaking otherwise uses stable natural offset order rather than
        UnityEngine.Random.Shuffle -- see module docstring note #7."""
        px, py = pred_pos
        possible, not_taken, safe, not_taken_safe = [], [], [], []
        for ox, oy in offsets:
            pos = (px + ox, py + oy)
            if not self.in_bounds(pos) or not self.walkable_static(pos):
                continue
            is_not_hole = self.check_if_not_hole(s, pos, context)
            is_not_taken = pos not in taken
            possible.append(pos)
            if is_not_taken:
                not_taken.append(pos)
            if is_not_hole:
                safe.append(pos)
                if is_not_taken:
                    not_taken_safe.append(pos)

        if ignore_holes:
            pool = not_taken if not_taken else possible
        else:
            pool = not_taken_safe or safe or possible

        if not pool:
            # Cornered with literally no in-bounds/walkable neighbor at all;
            # shouldn't happen on a bordered board, but guard defensively.
            return pred_pos

        return self._find_closest_movement(pool, pred_pos, bunny_pos)

    def _find_closest_movement(self, pool, pred_pos, bunny_pos) -> Tuple[int, int]:
        """Pick the pool candidate closest to bunny_pos (squared-Euclidean).
        Ties break by neighbor order (pool is already built in that order) --
        confirmed against real logs: a facing-direction "refinement" is NOT
        part of the real tie-break (see RULES.md and the turn0-4 log replay,
        where the slime's first move only matches plain neighbor-order
        tie-breaking, not a facing-based rule)."""
        bx, by = bunny_pos
        dists = {p: (bx - p[0]) ** 2 + (by - p[1]) ** 2 for p in pool}
        min_d = min(dists.values())
        tied = [p for p in pool if dists[p] == min_d]
        if len(tied) > 1:
            self.tie_count += 1
            if self.warn_ties:
                print(f"    [warning] genuine predator move tie at {pred_pos} among {tied}; "
                      f"real game breaks this with UnityEngine.Random -- see docstring note #7", file=sys.stderr)
        return tied[0]

    def compute_predator_target(self, s: State, pred: PredatorState, context: str,
                                 bunny_pos: Tuple[int, int], taken) -> Tuple[int, int]:
        """Port of Predator_Master.Generate_Orthogonal_Move / Generate_Diagonal_Move,
        as invoked by Update_Target_Position. Diagonal predators never use A*
        (Generate_Diagonal_Move goes straight to Generate_Move)."""
        if pred.diagonal:
            return self.generate_move(s, pred.pos, DIAGONAL_OFFSETS, context, bunny_pos, taken)

        step = self.astar_first_step(s, pred.pos, bunny_pos, context, taken)
        if step is None:
            candidate = self.generate_move(s, pred.pos, ORTHOGONAL_OFFSETS, context, bunny_pos, taken)
        else:
            candidate = step
        if self.cell_type(s, candidate) == CT.HOLE and not self.is_about_to_grow(s, candidate, context):
            candidate = self.generate_move(s, pred.pos, ORTHOGONAL_OFFSETS, context, bunny_pos, taken)
        return candidate

    def recompute_target_if_now_hole(self, s: State, pred: PredatorState,
                                      bunny_pos: Tuple[int, int]) -> PredatorState:
        """Port of Update_Target_Position's Prey_Turn branch, invoked via
        Game_Master.Upate_All_Enemies_Target_Positions() after every harvest
        action (player_master.harvest_location). Always uses the orthogonal
        A* path regardless of the predator's own diagonal flag -- see
        module docstring note (hardcoded Generate_Orthogonal_Move call)."""
        if pred.pending_target is None:
            return pred
        # NOTE: uses the lenient "predator_turn" (about-to-grow, threshold=1)
        # check here rather than a literal "prey_turn" (threshold=2) port.
        # Real log data (2026-07-08, turn13->14) showed a pending_target with
        # counter=1 was NOT rerouted by this recompute -- only counter=-1
        # (freshly created this same harvest, genuinely fatal) triggers a
        # reroute (see turn10->11). The flat strict-threshold literal port
        # contradicted the turn13->14 case; this lenient threshold matches
        # both observed cases.
        if self.check_if_not_hole(s, pred.pending_target, "predator_turn"):
            return pred
        step = self.astar_first_step(s, pred.pos, bunny_pos, "prey_turn", set())
        if step is None:
            new_target = self.generate_move(s, pred.pos, ORTHOGONAL_OFFSETS, "prey_turn", bunny_pos, set())
        else:
            new_target = step
        if self.cell_type(s, new_target) == CT.HOLE and not self.is_about_to_grow(s, new_target, "predator_turn"):
            new_target = self.generate_move(s, pred.pos, ORTHOGONAL_OFFSETS, "prey_turn", bunny_pos, set())
        return replace(pred, pending_target=new_target)

    # -- full turn resolution ------------------------------------------------
    DIRS = {"U": (0, 1), "D": (0, -1), "L": (-1, 0), "R": (1, 0)}

    def _kill_predators_standing_on_holes(self, working: State) -> State:
        """Removes any alive predator whose current tile is (now) a Hole,
        decrementing gen_count for each (Predator.Die() does this in the real
        game, which is what re-arms the periodic spawn timer for a respawn --
        see RULES.md). Used both right after a harvest (a hole opening under a
        stationary predator) and after predator movement (forced into a hole)."""
        preds = list(working.predators)
        gen_count = working.gen_count
        changed = False
        for i, p in enumerate(preds):
            if p.alive and self.cell_type(working, p.pos) == CT.HOLE:
                preds[i] = PredatorState(False, p.pos, p.diagonal, None, p.facing, False, None)
                gen_count -= 1
                changed = True
        if not changed:
            return working
        return replace(working, predators=tuple(preds), gen_count=gen_count)

    def resolve_turn(self, s: State, harvest_dir: Optional[str], move_dir: str):
        """One full player turn: optional harvest, then a mandatory move,
        then predator movement, spawning, and plant growth, in the exact
        phase order the game uses. Returns:
          ('WIN', state, actions)   if the harvest alone completed the level
          ('MOVE', state, actions)  if the turn resolved to a live, ongoing state
          None                      if this (harvest_dir, move_dir) combo is illegal
                                     or provably lethal (excluded, not explored)
        """
        working = s
        actions = []

        if harvest_dir is not None:
            dx, dy = self.DIRS[harvest_dir]
            target = (working.bunny[0] + dx, working.bunny[1] + dy)
            if not self.in_bounds(target) or self.cell_type(working, target) != CT.PLANT:
                return None  # nothing useful to harvest there
            working = self.apply_harvest(working, target)
            actions.append(f"harvest {harvest_dir}")
            if self.check_win(working):
                return ('WIN', working, actions)

            # [LIKELY, RULES.md]: if the flood-fill chain reaches the bunny's
            # own tile, the bunny falls in and dies.
            if self.cell_type(working, working.bunny) == CT.HOLE:
                return None

            # [GROUND TRUTH, RULES.md]: a hole opening under a STATIONARY
            # predator (this harvest reached its tile) kills it immediately,
            # before it gets a chance to move.
            working = self._kill_predators_standing_on_holes(working)

            # Port of Game_Master.Upate_All_Enemies_Target_Positions(), invoked
            # from player_master.harvest_location() after every harvest: give
            # each surviving predator a chance to re-route away from a
            # pending_target that's still a genuinely dangerous Hole. Uses the
            # lenient "about to grow" threshold (not a flat strict one) -- see
            # the note in recompute_target_if_now_hole for the log evidence.
            new_preds = tuple(
                self.recompute_target_if_now_hole(working, p, working.bunny) if p.alive else p
                for p in working.predators
            )
            working = replace(working, predators=new_preds)

        # -- the move ---------------------------------------------------------
        dx, dy = self.DIRS[move_dir]
        target = (working.bunny[0] + dx, working.bunny[1] + dy)
        if not self.in_bounds(target):
            return None
        ct = self.cell_type(working, target)
        if ct == CT.EMPTY:
            return None  # can't move into a wall
        if ct == CT.HOLE:
            return None  # always_die_over_hole -> instant death, never a valid move
        if any(p.alive and p.pos == target for p in working.predators):
            return None  # walking onto an occupied tile -> death
        actions.append(f"move {move_dir}")

        new_turn = working.turn + 1
        preds = list(working.predators)
        for i, p in enumerate(preds):
            if not p.alive or p.pending_target is None:
                continue
            new_pos = p.pending_target
            new_facing = (new_pos[0] - p.pos[0], new_pos[1] - p.pos[1])
            preds[i] = PredatorState(True, new_pos, p.diagonal, None, new_facing, p.awaiting_first_move,
                                      p.first_move_goal)

        if any(p.alive and p.pos == target for p in preds):
            return None  # a predator moved onto the bunny's new tile -> death

        working = replace(working, turn=new_turn, bunny=target, bunny_facing=(dx, dy), predators=tuple(preds))

        # -- generator tick: present-transitions + ready/periodic ---------------
        (gen_old_turn_count, gen_count, gen_readied_slimes, gen_spawn_plot, readied,
         gen_first_turn_pending, newly_present) = self._generator_step(working, new_turn, working.bunny)

        preds2 = list(working.predators)
        for spawn_idx, ready_pos in newly_present:
            x, y, is_diag = self.level.spawn_points[spawn_idx]
            # [LIKELY per developer, RULES.md]: if the bunny was on the spawn
            # tile back on the READY turn, it dies when the slime instantiates
            # there now, regardless of where the bunny is at this instant.
            if ready_pos == (x, y):
                return None
            preds2.append(PredatorState(True, (x, y), is_diag, None, (0, 1), True, ready_pos))
        working = replace(working, predators=tuple(preds2), gen_old_turn_count=gen_old_turn_count,
                           gen_count=gen_count, gen_readied_slimes=gen_readied_slimes,
                           gen_spawn_plot=gen_spawn_plot, gen_first_turn_pending=gen_first_turn_pending,
                           readied=readied)

        # a slime spawning directly onto the bunny's (new) tile is also lethal
        if any(p.alive and p.pos == working.bunny for p in working.predators):
            return None

        # -- plant growth phase -------------------------------------------------
        # A hole's counter increments every growth phase starting the SAME
        # cycle it's created (no activation delay) -- confirmed 2026-07-09
        # against a fixed-logging-bug log (4 independent blobs, sizes
        # 1/2/2/5, all regrown exactly 1 turn after creation). An earlier
        # "-1 sentinel, activate next cycle" model (regrowth at T_h+2) was
        # built from logs later found to have a plant-growth logging bug
        # that delayed the displayed regrowth turn by one; retracted.
        plants = list(working.plants)
        for i, (is_hole, color, counter) in enumerate(plants):
            if is_hole:
                counter += 1
                plants[i] = (False, color, 0) if counter >= CHANGE_MAX_LENGTH else (True, color, counter)
        working = replace(working, plants=tuple(plants))

        # [GROUND TRUTH, RULES.md + real-log correction 2026-07-08]: a predator
        # forced onto a hole dies -- but only checked AFTER growth resolves,
        # not before. A hole with counter=1 ("about to grow" for pathing
        # purposes) actually flips to Plant in THIS SAME growth phase, and a
        # real playthrough confirmed the predator survives landing on one
        # (turn13->14: predator moved onto a hole with counter=1, which
        # regrew to Plant same cycle, and the predator lived standing on it).
        # Checking pre-growth (the original design) killed it wrongly.
        working = self._kill_predators_standing_on_holes(working)

        # -- compute each alive predator's target for the NEXT cycle ------------
        # A predator awaiting its first move-after-spawn targets the bunny's
        # position at ITS ready turn, not wherever the bunny is now (see
        # PredatorState.awaiting_first_move docstring; validated against logs).
        taken: set = set()
        preds3 = list(working.predators)
        for i, p in enumerate(preds3):
            if not p.alive:
                continue
            goal = p.first_move_goal if p.awaiting_first_move else working.bunny
            tgt = self.compute_predator_target(working, p, "predator_turn", goal, taken)
            taken.add(tgt)
            preds3[i] = PredatorState(True, p.pos, p.diagonal, tgt, p.facing, False, None)
        working = replace(working, predators=tuple(preds3))

        # A board can also become fully unified PASSIVELY when the growth
        # phase above regrows the last active Hole, with no harvest this
        # turn at all. The real game's Game_Master.Update() checks
        # score>=100 every single frame (independent of Prey.Harvest()), so
        # this is a genuine win the instant it happens, not just something
        # noticed on the next harvest attempt.
        if self.check_win(working):
            return ('WIN', working, actions)

        return ('MOVE', working, actions)


# --------------------------------------------------------------------------
# Board trace, formatted to match Game_Master.Log_Board_State() exactly
# (including its quirk of emitting nothing at all for Empty/wall cells) so a
# real playthrough's level_log_turnN.txt files can be diffed against this.
# --------------------------------------------------------------------------

def format_board(sim: Sim, s: State) -> str:
    lines = [f"Turn {s.turn}"]
    height = sim.level.height
    for y in range(height - 1, -1, -1):
        row = ""
        for x in range(sim.level.width):
            pos = (x, y)
            if pos == s.bunny:
                row += "bunny:"
            for p in s.predators:
                if p.alive and p.pos == pos:
                    row += "Slime:"
            ct = sim.cell_type(s, pos)
            color = sim.cell_color(s, pos)
            letter = COLOR_LETTER[color]
            if ct == CT.HOLE:
                row += "h,"
            elif ct == CT.GROUND:
                row += "g,"
            elif ct == CT.BUSH:
                row += f"b:{letter},"
            elif ct == CT.PLANT:
                row += f"p:{letter},"
            elif ct == CT.SPAWN:
                row += "s,"
            elif ct == CT.DIAGONAL_SPAWN:
                row += "ds,"
            # CT.EMPTY: Log_Board_State has no case for it -- emits nothing.
        lines.append(row)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# BFS solver: minimum number of MOVES (harvesting is free) to reach the win
# condition. BFS explores states in strictly non-decreasing turn order, so
# the first win found is provably minimal.
# --------------------------------------------------------------------------

def state_key(s: State):
    return (s.bunny, s.bunny_facing, int(s.seed), s.plants,
            tuple((p.alive, p.pos, p.pending_target, p.facing, p.awaiting_first_move, p.first_move_goal)
                  for p in s.predators),
            s.gen_old_turn_count, s.gen_count, s.gen_readied_slimes, s.gen_spawn_plot,
            s.gen_first_turn_pending, s.readied)


def _reconstruct(key, parent, state_by_key):
    actions_rev = []
    while parent[key] is not None:
        pkey, actions = parent[key]
        actions_rev.append(actions)
        key = pkey
    out = []
    for actions in reversed(actions_rev):
        out.extend(actions)
    return out


def beam_search_solve(sim: Sim, beam_width: int = 3000, verbose: bool = False):
    """Fast, NON-exhaustive search: at each turn depth, keep only the
    beam_width states with the lowest Sim.min_blob_heuristic, expand all of
    them, and repeat. Unlike a single greedy rollout (see
    monte_carlo_solve), retaining many candidates per depth means one bad
    heuristic dip on some candidates doesn't strand the whole search --
    other candidates in the beam carry on. Still not exhaustive, so a
    found solution is not proven minimal, but in practice tracks much
    closer to the true optimum than random/greedy rollouts, and returns
    the first win found among the CURRENT beam once it turns up (i.e. no
    win existed among any smaller-or-equal turn count reachable through
    the beam's own candidates -- not a formal proof against the full
    state space, since off-beam states were discarded).
    """
    all_harvest = (None, "U", "D", "L", "R")
    all_move = ("U", "D", "L", "R")
    beam: List[Tuple[State, List[str]]] = [(sim.initial_state(), [])]

    for depth in range(sim.level.turn_limit):
        candidates = []
        for s, actions in beam:
            for hd in all_harvest:
                for md in all_move:
                    result = sim.resolve_turn(s, hd, md)
                    if result is None:
                        continue
                    rkind, new_s, act = result
                    if rkind == "WIN":
                        if verbose:
                            print(f"[beam] found a win at turn {new_s.turn} (depth step {depth + 1})",
                                  file=sys.stderr, flush=True)
                        return new_s.turn, actions + act
                    # h alone is the right primary key (floored, doesn't
                    # penalize committing the last harvest -- see
                    # _heuristic_detail). blobs is the tie-break: it strictly
                    # decreases the moment a blob is actually harvested
                    # (unlike raw, which temporarily gets worse from the
                    # fresh hole_wait and was found to starve committed
                    # branches out of the beam entirely), so it rewards
                    # actually finishing over sitting adjacent-but-idle.
                    # Tried _heuristic_committed (evaluate only against the
                    # currently-held seed's color) expecting it to reduce
                    # target-color thrashing -- measured WORSE (blobs stuck
                    # at 1 for all 28 depths, vs free-choice reaching 0).
                    # Reverted: the free min-over-colors choice actually
                    # navigates better in practice, even though it doesn't
                    # mirror the real seed-commitment mechanic.
                    h, _raw, blobs = sim._heuristic_detail(new_s)
                    # alive-predator count: reward a successful hole-bait
                    # kill directly, since h/blobs can't see it (2026-07-13).
                    # _approach_and_safety replaces a pure danger()
                    # tie-break, which always outranked any state that
                    # hadn't yet reduced h/blobs -- even a state one
                    # necessary step closer to a multi-turn approach --
                    # starving out every branch that wasn't immediately
                    # safe-and-idle.
                    alive_count = sum(1 for p in new_s.predators if p.alive)
                    candidates.append(((h, blobs, alive_count, sim._approach_and_safety(new_s)),
                                        new_s, actions + act))
        if not candidates:
            if verbose:
                print(f"[beam] dead end at depth {depth}: no legal actions from any beam member", file=sys.stderr)
            return None, None
        candidates.sort(key=lambda c: c[0])
        seen = set()
        deduped = []
        for h, s2, actions2 in candidates:
            k = state_key(s2)
            if k in seen:
                continue
            seen.add(k)
            deduped.append((h, s2, actions2))
        beam = [(s2, actions2) for _h, s2, actions2 in deduped[:beam_width]]
        if verbose:
            print(f"[beam] depth={depth + 1} beam_size={len(beam)} best_h={deduped[0][0]}",
                  file=sys.stderr, flush=True)
    return None, None


def monte_carlo_solve(sim: Sim, iterations: int = 500, epsilon: float = 0.15,
                       seed: Optional[int] = None, verbose: bool = False):
    """Fast, NON-exhaustive search: repeated rollouts from the start, at each
    step epsilon-greedily picking among the (harvest_dir, move_dir) options
    whose resulting state has the lowest Sim.min_blob_heuristic (same
    heuristic A* uses), keeping the shortest winning sequence found across
    all rollouts. This does not prove optimality -- unlike solve(), it can
    return more turns than truly necessary -- but finds *a* valid, correct
    winning sequence in seconds rather than an exhaustive proof in
    (potentially) hours. Intended for quickly getting something to verify
    against a real playthrough while an exact solve (if wanted) runs
    separately.
    """
    rng = random.Random(seed)
    all_harvest = (None, "U", "D", "L", "R")
    all_move = ("U", "D", "L", "R")
    best: Optional[Tuple[int, List[str]]] = None

    for it in range(iterations):
        s = sim.initial_state()
        actions: List[str] = []
        won = False
        while s.turn < sim.level.turn_limit:
            options = []
            for hd in all_harvest:
                won_here = False
                for md in all_move:
                    result = sim.resolve_turn(s, hd, md)
                    if result is None:
                        continue
                    rkind, new_s, act = result
                    if rkind == "WIN":
                        options.append((-1, s.turn, "WIN", None, act))
                        won_here = True
                        break  # every md gives the same WIN result for this hd
                    options.append((sim.min_blob_heuristic(new_s), new_s.turn, "MOVE", new_s, act))
                if won_here:
                    break
            if not options:
                break  # cornered with no legal action at all (shouldn't happen on this board)
            options.sort(key=lambda o: o[0])
            if rng.random() < epsilon:
                choice = rng.choice(options)
            else:
                best_h = options[0][0]
                choice = rng.choice([o for o in options if o[0] == best_h])
            _h, turn_here, rkind, new_s, act = choice
            actions.extend(act)
            if rkind == "WIN":
                won = True
                final_turns = turn_here
                break
            s = new_s

        if won and (best is None or final_turns < best[0]):
            best = (final_turns, actions)
            if verbose:
                print(f"[monte_carlo] rollout {it}: found a {final_turns}-turn solution", file=sys.stderr, flush=True)
        if verbose and (it + 1) % 50 == 0:
            print(f"[monte_carlo] {it + 1}/{iterations} rollouts done, "
                  f"best so far: {best[0] if best else 'none'}", file=sys.stderr, flush=True)

    if best is None:
        return None, None
    return best


def solve(sim: Sim, verbose: bool = False):
    """A* over (harvest_dir, move_dir) turns, g = turn count (every move
    costs 1, harvesting is free), h = Sim.min_blob_heuristic (admissible).

    A "win" is a side effect of a free harvest, so it doesn't have its own
    move-cost edge -- it's reachable at cost g(s) from whatever state s
    produced it. To keep A*'s optimality guarantee (which requires popping
    the goal itself in non-decreasing f order, not just noticing it in
    passing) we push a WIN entry onto the same priority queue at f=g(s)+0
    rather than returning as soon as one is found, and only return once such
    an entry is actually popped as the minimum.

    The heuristic is admissible but not proven consistent (see docstring in
    min_blob_heuristic), so entries are reopened via a best_g map instead of
    a one-shot visited set.
    """
    import heapq

    start = sim.initial_state()
    start_key = state_key(start)
    state_by_key: Dict[object, State] = {start_key: start}
    best_g: Dict[object, int] = {start_key: 0}
    parent: Dict[object, Optional[Tuple[object, List[str]]]] = {start_key: None}

    counter = itertools.count()  # heap tie-breaker so State/tuples are never compared
    heap = [(sim.min_blob_heuristic(start), next(counter), "STATE", start_key)]
    nodes_expanded = 0

    while heap:
        f, _, kind, payload = heapq.heappop(heap)
        if kind == "WIN":
            g, actions = payload
            if verbose:
                print(f"[solve] explored {nodes_expanded} states, visited={len(state_by_key)}",
                      file=sys.stderr, flush=True)
            return g, actions

        key = payload
        s = state_by_key[key]
        g = s.turn
        if g > best_g.get(key, g):
            continue  # stale heap entry; a cheaper path to this state was already found
        if g >= sim.level.turn_limit:
            continue  # out of turns; game would already be over

        nodes_expanded += 1
        if verbose and nodes_expanded % 2000 == 0:
            print(f"[solve] expanded={nodes_expanded} visited={len(state_by_key)} "
                  f"heap={len(heap)} at turn={g} f={f}", file=sys.stderr, flush=True)

        for harvest_dir in (None, "U", "D", "L", "R"):
            for move_dir in ("U", "D", "L", "R"):
                result = sim.resolve_turn(s, harvest_dir, move_dir)
                if result is None:
                    continue
                rkind, new_s, actions = result
                if rkind == "WIN":
                    win_actions = _reconstruct(key, parent, state_by_key) + actions
                    heapq.heappush(heap, (g, next(counter), "WIN", (g, win_actions)))
                    continue
                nkey = state_key(new_s)
                new_g = new_s.turn
                if new_g < best_g.get(nkey, new_g + 1):
                    best_g[nkey] = new_g
                    state_by_key[nkey] = new_s
                    parent[nkey] = (key, actions)
                    h = sim.min_blob_heuristic(new_s)
                    heapq.heappush(heap, (new_g + h, next(counter), "STATE", nkey))

    if verbose:
        print(f"[solve] explored {nodes_expanded} states, no solution within turn_limit", file=sys.stderr, flush=True)
    return None, None


def replay_and_print(sim: Sim, actions: List[str], print_trace: bool = True):
    """Re-runs the solved action list from scratch (optionally printing the
    board after every move, matching Log_Board_State's cadence, for diffing
    against a real playthrough)."""
    s = sim.initial_state()
    if print_trace:
        print(format_board(sim, s))
    pending_harvest = None
    for act in actions:
        kind, direction = act.split(" ")
        if kind == "harvest":
            pending_harvest = direction
        else:
            result = sim.resolve_turn(s, pending_harvest, direction)
            pending_harvest = None
            if result is None:
                raise RuntimeError(f"internal error: replay of {act!r} failed")
            kind2, s, _ = result
            if print_trace:
                print(format_board(sim, s))
            if kind2 == "WIN":
                return


def build_visualization_data(sim: Sim, actions: List[str]) -> dict:
    """Replays actions from scratch and produces a JSON-serializable list of
    board snapshots, split into a 'pre' (start-of-turn, before any harvest)
    and 'post' (right after the harvest resolves, right before the move)
    frame per turn -- exactly the two decision points in the turn model, so
    a harvest's flood-fill effect is visible on its own before the move/
    predator/growth phases change anything further."""
    plant_cells = sim.level.plant_cells

    def plants_dict(s: State):
        d = {}
        for i, pos in enumerate(plant_cells):
            is_hole, color, counter = s.plants[i]
            d[f"{pos[0]},{pos[1]}"] = {"hole": is_hole, "color": color, "counter": counter}
        return d

    def predators_list(s: State):
        return [[p.pos[0], p.pos[1]] for p in s.predators if p.alive]

    static = {}
    for pos, cell in sim.level.static_cells.items():
        static[f"{pos[0]},{pos[1]}"] = {"type": cell.base_type.name, "color": int(cell.fixed_color)}

    frames = []
    s = sim.initial_state()
    frames.append({"turn": s.turn, "phase": "pre", "bunny": list(s.bunny), "predators": predators_list(s),
                    "plants": plants_dict(s), "action": None, "harvested": [], "win": False})

    pending_harvest = None
    i = 0
    while i < len(actions):
        act = actions[i]
        kind, direction = act.split(" ", 1)
        if kind == "harvest":
            pending_harvest = direction
            i += 1
            continue

        # "move" action: first show the post-harvest frame (harvest, if any,
        # applied but bunny/predators/turn not yet advanced), then resolve
        # the full turn to get the next pre-harvest frame.
        harvested_cells = []
        if pending_harvest is not None:
            dx, dy = Sim.DIRS[pending_harvest]
            target = (s.bunny[0] + dx, s.bunny[1] + dy)
            harvested_state = sim.apply_harvest(s, target)
            for idx, pos in enumerate(plant_cells):
                if not s.plants[idx][0] and harvested_state.plants[idx][0]:
                    harvested_cells.append(list(pos))
        else:
            harvested_state = s

        frames.append({"turn": s.turn, "phase": "post", "bunny": list(s.bunny), "predators": predators_list(s),
                        "plants": plants_dict(harvested_state),
                        "action": (f"harvest {pending_harvest}" if pending_harvest else None),
                        "harvested": harvested_cells, "win": False})

        result = sim.resolve_turn(s, pending_harvest, direction)
        if result is None:
            raise RuntimeError(f"internal error: replay of {act!r} failed")
        kind2, s, _ = result
        pending_harvest = None
        frames.append({"turn": s.turn, "phase": "pre", "bunny": list(s.bunny), "predators": predators_list(s),
                        "plants": plants_dict(s), "action": f"move {direction}", "harvested": [],
                        "win": (kind2 == "WIN")})
        if kind2 == "WIN":
            break
        i += 1

    # A trailing harvest-only win (no move afterward) still needs its post frame emitted.
    if pending_harvest is not None:
        dx, dy = Sim.DIRS[pending_harvest]
        target = (s.bunny[0] + dx, s.bunny[1] + dy)
        harvested_state = sim.apply_harvest(s, target)
        frames.append({"turn": s.turn, "phase": "post", "bunny": list(s.bunny), "predators": predators_list(s),
                        "plants": plants_dict(harvested_state), "action": f"harvest {pending_harvest}",
                        "harvested": [], "win": True})

    return {
        "level_name": sim.level.level_name,
        "width": sim.level.width,
        "height": sim.level.height,
        "static": static,
        "spawn_points": [[x, y] for x, y, _d in sim.level.spawn_points],
        "frames": frames,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_LEVEL)
    ap.add_argument("--stats", type=Path, default=DEFAULT_STATS)
    ap.add_argument("--verbose", action="store_true", help="print board state after every turn of the found solution")
    ap.add_argument("--fast", action="store_true",
                    help="use Monte Carlo rollouts instead of exhaustive A* -- finds A valid winning "
                         "sequence in seconds, NOT proven optimal (may take more turns than necessary)")
    ap.add_argument("--iterations", type=int, default=500, help="rollout count for --fast mode")
    ap.add_argument("--mc-seed", type=int, default=None, help="RNG seed for --fast mode (for reproducibility)")
    ap.add_argument("--beam", action="store_true",
                    help="use beam search instead of exhaustive A* -- much more robust than --fast, "
                         "still NOT proven optimal, but far fewer wasted/oscillating states")
    ap.add_argument("--beam-width", type=int, default=3000, help="candidates kept per depth in --beam mode")
    ap.add_argument("--export-json", type=Path, default=None,
                    help="write a pre/post-harvest-per-turn board snapshot JSON for the found solution "
                         "(for the HTML visualizer)")
    args = ap.parse_args()

    level = build_level(args.csv, args.stats)
    print(f"Loaded level_name={level.level_name!r} from {args.csv.name} (stats: {args.stats.name})")
    print(f"grid {level.width}x{level.height}, prey_start={level.prey_start}, "
          f"turn_limit={level.turn_limit}, predators={level.generation_limit}, "
          f"spawn_points={[(x, y) for x, y, _ in level.spawn_points]}")

    sim = Sim(level, max_turn=level.turn_limit)
    init = sim.initial_state()
    readied_at_start = [i for i, r in enumerate(init.readied) if r is not None]
    if readied_at_start:
        print(f"Predator spawn point(s) readied at turn 0: {readied_at_start} "
              f"(generate_on_first_turn) -- spawn/respawn timing is otherwise path-dependent, "
              f"see the board trace")

    if args.beam:
        print(f"\nRunning beam search (width={args.beam_width}) -- "
              f"NOT an exhaustive/optimal search, just a fast valid solution:")
        turns, actions = beam_search_solve(sim, beam_width=args.beam_width, verbose=True)
    elif args.fast:
        print(f"\nRunning Monte Carlo rollouts ({args.iterations} iterations) -- "
              f"NOT an exhaustive/optimal search, just a fast valid solution:")
        turns, actions = monte_carlo_solve(sim, iterations=args.iterations, seed=args.mc_seed, verbose=True)
    else:
        turns, actions = solve(sim, verbose=True)
    if turns is None:
        print(f"NO SOLUTION found within turn_limit={level.turn_limit}")
        sys.exit(1)
    if sim.tie_count:
        print(f"[note] hit {sim.tie_count} genuine predator-move ties while exploring the search space "
              f"(expected on a symmetric board -- most are in branches that aren't part of the final answer)")

    if args.beam:
        label = "Turns to win (NOT proven minimal -- beam search result)"
    elif args.fast:
        label = "Turns to win (NOT proven minimal -- Monte Carlo result)"
    else:
        label = "Minimum turns to win"
    print(f"\n{label}: {turns}")
    print("Action sequence (harvest = free action on the adjacent tile in that direction, "
          "move = costs one turn):")
    for a in actions:
        print(f"  {a}")

    # Specifically check whether the WINNING path itself ever depended on a
    # tie-break -- that's the one thing that could make this solution not
    # reproduce exactly in a real playthrough (see docstring note #7).
    sim.tie_count = 0
    sim.warn_ties = True
    print("\nChecking the solution path itself for predator-move ties...")
    replay_and_print(sim, actions, print_trace=False)
    if sim.tie_count == 0:
        print("None found -- this solution's predator movement does not depend on any tie-break, "
              "so it should reproduce exactly in-game.")
    else:
        print(f"{sim.tie_count} tie(s) found ON the solution path (printed above with [warning]) -- "
              f"the predator's real move at that point depends on Unity's RNG and might differ from "
              f"this tool's prediction from that turn onward.")

    if args.verbose:
        print("\n--- board trace ---")
        replay_and_print(sim, actions)

    if args.export_json:
        import json
        data = build_visualization_data(sim, actions)
        args.export_json.write_text(json.dumps(data))
        print(f"\nWrote visualization data to {args.export_json}")


if __name__ == "__main__":
    main()


