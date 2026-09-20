# -*- coding: utf-8 -*-
"""対戦評価。勝率・自爆率・攻撃成功率・相手の逃走路を減らした量を、同じシードで再現できる形で出す。
  python -m bomberman_ai.cli evaluate --a combined --b rule --games 10 --seed 0 [--model runs/model.json]"""
import json, os, time
from typing import Dict, List
from .agents import Agent, make_agent, play_game
from .state import GameState


def match(a0: Agent, a1: Agent, n_games: int, seed: int = 0, max_frames: int = 7200, swap_sides: bool = True) -> Dict:
    """a0 の視点の指標。swap_sides で半分は左右を入れ替える（初期位置の有利不利を打ち消す）"""
    wins = losses = draws = 0
    own_deaths = 0
    opp_deaths_by_my_bomb = 0
    my_bombs = 0
    frames = []
    t0 = time.time()
    for g in range(n_games):
        flip = swap_sides and (g % 2 == 1)
        A, B = (a1, a0) if flip else (a0, a1)
        s, acts, s0 = play_game(A, B, seed=seed + g, max_frames=max_frames)
        me = 1 if flip else 0
        frames.append(s.frame)
        if s.winner == me:
            wins += 1
        elif s.winner == 1 - me:
            losses += 1
        else:
            draws += 1
        pm, po = s.players[me], s.players[1 - me]
        if not pm.alive and pm.cause_of_death == "own_bomb":
            own_deaths += 1
        if not po.alive and po.cause_of_death == "opp_bomb":
            opp_deaths_by_my_bomb += 1
        my_bombs += sum(1 for a in acts if a[me].endswith("/BOMB"))
    st = a0.stats()
    return {
        "games": n_games, "max_frames": max_frames, "win_rate": wins / n_games, "loss_rate": losses / n_games, "draw_rate": draws / n_games,
        "self_kill_rate": own_deaths / n_games,
        "attack_success_rate": opp_deaths_by_my_bomb / max(1, my_bombs),
        "kills": opp_deaths_by_my_bomb, "bombs_placed": my_bombs,
        "mean_frames": sum(frames) / n_games, "mean_routes_cut": st.get("mean_routes_cut", 0.0),
        "mean_D": st.get("mean_D", 0.0), "mean_F": st.get("mean_F", 0.0), "seconds": round(time.time() - t0, 1),
    }


def load_model(path: str) -> dict:
    return json.load(open(path, encoding="utf-8")) if path and os.path.exists(path) else {}


def evaluate_suite(model: dict, n_games: int, seed: int, opponents=("random", "rule", "untrained"), kind: str = "combined", max_frames: int = 7200) -> Dict[str, Dict]:
    """学習済みモデル（または手動重み）を、ランダム・ルール・学習前（手動重み）と対戦させる"""
    out = {}
    for opp in opponents:
        a = make_agent(kind, model)
        b = make_agent(kind, {}) if opp == "untrained" else make_agent(opp)
        out[opp] = match(a, b, n_games, seed, max_frames=max_frames)
    return out


def table(results: Dict[str, Dict]) -> str:
    keys = ["win_rate", "self_kill_rate", "attack_success_rate", "mean_routes_cut", "mean_frames"]
    lines = ["| 相手 | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
    for name, r in results.items():
        lines.append("| " + name + " | " + " | ".join("%.3f" % r[k] if isinstance(r[k], float) else str(r[k]) for k in keys) + " |")
    return "\n".join(lines)
