# -*- coding: utf-8 -*-
"""Safety features, temporal reachability and bounded simultaneous min-max.

Refuge features are conservative fixed-action forecasts. Only bounded_minimax
uses all legal joint actions, and its certificate ends at its stated horizon.
"""
from typing import Dict, Tuple, Set, Optional, List
from .constants import COLS, ROWS, FIRE, SPEED, DIRS, in_board, is_pillar
from .state import GameState

INF = 10 ** 9
_DIRS = [("U", 0, -1), ("D", 0, 1), ("L", -1, 0), ("R", 1, 0)]
_PILLAR = [[is_pillar(c, r) for r in range(ROWS)] for c in range(COLS)]


def burn_schedule(state: GameState, now: int):
    """First ignition under fixed future actions, including flights and chain delay.

    Unlike the old union-find approximation, rays are recomputed after each
    explosion. This is a forecast, NOT adversarial safety certification.
    """
    from .temporal import forecast
    tl = forecast(state)
    return tl.first, tl.bomb_tiles


def first_explosion(state: GameState) -> int:
    """最初の爆発（または燃えている炎）までのコマ数。無ければ INF"""
    now = state.frame
    budget = INF
    for b in state.bombs:
        if not b.held and 0 <= b.explode_at:
            budget = min(budget, b.explode_at - now)
    for (until, _) in state.flames.values():
        budget = min(budget, until - now)
    from .constants import FUSE
    for b in state.bombs:
        if b.fly_to is not None:
            when = b.explode_at if b.explode_at >= b.land_at else b.land_at + FUSE
            budget = min(budget, when-now)
    return max(0, budget)


def escape_area(state: GameState, i: int, margin: int = 0, max_tiles: Optional[int] = None, delay: int = 0):
    """Conservative refuge feature, with one label per FIRST departure direction.

    Distinct first departures are alternatives, not vertex-disjoint paths.
    Use temporal.survival for waiting/re-entry after flames have expired.
    """
    from collections import deque
    from .temporal import state_signature
    key = (state_signature(state), i, margin, max_tiles, delay)
    cache = getattr(state, '_areas', {})
    if key in cache: return cache[key]
    p = state.players[i]
    now = state.frame
    L, bomb_tiles = burn_schedule(state, now)
    budget = first_explosion(state)
    start = p.tile()
    initial = max(delay, p.stun_until-now, p.lag_until-now, 0)
    if p.prog: initial += SPEED-p.prog
    dist, first, safe, routes = {start: initial}, {start: ''}, set(), set()
    limit = budget
    if max_tiles is not None: limit = min(limit, max_tiles * SPEED)
    queue = deque([(start, initial, '')]) if p.alive else deque()
    visited = {start}
    while queue:
        cell, cost, direction = queue.popleft()
        if cell not in L:
            safe.add(cell)
            if direction: routes.add(direction)
        # Until the halfway crossing, the source tile remains occupied.
        if now + cost + SPEED//2 - 1 + margin >= L.get(cell, INF): continue
        arrival = cost + SPEED
        if arrival > limit: continue
        for name, dx, dy in _DIRS:
            nxt = (cell[0]+dx, cell[1]+dy)
            label = direction or name
            if (not in_board(*nxt) or is_pillar(*nxt) or nxt in bomb_tiles
                    or nxt == start or nxt in visited): continue
            if now + arrival + margin >= L.get(nxt, INF): continue
            visited.add(nxt)
            if arrival < dist.get(nxt, INF):
                dist[nxt], first[nxt] = arrival, label
            queue.append((nxt, arrival, label))
    # Check each initial departure independently. Stop as soon as ONE refuge
    # is found; unlike the old shortest-path tree this preserves merging routes.
    routes = set()
    for name, dx, dy in _DIRS:
        cell = (start[0]+dx, start[1]+dy)
        at = initial+SPEED
        if (not in_board(*cell) or is_pillar(*cell) or cell in bomb_tiles or at > limit
                or now+initial+SPEED//2-1+margin >= L.get(start, INF)
                or now+at+margin >= L.get(cell, INF)): continue
        pending, seen = deque([(cell, at)]), {start, cell}
        while pending:
            cur, cost = pending.popleft()
            if cur not in L:
                routes.add(name)
                break
            if cost+SPEED > limit or now+cost+SPEED//2-1+margin >= L.get(cur, INF): continue
            for _, xx, yy in _DIRS:
                nxt = (cur[0]+xx, cur[1]+yy)
                if (nxt in seen or not in_board(*nxt) or is_pillar(*nxt) or nxt in bomb_tiles
                        or now+cost+SPEED+margin >= L.get(nxt, INF)): continue
                seen.add(nxt)
                pending.append((nxt, cost+SPEED))
    result = safe, {'budget': budget, 'dist': dist, 'first': first, 'L': L,
                    'route_directions': routes}
    cache[key] = result
    state._areas = cache
    return result


