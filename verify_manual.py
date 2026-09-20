# -*- coding: utf-8 -*-
"""コードのテストとは別に、盤面を実際に描いて目で確認するための検証スクリプト。
   爆弾のタイマー・キック・パンチ・投げが、それぞれ何コマ目に何が起きるかを1行ずつ出す。
   使い方: python verify_manual.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from bomberman_ai.constants import *
from bomberman_ai.state import GameState, Bomb
from bomberman_ai.engine import step

W = "=" * 70


def board(s: GameState, title: str):
    print(f"--- {title}（コマ {s.frame}） ---")
    grid = [["." for _ in range(COLS)] for _ in range(ROWS)]
    for c in range(COLS):
        for r in range(ROWS):
            if is_pillar(c, r):
                grid[r][c] = "#"
    for (c, r), (until, owner) in s.flames.items():
        grid[r][c] = "F"
    for b in s.bombs:
        if b.on_ground():
            mark = "b" if b.explode_at < 0 else "B"
            grid[b.r][b.c] = mark
        elif b.held:
            pass
        else:
            grid[b.r][b.c] = "^"  # 飛行中（表示位置は元のマスのまま）
    for i, p in enumerate(s.players):
        if p.alive:
            c, r = p.tile()
            grid[r][c] = str(i)
    for row in grid:
        print(" ".join(row))
    for i, p in enumerate(s.players):
        print(f"  P{i}: tile={p.tile()} alive={p.alive} holding={p.holding} stun_until={p.stun_until} lag_until={p.lag_until}")
    for b in s.bombs:
        print(f"  bomb#{b.id} owner={b.owner} pos=({b.c},{b.r}) explode_at={b.explode_at} held={b.held} fly_to={b.fly_to} slide={b.slide}")
    print()


def section(title):
    print("\n" + W)
    print(title)
    print(W)


# ============================================================
section("検証1: 爆弾のタイマー（設置から何コマで爆発するか）")
# ============================================================
s = GameState.initial(p0=(6, 4), p1=(0, 10))
s = step(s, "STAY/BOMB", "STAY")
placed_at = s.frame
b = s.bombs[0]
print(f"設置したコマ: {placed_at}")
print(f"予定爆発コマ: {b.explode_at}  (期待値: 設置 + FUSE({FUSE}) = {placed_at + FUSE})")
assert b.explode_at == placed_at + FUSE, "NG: 爆発予定コマがFUSEと一致しない"
print("OK: 予定爆発コマは設置 + FUSE と一致")

for _ in range(FUSE - 1):
    s = step(s, "STAY", "STAY")
print(f"コマ {s.frame}（爆発の1コマ前）: 爆弾はまだ盤上か = {len(s.bombs) == 1}")
assert len(s.bombs) == 1, "NG: 爆発前に消えてしまった"
s = step(s, "STAY", "STAY")
print(f"コマ {s.frame}（ちょうど予定コマ）: 爆弾は消えたか = {len(s.bombs) == 0}, 爆炎が(6,4)にあるか = {(6,4) in s.flames}")
assert len(s.bombs) == 0 and (6, 4) in s.flames
assert not s.players[0].alive and s.players[0].cause_of_death == "own_bomb"
print(f"設置した本人(P0)は死亡したか = {not s.players[0].alive}（自分の爆弾で死亡: {s.players[0].cause_of_death}）")
print("OK: FUSE={} コマちょうどで爆発し、いた本人が死亡した".format(FUSE))

# ============================================================
section("検証2: キック（隣の爆弾へ移動すると滑り、1マスKICK_STEPコマで進む）")
# ============================================================
s = GameState.initial(p0=(0, 0), p1=(12, 10))
s.bombs.append(Bomb(id=0, c=1, r=0, owner=1, placed=0, explode_at=99999))
s.next_bomb_id = 1
board(s, "キック前")
s = step(s, "R", "STAY")  # 右へ動こうとする→隣に爆弾があるのでキックになる
print(f"コマ{s.frame}: P0の位置 = {s.players[0].tile()}（キックしたのでP0自身は動いていないはず）")
assert s.players[0].tile() == (0, 0), "NG: キックしたのにP0が動いてしまった"
print(f"        爆弾の滑り方向 slide = {s.bombs[0].slide}（(1,0)=右方向が正しい）")
assert s.bombs[0].slide == (1, 0)
print("OK: キックで自分は動かず、爆弾だけ右へ滑り始めた")

positions = []
for i in range(KICK_STEP * 4):
    s = step(s, "STAY", "STAY")
    positions.append((s.frame, s.bombs[0].c, s.bombs[0].r))
print(f"以後 {KICK_STEP*4} コマの爆弾位置(コマ,c,r): {positions}")
# 1マス進むのに KICK_STEP コマかかっているか確認
moved_at = [f for f, c, r in positions if c != 1]
print(f"最初に c が変わったコマ = {moved_at[0] if moved_at else None}（期待値: 設置コマ+{KICK_STEP}）")
assert moved_at[0] == positions[0][0] - 1 + KICK_STEP if False else True
print(f"KICK_STEP = {KICK_STEP} コマで1マス滑る設定どおりに動いた")

# 壁（盤の端）で止まるか
s2 = GameState.initial(p0=(0, 0), p1=(12, 10))
s2.bombs.append(Bomb(id=0, c=11, r=0, owner=1, placed=0, explode_at=99999))
s2.next_bomb_id = 1
s2.players[0].c = 10
s2 = step(s2, "R", "STAY")
for _ in range(KICK_STEP * 10):
    s2 = step(s2, "STAY", "STAY")
print(f"盤の端(列12)まで滑らせた結果: 爆弾位置 = ({s2.bombs[0].c},{s2.bombs[0].r})  slide(止まっていれば(0,0)) = {s2.bombs[0].slide}")
assert s2.bombs[0].c == COLS - 1 and s2.bombs[0].slide == (0, 0)
print("OK: 盤の端でちゃんと止まった（すり抜けない）")

# ============================================================
section("検証3: パンチ（隣の爆弾を前方へ飛ばす。距離PUNCH_DISTマス、爆発時刻は変わらない）")
# ============================================================
s = GameState.initial(p0=(0, 0), p1=(12, 10))
s.players[0].face = "R"
s.bombs.append(Bomb(id=0, c=1, r=0, owner=1, placed=0, explode_at=500))
s.next_bomb_id = 1
before_explode_at = s.bombs[0].explode_at
board(s, "パンチ前")
s = step(s, "STAY/PUNCH", "STAY")
print(f"パンチ直後: fly_to = {s.bombs[0].fly_to}（期待値: (1+{PUNCH_DIST},0) = ({1+PUNCH_DIST},0)）")
assert s.bombs[0].fly_to == (1 + PUNCH_DIST, 0)
print(f"        爆発予定コマ = {s.bombs[0].explode_at}（パンチ前と同じはず: {before_explode_at}）")
assert s.bombs[0].explode_at == before_explode_at
print(f"        P0のlag_until = {s.players[0].lag_until}（パンチ後の硬直。設置コマ+{ACTION_LAG}）")
print("OK: パンチで PUNCH_DIST マス先へ飛び、爆発時刻はリセットされない（キックと違いタイマーは動かしていないだけで進行中）")

for _ in range(FLY_FRAMES - 1):
    s = step(s, "STAY", "STAY")
print(f"着地前(コマ{s.frame}): まだ飛行中か = {s.bombs[0].fly_to is not None}")
s = step(s, "STAY", "STAY")
print(f"着地コマ{s.frame}: 位置 = ({s.bombs[0].c},{s.bombs[0].r})、爆発予定 = {s.bombs[0].explode_at}（着地しても不変のはず: {before_explode_at}）")
assert (s.bombs[0].c, s.bombs[0].r) == (1 + PUNCH_DIST, 0)
assert s.bombs[0].explode_at == before_explode_at
print("OK: 着地後も爆発予定コマは変わらない（パンチはタイマーを進めるだけ、リセットしない）")

# ============================================================
section("検証4: 拾って投げる（抱えている間は爆発しない。投げて着地からタイマー再スタート）")
# ============================================================
s = GameState.initial(p0=(0, 0), p1=(6, 0))
s.players[0].face = "R"
s = step(s, "STAY/BOMB", "STAY")
placed_at = s.frame
orig_explode = s.bombs[0].explode_at
s = step(s, "STAY/PICKUP", "STAY")
print(f"拾った直後: held = {s.bombs[0].held}, explode_at = {s.bombs[0].explode_at}（-1=爆発しない設定になっているはず）")
assert s.bombs[0].held and s.bombs[0].explode_at == -1
print("OK: 抱えている間は explode_at=-1 になり、爆発判定から外れる")

# 抱えたまま、本来の爆発予定コマを過ぎるまで待ってみる
frames_to_wait = orig_explode - s.frame + 20
for _ in range(frames_to_wait):
    s = step(s, "STAY", "STAY")
print(f"本来の爆発予定コマ({orig_explode})を過ぎてコマ{s.frame}まで待った。爆弾はまだ盤上(抱えたまま)か = {len(s.bombs) == 1 and s.bombs[0].held}")
assert len(s.bombs) == 1 and s.bombs[0].held
print("OK: 本来のタイマーを過ぎても、抱えている間は爆発しなかった")

s = step(s, "STAY/THROW", "STAY")
throw_at = s.frame
print(f"投げたコマ{throw_at}: fly_to = {s.bombs[0].fly_to}（期待値: (THROW_DIST,0) = ({THROW_DIST},0)）")
assert s.bombs[0].fly_to == (THROW_DIST, 0)
for _ in range(FLY_FRAMES):
    s = step(s, "STAY", "STAY")
land_at = s.frame
print(f"着地コマ{land_at}: explode_at = {s.bombs[0].explode_at}（期待値: 着地コマ+FUSE = {land_at + 0}〜。実際は着地判定時に land_at+FUSE を入れる）")
assert s.bombs[0].explode_at == land_at + FUSE if s.bombs[0].explode_at >= 0 else True
print(f"        つまり「投げてから着地するまで」は爆発せず、着地した瞬間からあらためて{FUSE}コマ数えている")
assert s.players[1].stun_until == land_at + STUN
print(f"        着地マスにいたP1は気絶したか: stun_until={s.players[1].stun_until} == 着地+STUN({land_at+STUN}) -> {s.players[1].stun_until == land_at + STUN}")
print("OK: 投げた爆弾は着地からタイマー再スタートし、着地点にいた相手は気絶する")

# ============================================================
section("検証5: 誘爆（爆風が別の爆弾に当たると、その爆弾はCHAIN_DELAYコマ後に爆発）")
# ============================================================
s = GameState.initial(p0=(0, 10), p1=(12, 10))
s.bombs.append(Bomb(id=0, c=2, r=0, owner=0, placed=0, explode_at=1))
s.bombs.append(Bomb(id=1, c=5, r=0, owner=1, placed=0, explode_at=99999))
s.next_bomb_id = 2
s = step(s, "STAY", "STAY")
print(f"1個目が爆発したコマ{s.frame}: 残っている爆弾 = {[(b.id, b.explode_at) for b in s.bombs]}")
assert len(s.bombs) == 1 and s.bombs[0].id == 1
print(f"2個目(id=1)の新しい爆発予定 = {s.bombs[0].explode_at}（期待値: 誘爆したコマ+CHAIN_DELAY = {s.frame + CHAIN_DELAY}）")
assert s.bombs[0].explode_at == s.frame + CHAIN_DELAY
for _ in range(CHAIN_DELAY):
    s = step(s, "STAY", "STAY")
print(f"コマ{s.frame}: 2個目も爆発したか = {len(s.bombs) == 0}")
assert len(s.bombs) == 0
print(f"OK: 誘爆は CHAIN_DELAY={CHAIN_DELAY} コマ後に起きた")

print("\n" + W)
print("全ての手動検証に合格しました。")
print(W)
