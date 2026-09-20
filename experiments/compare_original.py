"""Compare against the ORIGINAL opponent implementation, not changed defaults.

Prepare: git worktree add --detach ../bomberman-ai-baseline bd8048b
Run: python experiments/compare_original.py --model experiments/aggressive_candidate.json
"""
import argparse
import importlib
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bomberman_ai.agents import make_agent
from bomberman_ai.evaluate import match, load_model, table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', default='../bomberman-ai-baseline')
    ap.add_argument('--model', required=True)
    ap.add_argument('--games', type=int, default=4)
    ap.add_argument('--seed', type=int, default=100)
    ap.add_argument('--max-frames', type=int, default=1800)
    ap.add_argument('--out', default='experiments/08_frozen_opponents.json')
    a = ap.parse_args()
    folder = Path(a.baseline).resolve()/'bomberman_ai'
    spec = importlib.util.spec_from_file_location('frozen_bomberman_ai', folder/'__init__.py', submodule_search_locations=[str(folder)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    old = importlib.import_module('frozen_bomberman_ai.agents')
    results = {}
    for label, kind in [('original_rule', 'rule'), ('original_untrained', 'combined')]:
        results[label] = match(make_agent('combined', load_model(a.model)), old.make_agent(kind),
                               a.games, a.seed, max_frames=a.max_frames)
        print(label, json.dumps(results[label]), flush=True)
    Path(a.out).write_text(json.dumps(results, indent=2))
    print(table(results))

if __name__ == '__main__': main()
