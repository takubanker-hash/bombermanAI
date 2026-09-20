# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bomberman_ai.constants import *
from bomberman_ai.state import GameState, Bomb
from bomberman_ai.safety import escape_area, escape_routes, time_slack, INF, first_explosion


def test_no_bombs_everything_reachable_is_safe():
    s = GameState.initial(p0=(0, 0))
    safe, info = escape_area(s, 0)
    assert (0, 0) in safe and (12, 10) in safe and (1, 1) not in safe  # 柱は入らない
    assert info["budget"] == INF and time_slack(s, 0) == INF


def test_bomb_line_is_unsafe_and_side_tiles_safe():
    s = GameState.initial(p0=(0, 0), p1=(12, 10))
    s.bombs.append(Bomb(id=0, c=0, r=1, owner=1, placed=0, explode_at=FUSE))
    safe, info = escape_area(s, 0)
    assert (0, 0) not in safe and (0, 5) not in safe  # 爆風線上
    assert (2, 0) in safe  # 横に逃げれば安全（行0 は列1 が柱でないので (1,0) を通れる）
    assert info["budget"] == FUSE


def test_short_fuse_limits_reach():
    s = GameState.initial(p0=(0, 0), p1=(12, 10))
    s.bombs.append(Bomb(id=0, c=0, r=1, owner=1, placed=0, explode_at=SPEED * 2 + 1))  # 2歩ぶんの時間
    safe, info = escape_area(s, 0)
    assert (2, 0) in safe and (3, 0) not in safe  # 3歩目には間に合わない


def test_escape_routes_count():
    s = GameState.initial(p0=(6, 4), p1=(12, 10))
    assert escape_routes(s, 0) == 4
    s.bombs.append(Bomb(id=0, c=6, r=5, owner=1, placed=0, explode_at=FUSE))  # 下に爆弾
    assert escape_routes(s, 0) == 3  # 左右、および上へ出て横にそれる道。下は爆弾で塞がる


def test_chain_uses_earliest_timer():
    s = GameState.initial(p0=(0, 0), p1=(12, 10))
    s.bombs.append(Bomb(id=0, c=4, r=0, owner=1, placed=0, explode_at=30))
    s.bombs.append(Bomb(id=1, c=0, r=1, owner=1, placed=0, explode_at=FUSE))  # (0,1) は (4,0) の爆風線上ではないが (0,0)-(3,0) は共通
    safe, info = escape_area(s, 0)
    L = info["L"]
    assert L[(0, 0)] == 30  # 早い方の爆弾に合わせて燃える（(0,0) は両方の線上）
