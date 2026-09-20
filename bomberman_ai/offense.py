# -*- coding: utf-8 -*-
"""Attack features: refuge compression, bomb-horizon mobility and interception.

Immediate candidates use one tile of engine lookahead, then a shortlist receives
long fixed-bomb forecasts and all immediate legal opponent responses. Long-term
trap/robust scores are heuristics, not adversarial kill/safety certificates.
"""
from typing import Dict, List, Tuple, Optional
from .constants import FUSE, SPEED, ACTION_LAG, PICKUP_FRAMES, DIRS
from .state import GameState
from .safety import escape_area, time_slack, burn_schedule, bounded_minimax, INF
from .temporal import survival
from .engine import step
from .actions import legal_actions, parse
from .defense import lookahead
from functools import lru_cache
from collections import deque

@lru_cache(maxsize=128)
def _distances(target):
    from .constants import in_board, is_pillar
    dist = {target: 0}
    queue = deque([target])
    while queue:
        cell = queue.popleft()
        for dx, dy in DIRS.values():
            nxt = (cell[0]+dx, cell[1]+dy)
            if nxt not in dist and in_board(*nxt) and not is_pillar(*nxt):
                dist[nxt] = dist[cell]+1
                queue.append(nxt)
    return dist

def navigation_distance(a, b):
    return _distances(b).get(a, 24)


FEATURE_NAMES = ["area_cut", "routes_cut", "future_cut", "chain", "timing", "self_area", "self_dead", "lag_danger", "kill", "robust", "approach", "proximity", "trap", "long_cut", "intercept"]
EXPENSIVE = ("future_cut", "robust")
TOP_K = 4

DEFAULT_WEIGHTS: Dict[str, float] = {
    "area_cut": 1.5, "routes_cut": 1.0, "future_cut": 0.6, "chain": 0.3, "timing": 0.5,
    "self_area": 0.8, "self_dead": -100.0, "lag_danger": -1.5, "kill": 10.0, "robust": 1.0,
    "approach": 0.6, "proximity": 0.4, "trap": 6.0, "long_cut": 1.0, "intercept": 0.8,
}


def _opp_safety(s: GameState, opp: int):
    safe, info = escape_area(s, opp)
    routes = len(info["route_directions"])
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


def response_safety(s, me, action, frames=SPEED):
    """All immediately legal replies, including bomb operations and kicks.

    The reply is issued once; future motion is held for one decision interval.
    Long survival assumes no further operations. This is a scenario score,
    not a min-max certificate through the bomb horizon.
    """
    outcomes = []
    for oa in legal_actions(s, 1-me):
        t = lookahead(s, me, action, frames, opp_action=oa)
        if not t.players[me].alive:
            outcomes.append(False)
        elif t.done():
            outcomes.append(True)
        else:
            refuge = bool(escape_area(t, me)[0])
            outcomes.append(refuge or survival(t, me)['alive'])
    return outcomes


def robustness(s, me, action, frames=SPEED):
    outcomes = response_safety(s, me, action, frames)
    return sum(outcomes) / max(1, len(outcomes))


class Context:
    """判断 1 回ぶんの基準値（候補ごとに計算し直さない）"""

    def __init__(self, s: GameState, me: int, need_future: bool = True):
        self.opp = 1 - me
        self.area0, self.routes0 = _opp_safety(s, self.opp)
        self.future0 = safe_next_moves(s, self.opp) if need_future else 0
        self.long0 = None


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
    (mc, mr), (oc, orr) = s.players[me].tile(), s.players[opp].tile()
    d0 = navigation_distance((mc, mr), (oc, orr))
    (mc2, mr2), (oc2, orr2) = p.tile(), q.tile()
    d1 = navigation_distance((mc2, mr2), (oc2, orr2))
    mv, act = parse(action)
    lag = act in ("PUNCH", "THROW", "PICKUP")
    sl_me = time_slack(t, me)
    lag_danger = 1.0 if (lag and sl_me < ACTION_LAG + PICKUP_FRAMES + SPEED) else 0.0
    f = {
        "area_cut": max(-1.0, min(1.0, (ctx.area0 - area1) / 30.0)),
        "routes_cut": (ctx.routes0 - routes1) / 4.0,
        "future_cut": 0.0,
        "chain": chain,
        "timing": timing,
        "self_area": min(len(self_safe), 30) / 30.0,
        "self_dead": 0.0,
        "lag_danger": lag_danger,
        "kill": 1.0 if not q.alive else 0.0,
        "robust": 1.0,
        "approach": (d0 - d1) / 2.0,
        "proximity": 1.0 - min(d1, 24) / 24.0,
        "trap": 0.0, "long_cut": 0.0, "intercept": 0.0,
    }
    if full:
        add_expensive(s, me, action, f, t, ctx)
    return f, t


