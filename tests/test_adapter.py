import pytest
from game.level_solver import build_level, Sim, DEFAULT_LEVEL, DEFAULT_STATS
from interface.adapter import to_game_state
from interface.state import Color, Position, TileType

@pytest.fixture
def sim_and_state():
    level = build_level(DEFAULT_LEVEL, DEFAULT_STATS)
    sim=Sim(level,max_turn=level.turn_limit)
    return sim, sim.initial_state()

def test_converts_initial_state(sim_and_state):
    sim, state = sim_and_state
    gs = to_game_state(sim, state)
    assert gs.current_turn == state.turn
    assert gs.bunny == Position(x=1, y=1)
    assert gs.held_seed is Color.NONE
    assert gs.max_turn == 28
    assert len(gs.tiles) == sim.level.width * sim.level.height  # 6 * 5 = 30

def test_non_plant_tiles_have_no_color(sim_and_state):
    sim, state = sim_and_state
    gs = to_game_state(sim, state)
    non_plants = [t for t in gs.tiles if t.tile_type is not TileType.PLANT]
    assert non_plants 
    assert all(t.color is Color.NONE for t in non_plants)


def test_plant_count_matches_level(sim_and_state):
    sim, state = sim_and_state
    gs = to_game_state(sim, state)
    plants = [t for t in gs.tiles if t.tile_type is TileType.PLANT]
    assert len(plants) == len(sim.level.plant_cells)    # 15



