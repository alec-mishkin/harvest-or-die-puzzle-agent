from game.level_solver import build_level, Sim, DEFAULT_LEVEL, DEFAULT_STATS
from interface.adapter import Outcome, step, to_game_state, to_solver
from interface.serialize import to_prompt
from agent.llm_agent import LLMAgent

MAX_RETRIES = 3
def play_episode(agent, sim, verbose=True):
    state = sim.initial_state()
    history = []

    while state.turn < sim.level.turn_limit:
        board = to_prompt(to_game_state(sim, state))
        error = None

        for _ in range(MAX_RETRIES):
            turn = agent.choose_turn(board, error)
            harvest_code, move_code = to_solver(turn)
            outcome, new_state, msg = step(sim, state, harvest_code, move_code)
            if outcome is not Outcome.ILLEGAL:
                break
            error = msg
        else:
            return "FORFEIT", history

        history.append((turn, outcome))
        if verbose:
            print(f"T{state.turn}: harvest={turn.harvest} move={turn.move} -> {outcome.value}")
            print(f"    {turn.reasoning}")

        if outcome in (Outcome.WIN, Outcome.DEATH):
            return outcome.value.upper(), history
        state = new_state

     return "TIMEOUT", history

 if __name__ == "__main__":
     level = build_level(DEFAULT_LEVEL, DEFAULT_STATS)
     sim = Sim(level, max_turn=level.turn_limit)
     result, history = play_episode(LLMAgent(), sim)
     print(f"\nResult: {result} in {len(history)} turns")