def add_expensive(s: GameState, me: int, action: str, f: Dict[str, float], t: GameState, ctx: Context):
    opp = 1 - me
    future1 = safe_next_moves(t, opp) if t.players[opp].alive else 0
    f["future_cut"] = max(0, ctx.future0 - future1) / 4.0
    f["robust"] = robustness(s, me, action)
    # Both forecasts end at the SAME absolute frame, avoiding horizon bias.
    from .temporal import forecast_horizon
    # Counterfactual has the same elapsed opponent waiting as the action.
    # Comparing t+6 to the original t falsely rewarded STAY without any bombs.
    control = lookahead(s, me, 'STAY', t.frame-s.frame)
    end = max(control.frame + forecast_horizon(control), t.frame + forecast_horizon(t))
    base = survival(control, opp, end-control.frame)
    after = survival(t, opp, end-t.frame)
    f['long_cut'] = (base['count']-after['count']) / max(1, base['count'])
    f['trap'] = float(not after['alive'] and t.players[opp].alive)
    # A trajectory-dependent signal for targeted moving bombs, not bomb count.
    oc, orr = t.players[opp].tile()
    pending = max([0] + [p.queued['at']-t.frame for p in t.players if p.queued])
    interception_state = lookahead(t, me, 'STAY', pending) if pending else t
    for b in interception_state.bombs:
        if b.fly_to is not None:
            distance = abs(b.fly_to[0]-oc)+abs(b.fly_to[1]-orr)
            f['intercept'] = max(f['intercept'], 1.0/(1+distance))
        elif b.slide != (0, 0):
            dx, dy = b.slide
            aligned = (dx and b.r == orr and (oc-b.c)*dx > 0) or (dy and b.c == oc and (orr-b.r)*dy > 0)
            if aligned: f['intercept'] = max(f['intercept'], 0.5)
    # Immediate exact min-max guard; unknown is explicitly retained as unknown.
    if time_slack(s, me) <= SPEED:
        verdict = bounded_minimax(s, me, action, frames=2, max_nodes=128)
        if verdict['status'] == 'unsafe': f['self_dead'] = 1.0



def offense_score(feats: Dict[str, float], weights: Dict[str, float]) -> float:
    return sum(weights.get(k, 0.0) * v for k, v in feats.items())


def offense_candidates(s: GameState, me: int) -> List[str]:
    """攻撃の候補: 設置を伴う移動・その場設置・キック（爆弾へ向かう移動）・パンチ・拾う・投げる・待機・移動"""
    return legal_actions(s, me)


def tactical_preview(s, me, action):
    """Short preparation plans: turn→punch and pickup→throw.

    Only the first legal action is returned to the game; replan every decision.
    The preview is a heuristic, never a promised opponent trajectory.
    """
    t = lookahead(s, me, action)
    if t.done(): return None
    mv, op = parse(action)
    if op == 'PICKUP':
        wait = max(0, t.players[me].lag_until-t.frame)
        t = lookahead(t, me, 'STAY', wait) if wait else t
        if 'STAY/THROW' in legal_actions(t, me):
            return lookahead(t, me, 'STAY/THROW', SPEED)
    if mv in DIRS and op is None and t.players[me].face != s.players[me].face:
        if 'STAY/PUNCH' in legal_actions(t, me):
            return lookahead(t, me, 'STAY/PUNCH', SPEED)
    return None


def rank_candidates(s: GameState, me: int, weights: Dict[str, float], extra=None, top_k: int = TOP_K):
    """Compare candidates at equal refinement fidelity; never append cheap scores.

    Keep operation/kick candidates in the shortlist even if cheap scoring misses
    their distant landing/explosion. An excluded candidate cannot win via an
    optimistic placeholder robust=1 value.
    """
    ctx = Context(s, me, need_future=bool(top_k))
    cheap = []
    for a in offense_candidates(s, me):
        f, t = offense_features(s, me, a, ctx, full=False)
        if f['self_dead']: continue
        sc = offense_score(f, weights) + (extra(f, t, a) if extra else 0.0)
        cheap.append((sc, a, f, t))
    cheap.sort(key=lambda x: -x[0])
    if not top_k: return cheap
    selected = list(cheap[:top_k])
    names = {x[1] for x in selected}
    for row in cheap:
        a = row[1]
        mv, op = parse(a)
        p = s.players[me]
        kick = mv in DIRS and s.bomb_at(p.c+DIRS[mv][0], p.r+DIRS[mv][1]) is not None
        if a not in names and (op in ('PUNCH', 'PICKUP', 'THROW') or kick):
            selected.append(row)
            names.add(a)
    out = []
    for _, a, f, t in selected:
        add_expensive(s, me, a, f, t, ctx)
        if f['self_dead']: continue
        if f['self_area'] == 0 and not survival(t, me)['alive']: continue
        sc = offense_score(f, weights) + (extra(f, t, a) if extra else 0.0)
        preview = tactical_preview(s, me, a)
        if preview is not None and preview.players[me].alive and escape_area(preview, me)[0]:
            _, routes = _opp_safety(preview, 1-me)
            sc += 0.15 * max(0, ctx.routes0-routes)  # bounded preparation bonus
        out.append((sc, a, f, t))
    out.sort(key=lambda x: -x[0])
    return out


def choose_offense(s: GameState, me: int, weights: Dict[str, float] = None, frames: int = SPEED, with_robust: bool = True) -> Tuple[str, Dict[str, float]]:
    weights = weights or DEFAULT_WEIGHTS
    ranked = rank_candidates(s, me, weights, top_k=TOP_K if with_robust else 0)
    if not ranked:
        return "STAY", {}
    sc, a, f, t = ranked[0]
    return a, f
