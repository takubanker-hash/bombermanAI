# -*- coding: utf-8 -*-
"""攻撃評価関数 F。特徴量の計算・重み・行動選択を分離している。

候補: 設置（その場・移動しながら）、キック（爆弾へ向かう移動）、パンチ、拾う、投げる、待機・移動。
各候補を SPEED コマ先読み（相手は待機）し、相手の安全の減り方と自分の生存を特徴量にする。
速さのため 2 段階: 安い特徴で全候補を採点し、上位 TOP_K だけ高価な特徴（future_cut・robust）を計算する。
特徴量:
  area_cut      相手の逃げ込めるマスの減少 / 30
  routes_cut    相手の逃走路の減少 / 4
  future_cut    相手の「安全な次の一歩」の減少 / 4（相手の各移動を 1 歩先読みして安全か数える）[高価]
  chain         候補で置いた・動かした爆弾が既存の爆弾の爆風線につながる（誘爆）なら 1
  timing        相手のマスが燃えるまでの近さ 1 - slack/FUSE（燃える予定が無ければ 0）
  self_area     自分の逃げ込めるマス / 30（生存可能性）
  self_dead     先読みで自分が死ぬなら 1（拒否）
  lag_danger    硬直を伴う行動で、硬直中に自分のマスが燃えるなら 1
  kill          先読みで相手が死ぬなら 1
  robust        相手がどう動いても自分に逃げ場が残る割合（相手の行動を固定した安全を保証と扱わないための項）[高価]"""
from typing import Dict, List, Tuple, Optional
from .constants import FUSE, SPEED, ACTION_LAG, PICKUP_FRAMES
from .state import GameState
from .safety import escape_area, time_slack, burn_schedule, INF
from .engine import step
from .actions import legal_actions, parse
from .defense import lookahead

FEATURE_NAMES = ["area_cut", "routes_cut", "future_cut", "chain", "timing", "self_area", "self_dead", "lag_danger", "kill", "robust"]
EXPENSIVE = ("future_cut", "robust")
TOP_K = 4

DEFAULT_WEIGHTS: Dict[str, float] = {
    "area_cut": 1.0, "routes_cut": 0.8, "future_cut": 0.6, "chain": 0.3, "timing": 0.5,
    "self_area": 0.8, "self_dead": -100.0, "lag_danger": -1.5, "kill": 10.0, "robust": 1.0,
}


def _opp_safety(s: GameState, opp: int):
    safe, info = escape_area(s, opp)
    routes = len({info["first"][t] for t in safe if info["first"].get(t)})
    return len(safe), routes


def safe_next_moves(s: GameState, i: int) -> int:
    """プレイヤー i の移動候補のうち、1 歩先読みして逃げ込めるマスが残る物の数"""
    n = 0
    for a in legal_actions(s, i):
        if "/" in a or a == "STAY":
            continue
        t = lookahead(s, i, a, SPEED)
        if t.players[i].alive and len(escape_area(t, i)[0]) > 0:
            n += 1
    return n


def robustness(s: GameState, me: int, action: str, frames: int = SPEED) -> float:
    """相手の各移動（待機・上下左右）に対して、自分の行動を続けた後に逃げ場が残る割合"""
    opp = 1 - me
    opp_actions = [a for a in legal_actions(s, opp) if "/" not in a]
    if not opp_actions:
        return 1.0
    ok = 0
    mv, act = parse(action)
    for oa in opp_actions:
        t = s.copy(light=True)
        for k in range(frames):
            a = action if k == 0 else mv
            t = step(t, a, oa) if me == 0 else step(t, oa, a)
            if t.done():
                break
        if t.players[me].alive and (t.done() or len(escape_area(t, me)[0]) > 0):
            ok += 1
    return ok / len(opp_actions)


class Context:
    """判断 1 回ぶんの基準値（候補ごとに計算し直さない）"""

    def __init__(self, s: GameState, me: int, need_future: bool = True):
        self.opp = 1 - me
        self.area0, self.routes0 = _opp_safety(s, self.opp)
        self.future0 = safe_next_moves(s, self.opp) if need_future else 0