def escape_routes(state: GameState, i: int, margin: int = 0) -> int:
    """逃走路の数: 最初の一歩の方向のうち、その先に逃げ込めるマスがあるものの数（0〜4）"""
    safe, info = escape_area(state, i, margin=margin)
    return len(info["route_directions"])


def time_slack(state: GameState, i: int) -> int:
    """時間余裕: いるマスが燃え始めるまでのコマ数（燃える予定が無ければ INF）"""
    p = state.players[i]
    L, _ = burn_schedule(state, state.frame)
    lt = L.get(p.tile())
    return INF if lt is None else lt - state.frame


def in_danger(state: GameState, i: int) -> bool:
    return time_slack(state, i) < INF


def on_own_blast_line(state: GameState, i: int) -> bool:
    """自分の爆弾の爆風線上（誘爆は考えない）にいるか"""
    c0, r0 = state.players[i].tile()
    for b in state.bombs:
        if b.owner != i or not b.on_ground() or b.explode_at < 0:
            continue
        if (b.c, b.r) == (c0, r0):
            return True
        for _, dx, dy in _DIRS:
            c, r = b.c, b.r
            for _ in range(FIRE):
                c += dx
                r += dy
                if not (0 <= c < COLS and 0 <= r < ROWS) or _PILLAR[c][r]:
                    break
                if (c, r) == (c0, r0):
                    return True
                if state.bomb_at(c, r) is not None:
                    break
    return False


def reachable_tiles(state: GameState, i: int, frames: int) -> Set[Tuple[int, int]]:
    """危険を無視して frames コマ以内に着けるマス（将来の移動自由度の目安）"""
    c0, r0 = state.players[i].tile()
    bomb_tiles = {(b.c, b.r) for b in state.bombs if b.on_ground()}
    seen = {(c0, r0)}
    frontier = [(c0, r0)]
    steps = frames // SPEED
    for _ in range(steps):
        nxt = []
        for (c, r) in frontier:
            for _, dx, dy in _DIRS:
                cc, rr = c + dx, r + dy
                if (0 <= cc < COLS and 0 <= rr < ROWS) and not _PILLAR[cc][rr] and (cc, rr) not in bomb_tiles and (cc, rr) not in seen:
                    seen.add((cc, rr))
                    nxt.append((cc, rr))
        frontier = nxt
    return seen


def bounded_minimax(state, me, action=None, frames=2, max_nodes=256):
    """Finite-horizon ∃my action ∀opponent action, using the actual engine.

    All legal operations (placement, kick, punch, pickup, throw) are included.
    Returns safe/unsafe/unknown; budget exhaustion is NEVER a safe certificate.
    'safe' means alive through `frames` only, not through all future explosions.
    """
    from .actions import legal_actions
    from .engine import step
    from .temporal import state_signature
    if frames < 0 or max_nodes < 1: raise ValueError('invalid search budget')
    nodes, memo = 0, {}
    def search(s, depth, forced=None):
        nonlocal nodes
        if not s.players[me].alive: return 'unsafe'
        if s.done() or depth == 0: return 'safe'
        key = (state_signature(s), depth, forced)
        if key in memo: return memo[key]
        if nodes >= max_nodes: return 'unknown'
        mine = [forced] if forced is not None else legal_actions(s, me)
        theirs = legal_actions(s, 1-me)
        any_unknown = False
        for a in mine:
            worst = 'safe'
            for b in theirs:
                if nodes >= max_nodes:
                    worst = 'unknown'
                    break
                nodes += 1
                t = step(s, a, b) if me == 0 else step(s, b, a)
                status = search(t, depth-1)
                if status == 'unsafe':
                    worst = 'unsafe'
                    break
                if status == 'unknown': worst = 'unknown'
            if worst == 'safe':
                memo[key] = 'safe'
                return 'safe'
            any_unknown |= worst == 'unknown'
        result = 'unknown' if any_unknown else 'unsafe'
        memo[key] = result
        return result
    status = search(state.copy(light=True), frames, action)
    return {'status': status, 'frames': frames, 'nodes': nodes,
            'scope': 'all_legal_joint_actions_finite_horizon'}
