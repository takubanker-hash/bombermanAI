# -*- coding: utf-8 -*-
"""ゲーム状態（純データ）。engine.step() が新しい状態を返す。すべて整数・タプルで決定論的に複製できる。
位置の表現: プレイヤーはマスの中心にいるか、隣のマスの中心へ移動中（SPEED コマで 1 マス）。
  (c, r)=いるマス、(dc, dr)=移動方向、prog=移動の進み（0..SPEED-1）。prog が SPEED に達したら隣のマスへ移る。"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple, Dict
import dataclasses, json, copy as _copy
from .constants import *

@dataclass
class Player:
    c: int
    r: int
    dc: int = 0            # 移動中の方向
    dr: int = 0
    prog: int = 0          # 移動の進み（コマ）
    face: str = "D"        # 向き（パンチ・投げの方向）
    alive: bool = True
    stun_until: int = 0    # このコマまで動けない（頭に爆弾）
    lag_until: int = 0     # このコマまで移動できない（硬直）
    holding: Optional[int] = None   # 抱えている爆弾の id
    queued: Optional[dict] = None   # 振りかぶり中の動作。{kind: PUNCH/THROW/KICK, at: 発動するコマ, bomb_id, dir}
    cause_of_death: str = ""        # "own_bomb" / "opp_bomb" / ""
    def pos(self) -> Tuple[float, float]:
        """マス単位の連続位置（中心が整数）"""
        return (self.c + self.dc * self.prog / SPEED, self.r + self.dr * self.prog / SPEED)
    def tile(self) -> Tuple[int, int]:
        """当たり判定に使うマス（中心を越えたら隣のマス）"""
        if self.prog * 2 >= SPEED: return (self.c + self.dc, self.r + self.dr)
        return (self.c, self.r)

@dataclass
class Bomb:
    id: int
    c: int
    r: int
    owner: int                 # 0/1
    placed: int                # 置いたコマ
    explode_at: int            # 爆発予定コマ（抱え中は -1）
    # 滑り（キック）
    slide: Tuple[int, int] = (0, 0)
    slide_prog: int = 0
    # 飛行（パンチ・投げ）: 着地マスと着地コマ
    fly_to: Optional[Tuple[int, int]] = None
    land_at: int = -1
    held: bool = False
    def on_ground(self) -> bool:
        return not self.held and self.fly_to is None

@dataclass
class GameState:
    frame: int = 0
    players: List[Player] = field(default_factory=list)
    bombs: List[Bomb] = field(default_factory=list)
    flames: Dict[Tuple[int, int], int] = field(default_factory=dict)   # マス -> 消えるコマ
    next_bomb_id: int = 0
    winner: Optional[int] = None      # 0/1、引き分け -1、未決着 None
    log: List[str] = field(default_factory=list)
    keep_log: bool = True             # False なら step() はログを書かない（先読み用の軽量状態）

    @staticmethod
    def initial(p0=(0, 0), p1=(COLS - 1, ROWS - 1)) -> "GameState":
        return GameState(players=[Player(*p0, face="R"), Player(*p1, face="L")])

    def copy(self, light: bool = False) -> "GameState":
        """deepcopy より速い複製（先読みで大量に呼ぶ）。light=True はログを持たない先読み用"""
        keep = self.keep_log and not light
        return GameState(frame=self.frame, players=[_copy.copy(p) for p in self.players],
                         bombs=[_copy.copy(b) for b in self.bombs], flames=dict(self.flames),
                         next_bomb_id=self.next_bomb_id, winner=self.winner, log=(list(self.log) if keep else []), keep_log=keep)

    def bomb_at(self, c, r) -> Optional[Bomb]:
        for b in self.bombs:
            if b.on_ground() and b.c == c and b.r == r: return b
        return None

    def blocked(self, c, r, ignore_bomb: Optional[int] = None) -> bool:
        """そのマスに入れないか（盤外・柱・地面の爆弾）。ignore_bomb=自分が乗っている爆弾の id"""
        if not in_board(c, r) or is_pillar(c, r): return True
        b = self.bomb_at(c, r)
        return b is not None and b.id != ignore_bomb

    def done(self) -> bool:
        return self.winner is not None

    # ---- 保存・復元（リプレイ用）----
    def to_dict(self) -> dict:
        d = asdict(self); d.pop("keep_log", None); d["flames"] = [[c, r, t] for (c, r), t in self.flames.items()]
        for b in d["bombs"]:
            b["slide"] = list(b["slide"]); b["fly_to"] = list(b["fly_to"]) if b["fly_to"] else None
        return d
    @staticmethod
    def from_dict(d: dict) -> "GameState":
        s = GameState(frame=d["frame"], next_bomb_id=d["next_bomb_id"], winner=d["winner"], log=list(d.get("log", [])))
        s.players = [Player(**p) for p in d["players"]]
        for b in d["bombs"]:
            b = dict(b); b["slide"] = tuple(b["slide"]); b["fly_to"] = tuple(b["fly_to"]) if b["fly_to"] else None; s.bombs.append(Bomb(**b))
        s.flames = {(c, r): t for c, r, t in d["flames"]}
        return s
    def to_json(self) -> str: return json.dumps(self.to_dict())
    def key(self) -> str:
        """状態の同一性チェック用（テスト）"""
        return json.dumps(self.to_dict(), sort_keys=True)
