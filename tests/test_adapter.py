import pytest
from pydantic import field_validator
from game.level_solver import build_level, Sim, DEFAULT_LEVEL, DEFAULT_STATS
from interface.adapter import to_game_state, Outcome, step, to_solver, legal_turns

from interface.state import Color, Position, TileType
from interface.action import Direction, Turn

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

@pytest.mark.parametrize("direction,code", [
    (Direction.UP, "U"),
    (Direction.DOWN, "D"),
    (Direction.LEFT, "L"),
    (Direction.RIGHT,"R"),
])

def test_to_solver_maps_every_direction(direction, code):
    harvest, move = to_solver(Turn(reasoning="t", harvest=direction, move=direction))
    assert harvest == code
    assert move == code

def test_to_solver_keeps_harvest_and_move_distinct():
    harvest, move = to_solver(Turn(reasoning="t", harvest=Direction.LEFT, move=Direction.RIGHT))
    assert harvest == "L"
    assert move == "R"

def test_to_solver_omitted_harvest_is_none():
    harvest, move = to_solver(Turn(reasoning="t", move=Direction.UP))
    assert harvest is None
    assert move == "U"

def test_move_into_wall_is_illegal(sim_and_state):
    sim, state = sim_and_state # bunny at (1,1); (0,1) is a wall
    outcome, new_state, reason = step(sim, state, None, "L")
    assert outcome is Outcome.ILLEGAL
    assert new_state is state           # turn did NOT happen
    assert reason                       # non-empty explanation for the model

@pytest.mark.parametrize("move_code", ["U", "D", "R"])
def test_open_directions_are_not_illegal(sim_and_state, move_code):
    sim, state = sim_and_state
    outcome, _, _ = step(sim, state, None, move_code)
    print(move_code,outcome)
    assert outcome is not Outcome.ILLEGAL

def test_ongoing_turn_advances_state(sim_and_state):
    sim, state = sim_and_state
    outcome, new_state, _ = step(sim, state, None, "D")
    assert outcome is not Outcome.ILLEGAL
    if outcome is Outcome.ONGOING:
        assert new_state.turn == state.turn + 1
        assert new_state is not state

def test_legal_turns_at_start(sim_and_state):
    sim, state = sim_and_state
    turns = legal_turns(sim, state)
    assert len(turns) == 12 # 4 harvests x 3 moves
    assert all(t.move is not Direction.LEFT for t in turns)   # wall at (0,1)
    assert all(t.harvest is not Direction.LEFT for t in turns) 

