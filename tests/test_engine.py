# -*- coding: utf-8 -*-
"""主要ルールのテスト（SPEC.md の確認済み・仮定の値と一致することを確かめる）"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bomberman_ai.constants import *
from bomberman_ai.state import GameState, Player, Bomb
from bomberman_ai.engine import step
from bomberman_ai.actions import legal_actions
from bomberman_ai import replay


def run(s, actions):
    for a0, a1 in actions:
        s = step(s, a0, a1)
    return s


def test_move_takes_speed_frames():
    s = GameState.initial()
    for _ in range(SPEED):
        s = step(s, "R", "STAY")
    assert (s.players[0].c, s.players[0].r, s.players[0].prog) == (1, 0, 0)
    assert s.players[1].c == COLS - 1  # 相手は動かない


def test_pillar_blocks():
    s = GameState.initial(p0=(0, 0))
    s = run(s, [("D", "STAY")] * SPEED)  # (0,1)
    s = run(s, [("R", "STAY")] * SPEED)  # (1,1) は柱 → 動かない
    assert (s.players[0].c, s.players[0].r) == (0, 1)


def test_bomb_fuse_and_flame_extent():
    s = GameState.initial(p0=(6, 4), p1=(0, 10))
    s = step(s, "STAY/BOMB", "STAY")
    assert len(s.bombs) == 1 and s.bombs[0].explode_at == s.frame + FUSE
    s = run(s, [("STAY", "STAY")] * (FUSE - 1))
    assert len(s.bombs) == 1
    s = step(s, "STAY", "STAY")
    assert len(s.bombs) == 0 and (6, 4) in s.flames
    # 横: 6±8 → 0..12 のうち柱で止まる（行4は偶数行なので柱なし → 端まで）
    assert (0, 4) in s.flames and (12, 4) in s.flames
    # 縦: 列6は偶数列なので柱なし → 行 0..10 全部（8マス以内: 4-8<0 → 0、4+8>10 → 10）
    assert (6, 0) in s.flames and (6, 10) in s.flames
    assert (7, 5) not in s.flames  # 斜めには出ない
    # 置いた人は自分の爆弾で死ぬ
    assert not s.players[0].alive and s.players[0].cause_of_death == "own_bomb" and s.winner == 1


def test_flame_stops_at_pillar_and_burns_30():
    s = GameState.initial(p0=(0, 10), p1=(12, 10))
    s.bombs.append(Bomb(id=0, c=0, r=1, owner=0, placed=0, explode_at=1))
    s.next_bomb_id = 1
    s = step(s, "STAY", "STAY")  # 爆発（P0 は (0,10) にいて、列0は柱なしなので 8 マス先の (0,9) まで届く）
    assert (0, 9) in s.flames and (0, 10) not in s.flames
    assert (1, 1) not in s.flames  # (1,1) は柱
    assert (2, 1) not in s.flames  # 柱の向こうへは届かない
    assert s.players[0].alive
    s = run(s, [("STAY", "STAY")] * (BURN - 1))
    assert (0, 1) in s.flames
    s = step(s, "STAY", "STAY")
    assert (0, 1) not in s.flames


def test_chain_explosion_delay():
    s = GameState.initial(p0=(0, 10), p1=(12, 10))
    s.bombs.append(Bomb(id=0, c=2, r=0, owner=0, placed=0, explode_at=1))
    s.bombs.append(Bomb(id=1, c=5, r=0, owner=1, placed=0, explode_at=1000))
    s.next_bomb_id = 2
    s = step(s, "STAY", "STAY")
    assert len(s.bombs) == 1 and s.bombs[0].explode_at == s.frame + CHAIN_DELAY
    assert (5, 0) in s.flames and (6, 0) not in s.flames  # 爆風は爆弾で止まる
    s = run(s, [("STAY", "STAY")] * CHAIN_DELAY)
    assert len(s.bombs) == 0 and (8, 0) in s.flames


def test_kick_slides_and_stops():
    s = GameState.initial(p0=(0, 0), p1=(12, 10))
    s.bombs.append(Bomb(id=0, c=1, r=0, owner=1, placed=0, explode_at=10000))
    s.next_bomb_id = 1
    s = step(s, "R", "STAY")  # 右の爆弾をキック。自分は動かない
    assert (s.players[0].c, s.players[0].prog) == (0, 0) and s.bombs[0].slide == (1, 0)
    s = run(s, [("STAY", "STAY")] * KICK_STEP)
    assert s.bombs[0].c == 2
    s = run(s, [("STAY", "STAY")] * (KICK_STEP * 20))
    assert s.bombs[0].c == 12 and s.bombs[0].slide == (0, 0)  # 端で止まる


def test_punch_flies_3_tiles_and_keeps_timer():
    s = GameState.initial(p0=(0, 0), p1=(12, 10))
    s.players[0].face = "R"
    s.bombs.append(Bomb(id=0, c=1, r=0, owner=1, placed=0, explode_at=500))
    s.next_bomb_id = 1
    s = step(s, "STAY/PUNCH", "STAY")
    assert s.bombs[0].fly_to == (4, 0) and s.players[0].lag_until == s.frame + ACTION_LAG
    s = run(s, [("STAY", "STAY")] * FLY_FRAMES)
    assert (s.bombs[0].c, s.bombs[0].r) == (4, 0) and s.bombs[0].explode_at == 500


def test_pickup_throw_resets_fuse_and_stuns():
    s = GameState.initial(p0=(0, 0), p1=(6, 0))
    s.players[0].face = "R"
    s = step(s, "STAY/BOMB", "STAY")
    s = step(s, "STAY/PICKUP", "STAY")
    assert s.players[0].holding == 0 and s.bombs[0].held and s.bombs[0].explode_at == -1
    s = run(s, [("STAY", "STAY")] * PICKUP_FRAMES)
    s = step(s, "STAY/THROW", "STAY")
    assert s.bombs[0].fly_to == (THROW_DIST, 0)
    s = run(s, [("STAY", "STAY")] * FLY_FRAMES)
    b = s.bombs[0]
    assert (b.c, b.r) == (6, 0) and b.explode_at == s.frame + FUSE
    assert s.players[1].stun_until == s.frame + STUN  # 頭に当たって気絶
    assert legal_actions(s, 1) == ["STAY"]


def test_death_by_opponent_and_draw():
    s = GameState.initial(p0=(0, 0), p1=(2, 0))
    s.bombs.append(Bomb(id=0, c=1, r=0, owner=1, placed=0, explode_at=1))
    s.next_bomb_id = 1
    s = step(s, "STAY", "STAY")
    assert s.winner == -1 and s.players[0].cause_of_death == "opp_bomb" and s.players[1].cause_of_death == "own_bomb"


def test_time_limit_draw():
    s = GameState.initial()
    s.frame = TIME_LIMIT - 1
    s = step(s, "STAY", "STAY")
    assert s.winner == -1


def test_determinism_and_replay_roundtrip():
    import random
    rng = random.Random(1)
    s0 = GameState.initial()
    acts = []
    s = s0
    for _ in range(400):
        a0 = rng.choice(legal_actions(s, 0))
        a1 = rng.choice(legal_actions(s, 1))
        acts.append((a0, a1))
        s = step(s, a0, a1)
        if s.done():
            break
    s2 = replay.play(s0, acts)
    assert s.key() == s2.key()
    path = os.path.join(tempfile.gettempdir(), "bb_replay_test.json")
    replay.save(path, s0, acts, {"seed": 1})
    s0b, actsb, meta = replay.load(path)
    assert replay.play(s0b, actsb).key() == s.key() and meta["seed"] == 1


def test_legal_actions_basic():
    s = GameState.initial(p0=(0, 0))
    la = legal_actions(s, 0)
    assert "R" in la and "D" in la and "U" not in la and "L" not in la and "R/BOMB" in la
    assert "STAY/PUNCH" not in la
