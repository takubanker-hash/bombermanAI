# -*- coding: utf-8 -*-
"""動画解析プロジェクト（bomberman-analysis）との接続。
解析側の report/replay_data.js（const REPLAY={...}）の「場面（clip）」の 1 コマを、シミュレータの GameState に変換する。
  clip.frames[k] = {ok, me:[x,y], op:[x,y], bombs:[[c, r, age, explode_at, owner]], fl:[[c, r, age]]}
    - 位置は足もとのマス座標（小数）。ここでは四捨五入してマスの中心に置く
    - bombs の age は置いてからのコマ数、explode_at は映像で確認できた爆発コマ（無ければ -1 → 置いてから FUSE で爆発とみなす）
    - owner 1 = 解析側の「自分」（紫★/黄★）, 2 = 相手, 0 = 不明（相手の物として扱う）
    - fl は燃えているマス（age = 燃え始めからのコマ数）
使い方:
  from bridge.from_analysis import load_clips, state_from_frame
  clips = load_clips("C:/.../bomberman-analysis/report/replay_data.js")
  s = state_from_frame(clips[0], k=300)
  # → AI に渡して「この局面で AI なら何をするか」を比べる（agents.CombinedAgent().act(s, 0, rng)）
制約: 解析側の位置検出には誤差（半マス程度）と欠けがあり、キャラの向き・硬直・抱えている爆弾は分からない（向きは D、硬直なし、queued=None とする）。"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bomberman_ai.constants import FUSE, BURN, COLS, ROWS, is_pillar
from bomberman_ai.state import GameState, Player, Bomb


def load_clips(path: str):
    s = open(path, encoding="utf-8").read()
    j = s[s.index("=") + 1:].strip().rstrip(";")
    return json.loads(j)["clips"]


def _tile(xy):
    c = max(0, min(COLS - 1, int(round(xy[0]))))
    r = max(0, min(ROWS - 1, int(round(xy[1]))))
    if is_pillar(c, r):  # 検出誤差で柱に乗っていたら隣へ
        c = c + 1 if c + 1 < COLS else c - 1
    return c, r


def state_from_frame(clip: dict, k: int) -> GameState:
    fr = clip["frames"][k]
    f = clip["start"] + k
    me = _tile(fr["me"]) if fr.get("me") else (0, 0)
    op = _tile(fr["op"]) if fr.get("op") else (COLS - 1, ROWS - 1)
    s = GameState(frame=f, players=[Player(*me), Player(*op)])
    for i, b in enumerate(fr.get("bombs") or []):
        c, r, age, ex, owner = b
        if is_pillar(c, r):
            continue
        explode_at = ex if ex and ex > 0 else f + max(1, FUSE - max(0, age))
        s.bombs.append(Bomb(id=i, c=int(c), r=int(r), owner=0 if owner == 1 else 1, placed=f - max(0, age), explode_at=int(explode_at)))
    s.next_bomb_id = len(s.bombs)
    for c, r, age in fr.get("fl") or []:
        s.flames[(int(c), int(r))] = (f + max(1, BURN - max(0, age)), 1)
    return s


if __name__ == "__main__":
    import random
    from bomberman_ai.agents import CombinedAgent
    from bomberman_ai.safety import escape_area
    path = sys.argv[1] if len(sys.argv) > 1 else "../bomberman-analysis/report/replay_data.js"
    clips = load_clips(path)
    clip = clips[0]
    k = int(sys.argv[2]) if len(sys.argv) > 2 else len(clip["frames"]) // 2
    s = state_from_frame(clip, k)
    print("clip:", clip["label"], "frame", s.frame, "bombs", len(s.bombs), "flames", len(s.flames))
    print("escape area me/op:", len(escape_area(s, 0)[0]), len(escape_area(s, 1)[0]))
    print("AI (combined) would do:", CombinedAgent().act(s, 0, random.Random(0)))
