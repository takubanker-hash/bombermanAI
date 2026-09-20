# -*- coding: utf-8 -*-
"""リプレイの保存・再生。初期状態と行動列（コマごとの [a0, a1]）から同じ結果を再現できる。"""
import json
from typing import List, Tuple
from .state import GameState
from .engine import step


def play(initial: GameState, actions: List[Tuple[str, str]]) -> GameState:
    s = initial
    for a0, a1 in actions:
        s = step(s, a0, a1)
        if s.done():
            break
    return s


def save(path: str, initial: GameState, actions: List[Tuple[str, str]], meta: dict = None):
    json.dump({"meta": meta or {}, "initial": initial.to_dict(), "actions": [list(a) for a in actions]},
              open(path, "w", encoding="utf-8"))


def load(path: str):
    d = json.load(open(path, encoding="utf-8"))
    return GameState.from_dict(d["initial"]), [tuple(a) for a in d["actions"]], d.get("meta", {})