def offense_features(s: GameState, me: int, action: str, ctx: Optional[Context] = None, frames: int = SPEED,
                     full: bool = True) -> Tuple[Dict[str, float], GameState]:
    """特徴量と先読み後の状態を返す。full=False なら高価な特徴（future_cut, robust）を計算しない（0 と 1 を入れる）"""
    opp = 1 - me
    ctx = ctx or Context(s, me, need_future=full)
    t = lookahead(s, me, action, frames)
    p = t.players[me]
    q = t.players[opp]
    if not p.alive:
        f = {k: 0.0 for k in FEATURE_NAMES}
        f["self_dead"] = 1.0
        return f, t
    area1, routes1 = _opp_safety(t, opp) if q.alive else (0, 0)
    L_all, _ = burn_schedule(t, t.frame)
    chain = 0.0
    mine = [b for b in t.bombs if b.owner == me and b.on_ground()]
    for b in mine:
        lb = L_all.get((b.c, b.r))
        for o in t.bombs:
            if o.id != b.id and o.on_ground() and o.explode_at >= 0 and L_all.get((o.c, o.r)) == lb and lb is not None:
                chain = 1.0
                break
        if chain:
            break
    sl_opp = time_slack(t, opp) if q.alive else 0
    timing = 0.0 if sl_opp >= INF else 1.0 - max(0, min(sl_opp, FUSE)) / FUSE
    self_safe, _ = escape_area(t, me)
    mv, act = parse(action)
    lag = act in ("PUNCH", "THROW", "PICKUP")
    sl_me = time_slack(t, me)
    lag_danger = 1.0 if (lag and sl_me < ACTION_LAG + PICKUP_FRAMES + SPEED) else 0.0
    f = {
        "area_cut": max(0, ctx.area0 - area1) / 30.0,
        "routes_cut": max(0, ctx.routes0 - routes1) / 4.0,
        "future_cut": 0.0,
        "chain": chain,
        "timing": timing,
        "self_area": min(len(self_safe), 30) / 30.0,
        "self_dead": 0.0,
        "lag_danger": lag_danger,
        "kill": 1.0 if not q.alive else 0.0,
        "robust": 1.0,
    }
    if full:
        add_expensive(s, me, action, f, t, ctx)
    return f, t


def add_expensive(s: GameState, me: int, action: str, f: Dict[str, float], t: GameState, ctx: Context):
    opp = 1 - me
    future1 = safe_next_moves(t, opp) if t.players[opp].alive else 0
    f["future_cut"] = max(0, ctx.future0 - future1) / 4.0
    f["robust"] = robustness(s, me, action)


def offense_score(feats: Dict[str, float], weights: Dict[str, float]) -> float:
    return sum(weights.get(k, 0.0) * v for k, v in feats.items())


def offense_candidates(s: GameState, me: int) -> List[str]:
    """攻撃の候補: 設置を伴う移動・その場設置・キック（爆弾へ向かう移動）・パンチ・拾う・投げる・待機・移動"""
    return legal_actions(s, me)


def rank_candidates(s: GameState, me: int, weights: Dict[str, float], extra=None, top_k: int = TOP_K):
    """2 段階評価。extra(feats, t, action) -> 追加得点（統合エージェントが D を足すのに使う）。
    返り値: [(score, action, feats, t)] を得点順に（上位 top_k は高価な特徴込み）"""
    ctx = Context(s, me, need_future=True)
    cheap = []
    for a in offense_candidates(s, me):
        f, t = offense_features(s, me, a, ctx, full=False)
        if f["self_dead"] > 0:
            continue
        sc = offense_score(f, weights) + (extra(f, t, a) if extra else 0.0)
        cheap.append((sc, a, f, t))
    cheap.sort(key=lambda x: -x[0])
    out = []
    for sc, a, f, t in cheap[:top_k]:
        add_expensive(s, me, a, f, t, ctx)
        sc = offense_score(f, weights) + (extra(f, t, a) if extra else 0.0)
        out.append((sc, a, f, t))
    out.sort(key=lambda x: -x[0])
    return out + cheap[top_k:]


def choose_offense(s: GameState, me: int, weights: Dict[str, float] = None, frames: int = SPEED, with_robust: bool = True) -> Tuple[str, Dict[str, float]]:
    weights = weights or DEFAULT_WEIGHTS
    ranked = rank_candidates(s, me, weights, top_k=TOP_K if with_robust else 0)
    if not ranked:
        return "STAY", {}
    sc, a, f, t = ranked[0]
    return a, f
