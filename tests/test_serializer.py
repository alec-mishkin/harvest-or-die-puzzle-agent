import pytest
from interface.serializer import render_board, to_prompt
from game.level_solver import build_level, Sim, DEFAULT_LEVEL, DEFAULT_STATS
from interface.adapter import to_game_state

@pytest.fixture
def sim_and_state():
    level = build_level(DEFAULT_LEVEL, DEFAULT_STATS)
    sim=Sim(level,max_turn=level.turn_limit)
    return sim, sim.initial_state()

def test_board_has_exactly_one_bunny(sim_and_state):
    sim, state = sim_and_state
    board = render_board(to_game_state(sim, state))
    assert board.count("@") == 1

def test_board_renders_high_y_at_top(sim_and_state):
    sim, state = sim_and_state
    gs = to_game_state(sim, state)
    height = max(t.pos.y for t in gs.tiles) + 1
    rows = render_board(gs).splitlines()[:-1]        # drop the x-axis line
    bunny_row = next(i for i, r in enumerate(rows) if "@" in r)
    assert bunny_row == height - 1 - gs.bunny.y
