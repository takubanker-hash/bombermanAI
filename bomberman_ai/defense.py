# -*- coding: utf-8 -*-
"""守備評価関数 D。特徴量の計算・重み・行動選択を分離している。

使い方:
  feats = defense_features(state_after, me)          # 候補行動を先読みした後の状態で特徴量を計算
  score = defense_score(feats, weights)               # 重み付き和
  action = choose_defense(state, me, weights)         # 生存可能な移動候補から D 最大を選ぶ
特徴量（すべて 0〜1 程度に正規化。dead は拒否条件）:
  safe_area   逃げ込めるマスの数 / 30
  routes      逃走路の数 / 4
  slack       いるマスが燃えるまでの余裕 / FUSE（燃えないなら 1）
  on_line     いるマスが爆風線上（燃える予定）なら 1。余裕があっても線上に留まらないための項
  mobility    危険を無視して 4 歩以内に着けるマス数 / 20（将来の移動自由度）
  deadend     袋小路（出られる隣が 1 つ以下）なら 1
  own_danger  自分の爆弾の爆風線上にいるなら 1
  dist_opp    相手との距離 / 20（重み 0 でも可。距離を取る／詰める性向）
  dead        先読みで死んだら 1（choose では拒否）"""
from typing import Dict, List, Tuple
from .constants import FUSE, SPEED, DIRS, in_board, is_pillar
from .state import GameState
from .safety import escape_area, escape_routes, time_slack, reachable_tiles, burn_schedule, on_own_blast_line, INF
from .engine import step
from .actions import legal_actions, parse

FEATURE_NAMES = ["safe_area", "routes", "slack", "on_line", "mobility", "deadend", "own_danger", "dist_opp", "dead"]

DEFAULT_WEIGHTS: Dict[str, float] = {
    "safe_area": 1.0, "routes": 0.8, "slack": 1.0, "on_line": -1.0, "mobility": 0.4, "deadend": -0.6, "own_danger": -0.8,
    "dist_opp": 0.0, "dead": -100.0,
}


def defense_features(s: GameState, me: int) -> Dict[str, float]:
    p = s.players[me]
    if not p.alive:
        f = {k: 0.0 for k in FEATURE_NAMES}
        f["dead"] = 1.0
        return f
    safe, info = escape_area(s, me)
    routes = len({info["first"][t] for t in safe if info["first"].get(t)})
    c, r = p.tile()
    lt = info["L"].get((c, r))
    sl = INF if lt is None else lt - s.frame
    open_nb = sum(1 for dx, dy in DIRS.values() if in_board(c + dx, r + dy) and not is_pillar(c + dx, r + dy) and s.bomb_at(c + dx, r + dy) is None)
    q = s.players[1 - me]
    oc, orr = q.tile()
    return {
        "safe_area": min(len(safe), 30) / 30.0,
        "routes": routes / 4.0,
        "slack": 1.0 if sl >= INF else max(0, min(sl, FUSE)) / FUSE,
        "on_line": 0.0 if lt is None else 1.0,
        "mobility": min(len(reachable_tiles(s, me, SPEED * 4)), 20) / 20.0,
        "deadend": 1.0 if open_nb <= 1 else 0.0,
        "own_danger": 1.0 if on_own_blast_line(s, me) else 0.0,
        "dist_opp": (abs(c - oc) + abs(r - orr)) / 20.0,
        "dead": 0.0,
    }


def defense_score(feats: Dict[str, float], weights: Dict[str, float]) -> float:
    return sum(weights.get(k, 0.0) * v for k, v in feats.items())


def lookahead(s: GameState, me: int, action: str, frames: int = SPEED, opp_action: str = "STAY") -> GameState:
    """自分の行動を frames コマ続け、相手は opp_action を続けたときの状態（移動は最初のコマだけ指示し、以降は続行）"""
    mv, act = parse(action)
    t = s.copy(light=True)
    for k in range(frames):
        a = action if k == 0 else mv  # 操作は最初のコマだけ、移動は続ける
        t = step(t, a, opp_action) if me == 0 else step(t, opp_action, a)
        if t.done():
            break
    return t


def survivable_moves(s: GameState, me: int, frames: int = SPEED) -> List[Tuple[str, GameState]]:
    """生存可能な移動候補（先読み後に生きていて、逃げ込めるマスが 1 つ以上ある）。無ければ全候補を返す（最善を尽くす）"""
    cands = []
    for a in legal_actions(s, me):
        if "/" in a:
            continue  # 守備は移動だけ
        t = lookahead(s, me, a, frames)
        cands.append((a, t))
    ok = [(a, t) for a, t in cands if t.players[me].alive and (len(escape_area(t, me)[0]) > 0 or t.done())]
    return ok or cands


def choose_defense(s: GameState, me: int, weights: Dict[str, float] = None, frames: int = SPEED) -> Tuple[str, Dict[str, float]]:
    weights = weights or DEFAULT_WEIGHTS
    best, best_score, best_feats = "STAY", -1e18, {}
    for a, t in survivable_moves(s, me, frames):
        f = defense_features(t, me)
        sc = defense_score(f, weights)
        if sc > best_score:
            best, best_score, best_feats = a, sc, f
    return best, best_feats
