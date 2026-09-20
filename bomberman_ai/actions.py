# -*- coding: utf-8 -*-
"""行動の表現と合法行動。
行動は文字列 "<移動>/<操作>"。移動 = STAY/U/D/L/R、操作 = なし/BOMB/PUNCH/PICKUP/THROW。例: "U", "R/BOMB", "STAY/PUNCH"。
  - 移動先に地面の爆弾があれば、その方向への移動は「キック」になる（移動はしない）
  - BOMB: いまのマスに設置（同時設置数 MAX_BOMBS まで、同じマスに2個は不可）
  - PUNCH: 向いている隣のマスの爆弾を PUNCH_DIST マス先へ飛ばす
  - PICKUP: 乗っている爆弾を抱える（マスの中心にいる時だけ）。抱えている間は爆発しない
  - THROW: 抱えた爆弾を向いている方向へ THROW_DIST マス投げる。着地からカウント再開（FUSE）"""
from typing import List, Tuple, Optional
from .constants import DIRS, MAX_BOMBS, in_board, is_pillar

MOVES = ["STAY", "U", "D", "L", "R"]
ACTS = [None, "BOMB", "PUNCH", "PICKUP", "THROW"]


def parse(action: str) -> Tuple[str, Optional[str]]:
    if "/" in action:
        m, a = action.split("/", 1)
        return m, (a or None)
    return action, None


def dir_name(dx: int, dy: int) -> str:
    for k, v in DIRS.items():
        if v == (dx, dy):
            return k
    return "STAY"


def legal_actions(state, i: int) -> List[str]:
    """プレイヤー i の合法行動（気絶中は STAY のみ、硬直中は移動不可）"""
    p = state.players[i]
    if not p.alive:
        return ["STAY"]
    t = state.frame + 1
    if t <= p.stun_until:
        return ["STAY"]
    moves = ["STAY"]
    if t > p.lag_until:
        if p.prog == 0:
            for d, (dx, dy) in DIRS.items():
                c, r = p.c + dx, p.r + dy
                if in_board(c, r) and not is_pillar(c, r):
                    moves.append(d)  # 爆弾があればキックになる
        else:
            moves = ["STAY", dir_name(p.dc, p.dr), dir_name(-p.dc, -p.dr)]  # 移動中は続行か反転だけ
    acts: List[Optional[str]] = [None]
    own = sum(1 for b in state.bombs if b.owner == i)
    tc, tr = p.tile()
    if p.holding is None and own < MAX_BOMBS and state.bomb_at(tc, tr) is None and t > p.lag_until:
        acts.append("BOMB")
    if p.holding is not None and t > p.lag_until:
        acts.append("THROW")
    if p.holding is None and p.prog == 0 and t > p.lag_until:
        fx, fy = DIRS[p.face]
        if state.bomb_at(p.c + fx, p.r + fy) is not None:
            acts.append("PUNCH")
        if state.bomb_at(p.c, p.r) is not None:
            acts.append("PICKUP")
    out = []
    for m in moves:
        for a in acts:
            if a in ("PUNCH", "PICKUP", "THROW") and m != "STAY":
                continue  # 操作系は立ち止まって行う（単純化）
            out.append(m if a is None else m + "/" + a)
    return out
