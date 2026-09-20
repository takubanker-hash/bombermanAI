# -*- coding: utf-8 -*-
"""1コマ進める処理。同じ状態と行動から必ず同じ結果になる（乱数を使わない）。

1コマ内の処理順序（SPEC.md「処理順序」と一致させること）:
  1. コマ番号を +1 する（t）
  2. 消える時刻が来た爆炎を消す
  3. 飛んでいる爆弾が着地する（着地マスにいる人は気絶。投げた爆弾は着地からカウント再開）
  4. 滑っている爆弾が進む（次のマスが塞がっていれば止まる）
  5. 爆発時刻が来た爆弾が爆発する（爆風は柱で止まり、地面の爆弾に当たるとその爆弾は 10 コマ後に爆発、爆風はそこで止まる）
  6. 両プレイヤーの操作（BOMB/PUNCH/PICKUP/THROW）を 0,1 の順に適用（同じマスへの同時設置は 0 が優先）
  7. 両プレイヤーの移動を同時に適用（プレイヤー同士はすり抜ける。移動先の爆弾はキック）
  8. 爆炎のマスにいる人は死亡。両方なら引き分け。制限時間で引き分け"""
from typing import Tuple
from .constants import (COLS, ROWS, FUSE, FIRE, BURN, CHAIN_DELAY, SPEED, KICK_STEP, PUNCH_DIST, THROW_DIST,
                        FLY_FRAMES, STUN, ACTION_LAG, MAX_BOMBS, TIME_LIMIT, PICKUP_FRAMES, DIRS, in_board, is_pillar)
from .state import GameState, Bomb
from .actions import parse


def step(state: GameState, a0: str, a1: str) -> GameState:
    s = state.copy()
    if s.done():
        return s
    s.frame += 1
    t = s.frame
    # 2. 爆炎
    s.flames = {k: v for k, v in s.flames.items() if v[0] > t}
    # 3. 着地
    for b in s.bombs:
        if b.fly_to is not None and b.land_at <= t:
            b.c, b.r = _free_landing(s, b.fly_to, b.slide)  # slide に飛行方向を入れてある
            b.fly_to = None
            b.slide = (0, 0)
            b.slide_prog = 0
            if b.explode_at < 0 or b.explode_at < t:
                b.explode_at = t + FUSE  # 投げた物はカウント再開。飛行中に時刻が来ていた物も着地から
            for j, p in enumerate(s.players):
                if p.alive and p.tile() == (b.c, b.r):
                    p.stun_until = t + STUN
                    _log(s, f"{t}: P{j} stunned by bomb {b.id}")
    # 4. 滑り
    for b in s.bombs:
        if b.slide != (0, 0) and b.on_ground():
            b.slide_prog += 1
            if b.slide_prog >= KICK_STEP:
                nc, nr = b.c + b.slide[0], b.r + b.slide[1]
                if s.blocked(nc, nr) or any(p.alive and p.tile() == (nc, nr) for p in s.players):
                    b.slide = (0, 0)
                    b.slide_prog = 0
                else:
                    b.c, b.r = nc, nr
                    b.slide_prog = 0
    # 5. 爆発
    _explode(s, t)
    # 6. 操作
    mv = [parse(a0), parse(a1)]
    for i, p in enumerate(s.players):
        act = mv[i][1]
        if not p.alive or act is None or t <= p.stun_until or t <= p.lag_until:
            continue
        if act == "BOMB":
            tc, tr = p.tile()
            if p.holding is None and sum(1 for b in s.bombs if b.owner == i) < MAX_BOMBS and s.bomb_at(tc, tr) is None:
                s.bombs.append(Bomb(id=s.next_bomb_id, c=tc, r=tr, owner=i, placed=t, explode_at=t + FUSE))
                s.next_bomb_id += 1
        elif act == "PUNCH" and p.prog == 0 and p.holding is None:
            fx, fy = DIRS[p.face]
            b = s.bomb_at(p.c + fx, p.r + fy)
            if b is not None:
                _launch(b, (fx, fy), PUNCH_DIST, t, reset=False)
                p.lag_until = t + ACTION_LAG
                _log(s, f"{t}: P{i} punched bomb {b.id}")
        elif act == "PICKUP" and p.prog == 0 and p.holding is None:
            b = s.bomb_at(p.c, p.r)
            if b is not None:
                b.held = True
                b.explode_at = -1
                b.slide = (0, 0)
                p.holding = b.id
                p.lag_until = t + PICKUP_FRAMES
        elif act == "THROW" and p.holding is not None:
            b = next((x for x in s.bombs if x.id == p.holding), None)
            if b is not None:
                b.held = False
                b.c, b.r = p.tile()
                _launch(b, DIRS[p.face], THROW_DIST, t, reset=True)
                _log(s, f"{t}: P{i} threw bomb {b.id}")
            p.holding = None
            p.lag_until = t + ACTION_LAG
    # 7. 移動（同時）
    for i, p in enumerate(s.players):
        m = mv[i][0]
        if not p.alive or t <= p.stun_until:
            continue
        if p.prog == 0:
            if m in DIRS and t > p.lag_until:
                dx, dy = DIRS[m]
                p.face = m
                nc, nr = p.c + dx, p.r + dy
                if not in_board(nc, nr) or is_pillar(nc, nr):
                    continue
                b = s.bomb_at(nc, nr)
                if b is not None:
                    if b.slide == (0, 0):
                        b.slide = (dx, dy)
                        b.slide_prog = 0
                        _log(s, f"{t}: P{i} kicked bomb {b.id}")
                    continue
                p.dc, p.dr, p.prog = dx, dy, 1
        else:
            if m in DIRS and DIRS[m] == (-p.dc, -p.dr):  # 反転
                p.c, p.r = p.c + p.dc, p.r + p.dr
                p.dc, p.dr = -p.dc, -p.dr
                p.prog = SPEED - p.prog
                p.face = m
            p.prog += 1
            if p.prog >= SPEED:
                p.c, p.r = p.c + p.dc, p.r + p.dr
                p.dc = p.dr = 0
                p.prog = 0
    # 8. 死亡・勝敗
    dead = []
    for i, p in enumerate(s.players):
        if p.alive and p.tile() in s.flames:
            p.alive = False
            owner = s.flames[p.tile()][1]
            p.cause_of_death = "own_bomb" if owner == i else "opp_bomb"
            dead.append(i)
            _log(s, f"{t}: P{i} died ({p.cause_of_death})")
    if len(dead) == 2:
        s.winner = -1
    elif len(dead) == 1:
        s.winner = 1 - dead[0]
    elif t >= TIME_LIMIT:
        s.winner = -1
    return s


