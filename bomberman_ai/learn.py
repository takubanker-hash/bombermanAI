# -*- coding: utf-8 -*-
"""初期学習処理: 攻守それぞれの重みを、対戦結果の報酬で改善する（進化戦略 / 有限差分の方策勾配）。
大規模なニューラルネットや MCTS は使わない。線形の評価関数 D・F の重みベクトルを直接更新する。

  役割 defense: CombinedAgent の wD を更新（wF 固定）。相手は固定（rule または前回のモデル）
  役割 offense: CombinedAgent の wF を更新（wD 固定）
  報酬 = 勝ち +1 / 負け -1（自爆なら -1.5）/ 引き分け 0 + 0.1 × 生存時間の割合（時間切れまで）
  更新: w ← w + lr × Σ_k (R_k − mean R) ε_k / (n σ)   （ε_k ~ N(0,1) の摂動を各重みに加えて評価）
  「評価点だけを稼ぐ挙動」の確認: 反復ごとに mean_D / mean_F（自分の評価点の平均）と勝率を並べて記録する。
  評価点が上がるのに勝率が上がらない・自爆率が上がる場合は報酬ハックの疑い。
使い方: python -m bomberman_ai.cli train --role defense --iters 3 --pop 6 --games 4 --seed 0 --out runs/model.json"""
import json, os, random, time
from typing import Dict
from . import defense as D
from . import offense as F
from .agents import CombinedAgent, make_agent
from .evaluate import match


def reward_of(result: Dict) -> float:
    # match() は複数試合の平均指標を返すので、そこから期待報酬を作る
    r = result["win_rate"] - result["loss_rate"] - 0.5 * result["self_kill_rate"]
    r += 0.1 * min(1.0, result["mean_frames"] / float(result.get("max_frames", 7200)))
    return r


def train(role: str = "defense", iters: int = 3, pop: int = 6, games: int = 4, seed: int = 0, sigma: float = 0.3, lr: float = 0.5,
          opponent: str = "rule", model: Dict = None, out: str = "runs/model.json", log_path: str = None, max_frames: int = 7200) -> Dict:
    rng = random.Random(seed)
    model = dict(model or {})
    wD = dict(model.get("wD") or D.DEFAULT_WEIGHTS)
    wF = dict(model.get("wF") or F.DEFAULT_WEIGHTS)
    target = wD if role == "defense" else wF
    fixed_keys = {"dead", "self_dead"}  # 拒否条件の重みは学習しない
    keys = [k for k in target if k not in fixed_keys]
    history = model.get("history", [])
    log = open(log_path, "a", encoding="utf-8") if log_path else None

    def evaluate_weights(w: Dict[str, float], it: int, k: int) -> Dict:
        m = {"wD": wD if role != "defense" else w, "wF": wF if role != "offense" else w}
        a = CombinedAgent(m["wD"], m["wF"])
        b = make_agent(opponent, model) if opponent != "self" else CombinedAgent(wD, wF)
        return match(a, b, games, seed=seed * 1000 + it * 100 + k * 10, max_frames=max_frames)

    for it in range(iters):
        t0 = time.time()
        base = evaluate_weights(target, it, 0)
        eps = []
        rewards = []
        for k in range(pop):
            e = {key: rng.gauss(0, 1) for key in keys}
            w = {key: target[key] + sigma * e[key] for key in keys}
            w.update({key: target[key] for key in fixed_keys if key in target})
            res = evaluate_weights(w, it, k + 1)
            eps.append(e)
            rewards.append(reward_of(res))
        mean_r = sum(rewards) / len(rewards)
        std = (sum((r - mean_r) ** 2 for r in rewards) / len(rewards)) ** 0.5 or 1.0
        for key in keys:
            g = sum((r - mean_r) / std * e[key] for r, e in zip(rewards, eps)) / (pop * sigma)
            target[key] += lr * g
        rec = {"iter": it, "role": role, "base_reward": round(reward_of(base), 3), "pop_mean_reward": round(mean_r, 3),
               "win_rate": base["win_rate"], "self_kill_rate": base["self_kill_rate"], "mean_D": round(base["mean_D"], 3),
               "mean_F": round(base["mean_F"], 3), "mean_routes_cut": round(base["mean_routes_cut"], 3), "seconds": round(time.time() - t0, 1)}
        history.append(rec)
        line = json.dumps(rec, ensure_ascii=False)
        print(line, flush=True)
        if log:
            log.write(line + "\n")
            log.flush()
        model = {"wD": wD, "wF": wF, "mix": model.get("mix", 0.5), "history": history, "seed": seed, "role_last": role}
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        json.dump(model, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return model
