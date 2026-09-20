# -*- coding: utf-8 -*-
"""コマンド入口。
  python -m bomberman_ai.cli match    --a rule --b random --games 4 --seed 0 [--replay runs/last.json]
  python -m bomberman_ai.cli train    --role defense --iters 3 --pop 6 --games 4 --seed 0 --out runs/model.json
  python -m bomberman_ai.cli evaluate --model runs/model.json --games 10 --seed 100 --out runs/eval.json
  python -m bomberman_ai.cli replay   --file runs/last.json     （再生して最終状態のキーを表示）"""
import argparse, json, os, sys
from .agents import make_agent, play_game
from .evaluate import match, evaluate_suite, load_model, table
from . import replay as R
from .learn import train


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("match")
    m.add_argument("--a", default="rule")
    m.add_argument("--b", default="random")
    m.add_argument("--games", type=int, default=4)
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--model", default="")
    m.add_argument("--replay", default="")
    t = sub.add_parser("train")
    t.add_argument("--role", choices=["defense", "offense"], default="defense")
    t.add_argument("--iters", type=int, default=3)
    t.add_argument("--pop", type=int, default=6)
    t.add_argument("--games", type=int, default=4)
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--opponent", default="rule")
    t.add_argument("--model", default="")
    t.add_argument("--out", default="runs/model.json")
    e = sub.add_parser("evaluate")
    e.add_argument("--model", default="")
    e.add_argument("--games", type=int, default=10)
    e.add_argument("--seed", type=int, default=100)
    e.add_argument("--out", default="")
    r = sub.add_parser("replay")
    r.add_argument("--file", required=True)
    for sp in (m, t, e):
        sp.add_argument("--max-frames", type=int, default=7200, help="1試合の最大コマ数（学習を速くするには 1800 など）")
    a = ap.parse_args(argv)
    if a.cmd == "match":
        model = load_model(a.model)
        A, B = make_agent(a.a, model), make_agent(a.b, model)
        if a.replay:
            s, acts, s0 = play_game(A, B, seed=a.seed, max_frames=a.max_frames)
            R.save(a.replay, s0, acts, {"a": a.a, "b": a.b, "seed": a.seed, "winner": s.winner, "frames": s.frame})
            print("winner", s.winner, "frames", s.frame, "replay ->", a.replay)
        res = match(A, B, a.games, a.seed, max_frames=a.max_frames)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    elif a.cmd == "train":
        train(a.role, a.iters, a.pop, a.games, a.seed, opponent=a.opponent, model=load_model(a.model), out=a.out,
              log_path=os.path.splitext(a.out)[0] + "_log.jsonl", max_frames=a.max_frames)
    elif a.cmd == "evaluate":
        res = evaluate_suite(load_model(a.model), a.games, a.seed, max_frames=a.max_frames)
        print(table(res))
        if a.out:
            json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    elif a.cmd == "replay":
        s0, acts, meta = R.load(a.file)
        s = R.play(s0, acts)
        print("meta", meta, "winner", s.winner, "frames", s.frame, "key", hash(s.key()))


if __name__ == "__main__":
    main()
