# -*- coding: utf-8 -*-
"""Safety Solver: 爆発時刻と移動速度を考慮して「逃げ込めるマス」を求める（動画解析の escape.py と同じ考え方）。

考え方（時間つき安全地帯）:
  - 各マスが燃え始める時刻 L を、地面の爆弾の爆発予定と爆風の届く範囲から作る。爆風でつながる爆弾は最も早い爆弾に合わせて爆発する
    （誘爆の遅れ CHAIN_DELAY は安全側に無視）。いま燃えているマスは L = 今。
  - 最初の爆発までの時間（budget）内に、1 マス SPEED コマで走って着ける場所のうち、通り道のどのマスも
    燃え始める MARGIN コマ前までに通り抜けられ、着いた先が爆風線上でないマスを「逃げ込めるマス」とする。
  - 抱えられている爆弾・飛んでいる爆弾は位置が確定しないので、爆風線には入れない（攻撃側はこれを利用できる）。
  - これは「相手が何もしない」前提の安全であり、必ず生き残れる保証ではない（相手のキック・パンチ・投げで変わる）。
返り値は集合と付随情報。決定論的。移動コストが一定なので幅優先探索で解く（速さのため）。"""
from typing import Dict, Tuple, Set, Optional, List
from .constants import COLS, ROWS, FIRE, SPEED, DIRS, in_board, is_pillar
from .state import GameState

INF = 10 ** 9
_DIRS = [("U", 0, -1), ("D", 0, 1), ("L", -1, 0), ("R", 1, 0)]
_PILLAR = [[is_pillar(c, r) for r in range(ROWS)] for c in range(COLS)]


def burn_schedule(state: GameState, now: int) -> Tuple[Dict[Tuple[int, int], int], Set[Tuple[int, int]]]:
    """各マスが燃え始める時刻 L と、地面の爆弾のマス（通れない）を返す。同じ状態では結果をキャッシュする"""
    key = (now, len(state.flames), tuple((b.id, b.c, b.r, b.explode_at, b.held, b.fly_to) for b in state.bombs))
    cache = getattr(state, "_bs", None)
    if cache is not None and cache[0] == key:
        return cache[1], cache[2]
    bombs = [b for b in state.bombs if b.on_ground() and b.explode_at >= 0]
    tile_of = {(b.c, b.r): i for i, b in enumerate(bombs)}
    lines: List[List[Tuple[int, int]]] = []
    for b in bombs:
        ln = [(b.c, b.r)]
        for _, dx, dy in _DIRS:
            c, r = b.c, b.r
            for _ in range(FIRE):
                c += dx
                r += dy
                if not (0 <= c < COLS and 0 <= r < ROWS) or _PILLAR[c][r]:
                    break
                ln.append((c, r))
                if (c, r) in tile_of:
                    break
        lines.append(ln)
    parent = list(range(len(bombs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, ln in enumerate(lines):
        for t in ln:
            j = tile_of.get(t)
            if j is not None and j != i:
                parent[find(i)] = find(j)
    gt: Dict[int, int] = {}
    for i, b in enumerate(bombs):
        g = find(i)
        gt[g] = min(gt.get(g, INF), b.explode_at)
    L: Dict[Tuple[int, int], int] = {}
    for i, ln in enumerate(lines):
        v = gt[find(i)]
        for t in ln:
            if v < L.get(t, INF):
                L[t] = v
    for t in state.flames:
        L[t] = min(L.get(t, INF), now)
    bt = set(tile_of.keys())
    try:
        state._bs = (key, L, bt)
    except Exception:
        pass
    return L, bt


def first_explosion(state: GameState) -> int:
    """最初の爆発（または燃えている炎）までのコマ数。無ければ INF"""
    now = state.frame
    budget = INF
    for b in state.bombs:
        if b.on_ground() and 0 <= b.explode_at:
            budget = min(budget, b.explode_at - now)
    for (until, _) in state.flames.values():
        budget = min(budget, until - now)
    return budget


def escape_area(state: GameState, i: int, margin: int = 0, max_tiles: Optional[int] = None, delay: int = 0):
    """プレイヤー i が逃げ込めるマスの集合と情報 dict(budget, dist, first, L)。
    dist: 各マスへの到達コマ数、first: そのマスへ最短で行くときの最初の方向（逃走路の数え上げに使う）。
    delay = 反応の遅れ（コマ）。margin = 燃え始めの何コマ前までに通り抜ける必要があるか（実戦の余裕。シミュレータ内は 0 で厳密）"""
    p = state.players[i]
    now = state.frame
    L, bomb_tiles = burn_schedule(state, now)
    budget = first_explosion(state)
    c0, r0 = p.tile()
    start_cost = (SPEED - p.prog) if p.prog else 0
    dist: Dict[Tuple[int, int], int] = {(c0, r0): start_cost}
    first: Dict[Tuple[int, int], str] = {(c0, r0): ""}
    safe: Set[Tuple[int, int]] = set()
    limit = budget - delay
    if max_tiles is not None:
        limit = min(limit, max_tiles * SPEED)
    frontier = [(c0, r0)]
    a = start_cost
    while frontier:
        nxt = []
        for (c, r) in frontier:
            if (c, r) not in L:
                safe.add((c, r))
            a2 = a + SPEED
            if a2 > limit:
                continue
            f0 = first[(c, r)]
            for name, dx, dy in _DIRS:
                cc, rr = c + dx, r + dy
                if not (0 <= cc < COLS and 0 <= rr < ROWS) or _PILLAR[cc][rr] or (cc, rr) in bomb_tiles or (cc, rr) in dist:
                    continue
                lt2 = L.get((cc, rr))
                if lt2 is not None and (now + delay + a2) > lt2 - margin:
                    continue
                dist[(cc, rr)] = a2
                first[(cc, rr)] = f0 or name
                nxt.append((cc, rr))
        frontier = nxt
        a += SPEED
    return safe, {"budget": budget, "dist": dist, "first": first, "L": L}


def escape_routes(state: GameState, i: int, margin: int = 0) -> int:
    """逃走路の数: 最初の一歩の方向のうち、その先に逃げ込めるマスがあるものの数（0〜4）"""
    safe, info = escape_area(state, i, margin=margin)
    return len({info["first"][t] for t in safe if info["first"].get(t)})


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
