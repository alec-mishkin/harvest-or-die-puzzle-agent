from game.level_solver import Sim, State, CT, Color as SolverColor
from interface.state import GameState, Tile, Position, Predator, Color, TileType
from interface.action import Direction, Turn
from enum import Enum

TILE_TYPE_MAP = {
    CT.HOLE: TileType.HOLE, CT.GROUND: TileType.GROUND, CT.BUSH: TileType.BUSH,
    CT.PLANT: TileType.PLANT, CT.SPAWN: TileType.SPAWN,
    CT.DIAGONAL_SPAWN: TileType.DIAGONAL_SPAWN,
    CT.EMPTY: TileType.WALL,    #rename: solver's EMPTY means wall
}

COLOR_MAP = {
    SolverColor.RED: Color.RED, SolverColor.BLUE: Color.BLUE,
    SolverColor.PURPLE: Color.PURPLE, SolverColor.YELLOW: Color.YELLOW,
    SolverColor.NONE: Color.NONE,
}

DIR_CODE = {
    Direction.UP: "U", Direction.DOWN: "D",
    Direction.LEFT: "L", Direction.RIGHT: "R",
}

def _pos(t: tuple[int,int]) -> Position:
    return Position(x=t[0], y=t[1])

def to_game_state(sim: Sim, state: State) -> GameState:
    tiles = []
    for pos in sim.level.static_cells:
        ct = sim.cell_type(state, pos)
        tiles.append(Tile(
            pos=_pos(pos),
            tile_type=TILE_TYPE_MAP[ct],
            color=COLOR_MAP[sim.cell_color(state, pos)] if ct is CT.PLANT else Color.NONE,
            hole_counter=sim.hole_counter(state,pos),
            scored=pos in sim.scored_cells,
        ))
    predators = [
        Predator(
            pos=_pos(p.pos),
            next_pos=_pos(p.pending_target) if p.pending_target else None,
            diagonal=p.diagonal,
        )
        for p in state.predators if p.alive
    ]

    return GameState(
        current_turn=state.turn,
        max_turn=sim.level.turn_limit,
        bunny=_pos(state.bunny),
        held_seed=COLOR_MAP[state.seed],
        tiles=tiles,
        predators=predators,
    )
    
def to_solver(turn: Turn) -> tuple[str | None, str]:
    harvest = DIR_CODE[turn.harvest] if  turn.harvest else None
    return harvest, DIR_CODE[turn.move]

class Outcome(Enum):
    ONGOING = "ongoing"; WIN = "win"; DEATH = "death"; ILLEGAL = "illegal"

def step(sim, state, harvest_code, move_code):
    reason = _illegal_reason(sim, state, harvest_code, move_code)
    if reason:
        return Outcome.ILLEGAL, state, reason
    result = sim.resolve_turn(state, harvest_code, move_code)
    if result is None:
        return Outcome.DEATH, state, "that move was fatal"
    kind, new_state, _ = result
    return (Outcome.WIN if kind == "WIN" else Outcome.ONGOING), new_state, ""

def _neighbor(pos: tuple[int, int], code: str) -> tuple[int, int]:
    dx, dy = Sim.DIRS[code]
    return (pos[0] + dx, pos[1] + dy)

def _illegal_reason(sim, s, harvest_code, move_code):
    if harvest_code is not None:
        t = _neighbor(s.bunny, harvest_code)
        if not sim.in_bounds(t) or sim.cell_type(s, t) is not CT.PLANT:
           return f"nothing to harvest to the {harvest_code}"

    m = _neighbor(s.bunny, move_code)
    if not sim.in_bounds(m) or not sim.walkable_static(m):
        return f"can't move {move_code}: wall or edge of board"
    
    return None
