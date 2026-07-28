from collections import Counter
from interface.state import Color, GameState, Position, Tile, TileType

PLANT_CHAR = {Color.RED: "R", Color.BLUE: "B", Color.YELLOW: "Y", Color.PURPLE: "P"}

TYPE_CHAR = {
    TileType.HOLE: "o", TileType.GROUND: ".", TileType.WALL: "#",
    TileType.SPAWN: "s", TileType.DIAGONAL_SPAWN: "d", TileType.BUSH: "*",
}

def _cell_char(tile: Tile) -> str:
    if tile.tile_type is TileType.PLANT:
        return PLANT_CHAR[tile.color]
    if tile.tile_type is TileType.HOLE and tile.color in PLANT_CHAR:
        return PLANT_CHAR[tile.color].lower()
    return TYPE_CHAR[tile.tile_type]

def _describe(t: Tile) -> str:
    if t.tile_type is TileType.PLANT:
        return f"a {t.color} plant"
    return t.tile_type.replace("_", " " )

def to_prompt(gs: GameState) -> str:
    by_pos = {t.pos: t for t in gs.tiles}
    width = max(p.x for p in by_pos) + 1
    height = max(p.y for p in by_pos) + 1
    pred_at = {p.pos for p in gs.predators}

    rows = []
    for y in range(height - 1, -1, -1): #high y first up is up
        cells = []
        for x in range(width):
            pos = Position(x=x, y=y)
            if pos == gs.bunny:
                cells.append("@")
            elif pos in pred_at:
                cells.append("X")
            else:
                cells.append(_cell_char(by_pos[pos]))
        rows.append(f" {y} " + " ".join(cells))
    rows.append("   " + " ".join(str(x) for x in range(width)))
    board = "\n".join(rows)
    
    scored = [ t for t in gs.tiles if t.scored and t.tile_type in (TileType.PLANT, TileType.HOLE)]
    tally = Counter(t.color if t.tile_type is TileType.PLANT else "hole" for t in scored)
    tally_str = ", ".join(f"{n} {k}" for k, n in sorted(tally.items(), key=lambda kv: -kv[1]))
    lines = [
        f"Turn {gs.current_turn}/{gs.max_turn}  ({gs.max_turn - gs.current_turn} moves left)",
        f"Held seed: {gs.held_seed.upper()}  (harvested plants regrow this color)",
        f"You are at ({gs.bunny.x},{gs.bunny.y}) standing on: {_describe(by_pos[gs.bunny])}",
        "",
        "Goal: every scoring tile the same color, and no holes.",
        f"Currently: {tally_str}",
        "",
        board,
        "",
        "Legend: @ you | X predator | R/B/Y/P plants | r/b/y/p holes (lowercase = regrow color)",
        "        # wall | s spawn | * bush | o hole with no color"
        "Coordinates: x increases right, y increases UP (so 'up' moves toward the top row).",

    ]

    for p in gs.predators:
        kind = "diagonal predator" if p.diagonal else "predator"
        if p.next_pos:
            lines.append(f"- {kind} at ({p.pos.x},{p.pos.y}) will move to ({p.next_pos.x},{p.next_pos.y}) next turn")
        else:
            lines.append(f"- {kind} at ({p.pos.x},{p.pos.y}), next move not yet decided")
    for t in sorted((t for t in gs.tiles if t.tile_type is TileType.HOLE and t.hole_counter is not None),
                    key=lambda t: (t.pos.y, t.pos.x)):
        turns = "turn" if t.hole_counter == 1 else "turns"
        lines.append(f"- hole at ({t.pos.x},{t.pos.y}) regrows in {t.hole_counter} {turns} as a {t.color.upper()} plant")
    return "\n".join(lines)


