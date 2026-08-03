import argparse, time
from collections import Counter

from game.levels import LEVELS, make_sim
from game.level_solver import build_level, Sim
from interface.adapter import Outcome, step, to_game_state, to_solver, legal_turns
from interface.serializer import to_prompt
from agent.random_agent import RandomAgent
from agent.greedy_agent import GreedyAgent
from agent.openai_agent import OpenAIAgent


MAX_RETRIES = 3
def play_episode(agent, sim, verbose=True, on_turn = None):
    state = sim.initial_state()
    history = []

    while state.turn < sim.level.turn_limit:
        gs = to_game_state(sim, state)
        board = to_prompt(gs)
        
        candidates = []
        for turn in legal_turns(sim, state):
            hc, mc = to_solver(turn)
            result = sim.resolve_turn(state, hc, mc)
            candidates.append((turn, result[1] if result else None))   # None = fatal
        if not candidates:
            return "TRAPPED", history

        error, attempts = None, 0
        for _ in range(MAX_RETRIES):
            t0 = time.perf_counter()
            turn = agent.choose_turn(gs,candidates, error)
            latency = time.perf_counter() - t0
            attempts += 1
            harvest_code, move_code = to_solver(turn)
            outcome, new_state, msg = step(sim, state, harvest_code, move_code)
            if outcome is not Outcome.ILLEGAL:
                break
            error = msg
        else:
            return "FORFEIT", history
        if on_turn:
            on_turn({
                "turn": state.turn,
                "board": board,
                "reasoning": turn.reasoning,
                "harvest": turn.harvest.value if turn.harvest else None,
                "move": turn.move.value,
                "outcome": outcome.value,
                "attempts": attempts,
                "latency_s": round(latency, 2),
                "n_candidates": len(candidates),
            })

        history.append((turn, outcome))
        if verbose:
            print(f"T{state.turn}: harvest={turn.harvest} move={turn.move} -> {outcome.value}")
            if turn.reasoning:
                print(f"    {turn.reasoning}")

        if outcome in (Outcome.WIN, Outcome.DEATH):
            return outcome.value.upper(), history
        state = new_state

    return "TIMEOUT", history

def make_agent(kind, seed,sim):
    if kind == "random":
        return RandomAgent(seed=seed)
    if kind == "greedy":
        return GreedyAgent(sim, seed=seed)
    if kind == "openai":
        return OpenAIAgent(model="gpt-5.6-luna")

    #return LLMAgent()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", choices=["random", "greedy", "openai"], default="random")
    ap.add_argument("--level", default="level_3", choices=[*LEVELS])
    ap.add_argument("--episodes", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    

    level = build_level(DEFAULT_LEVEL, DEFAULT_STATS)
    sim = make_sim(args.level)

    if args.episodes == 1:
        result, history = play_episode(make_agent(args.agent, args.seed,sim), sim)
        print(f"\nResult: {result} in {len(history)} turns")
    else:
        results = Counter()
        for i in range(args.episodes):
            result, history = play_episode(make_agent(args.agent, args.seed + i,sim), sim, verbose=False)
            results[result] += 1
        total = sum(results.values())
        print(f"{args.agent} over {total} episodes:")
        for outcome, n in results.most_common():
            print(f"  {outcome:8} {n:4}  ({n / total:.0%})")
