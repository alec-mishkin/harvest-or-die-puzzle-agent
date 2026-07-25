from game.level_solver import build_level, Sim, DEFAULT_LEVEL, DEFAULT_STATS

def test_level_loads():
    level = build_level(DEFAULT_LEVEL, DEFAULT_STATS)
    assert level.width > 0
    assert level.height > 0
    assert level.turn_limit > 0

def test_initial_state_places_bunny_at_start():
    level = build_level(DEFAULT_LEVEL, DEFAULT_STATS)
    sim = Sim(level, max_turn=level.turn_limit)
    state = sim.initial_state()
    assert state.bunny == level.prey_start

def test_level_matches_unity():
    level = build_level(DEFAULT_LEVEL, DEFAULT_STATS)
    assert level.turn_limit == 28          
    assert level.generation_limit == 1    
