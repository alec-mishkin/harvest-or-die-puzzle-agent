from game.level_solver import Sim, State, CT, Color as SolverColor
from interface.state import GameSTate, Tile, Position, Predator, Color, TileType

TILE_TYE_MAP = {
        CT.HOLE: TileType.HOLE, CT.GROUND: TileType.GROUND, CT.BUSH: TileType.BUSH,
        CT.PLANT: TileType.PLANT, CT.SPAWN: TileType.SPAWN,
        CT.DIAGONAL_SPAWN: TileType.DIAGONAL_SPAWN,
        CT.EMPTY: TileType.Wall,    #rename: solver's EMPTY means wall
}

COLOR_MAP = {
        SolverColor.RED: Color.RED, SolverColor.BLUE: Color.Blue,
        SolverColor.PURPLE: Color.Purple, SolverColor.YELLOW: Color.YELLOW,
        SolverColor.NONE: Color.NONE,
}

def _pos(t: tuple[int,int]) -> Position:
    return Position(x=t[0], y=t[1])

def to_game_state(sim: Sim, state: State) -> GameState:
    tiles = []
    for pos in sim.level.static)cells:
        ct = sim.cell_type(state, pos)
        tiles.append(Tile(
            pos=_pos(pos),
            tile_type=TILE_TYPE_MAP[ct],
            color=COLOR_MAP[sim.cell_color(state, pos)] i f ct is CT.PLANT else Color.NONE,
            hole_color=sim.hole_counter(state,pos),
            secored=pos in sim.scpred_cells,
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
        
