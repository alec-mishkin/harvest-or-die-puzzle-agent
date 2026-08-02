import argparse
from collections import Counter

from game.levels import LEVELS, make_sim
from game.level_solver import build_level, Sim, DEFAULT_LEVEL, DEFAULT_STATS
from interface.adapter import Outcome, step, to_game_state, to_solver, legal_turns
from interface.serializer import to_prompt
#from agent.llm_agent import LLMAgent
from agent.random_agent import RandomAgent
from agent.greedy_agent import GreedyAgent
from agent.openai_agent import OpenAIAgent


MAX_RETRIES = 3
def play_episode(agent, sim, verbose=True):
    state = sim.initial_state()
    history = []

    while state.turn < sim.level.turn_limit:
        gs = to_game_state(sim, state)
        #legal = legal_turns(sim, state)
        #if not legal:
        #    return "TRAPPED", history
        
        candidates = []
        for turn in legal_turns(sim, state):
            hc, mc = to_solver(turn)
            result = sim.resolve_turn(state, hc, mc)
            candidates.append((turn, result[1] if result else None))   # None = fatal
        if not candidates:
            return "TRAPPED", history

        error = None
        for _ in range(MAX_RETRIES):
            turn = agent.choose_turn(gs,candidates, error)
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
    ap.add_argument("--agent", choices=["random", "greedy", "llm", "openai"], default="random")
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