def _log(s: GameState, msg: str):
    if s.keep_log:
        s.log.append(msg)


def _free_landing(s: GameState, target: Tuple[int, int], d: Tuple[int, int]) -> Tuple[int, int]:
    """着地先が柱か爆弾なら同じ方向へ 1 マスずつ先へ（仮定）。盤の端まで塞がっていれば手前へ戻る"""
    c, r = target
    for _ in range(COLS + ROWS):
        if in_board(c, r) and not is_pillar(c, r) and s.bomb_at(c, r) is None:
            return (c, r)
        nc, nr = c + d[0], r + d[1]
        if not in_board(nc, nr):
            break
        c, r = nc, nr
    c, r = target
    for _ in range(COLS + ROWS):
        if in_board(c, r) and not is_pillar(c, r) and s.bomb_at(c, r) is None:
            return (c, r)
        c, r = c - d[0], r - d[1]
    return target


def _launch(b: Bomb, d: Tuple[int, int], dist: int, t: int, reset: bool):
    tc = max(0, min(COLS - 1, b.c + d[0] * dist))  # 盤外は端で止まる（仮定）
    tr = max(0, min(ROWS - 1, b.r + d[1] * dist))
    b.fly_to = (tc, tr)
    b.slide = d
    b.slide_prog = 0
    b.land_at = t + FLY_FRAMES
    if reset:
        b.explode_at = -1


def _explode(s: GameState, t: int):
    exploding = [b for b in s.bombs if b.on_ground() and 0 <= b.explode_at <= t]
    if not exploding:
        return
    ids = {b.id for b in exploding}
    for b in exploding:
        _add_flame(s, b.c, b.r, t + BURN, b.owner)
        for dx, dy in DIRS.values():
            for k in range(1, FIRE + 1):
                c, r = b.c + dx * k, b.r + dy * k
                if not in_board(c, r) or is_pillar(c, r):
                    break
                _add_flame(s, c, r, t + BURN, b.owner)
                other = s.bomb_at(c, r)
                if other is not None:
                    if other.id not in ids and other.explode_at >= 0:
                        other.explode_at = min(other.explode_at, t + CHAIN_DELAY)  # 誘爆
                    break  # 爆風は爆弾で止まる
        _log(s, f"{t}: bomb {b.id} (P{b.owner}) exploded at ({b.c},{b.r})")
    s.bombs = [b for b in s.bombs if b.id not in ids]


def _add_flame(s: GameState, c: int, r: int, until: int, owner: int):
    cur = s.flames.get((c, r))
    if cur is None or until > cur[0]:
        s.flames[(c, r)] = (until, owner)
