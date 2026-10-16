from interface.action import Direction
from interface.state import Color, GameState, Position, TileType

DELTA = {Direction.UP: (0, 1), Direction.DOWN: (0, -1),
         Direction.LEFT: (-1, 0), Direction.RIGHT: (1, 0)}

def futile_harvests(gs: GameState) -> list[Direction]:
     """Harvest directions whose target plant colour equals the held seed."""
     if gs.held_seed is Color.NONE:
         return []
     by_pos = {t.pos: t for t in gs.tiles}
     return [d for d, (dx, dy) in DELTA.items()
             if (t := by_pos.get(Position(x=gs.bunny.x + dx, y=gs.bunny.y + dy)))
             and t.tile_type is TileType.PLANT and t.color == gs.held_seed]

