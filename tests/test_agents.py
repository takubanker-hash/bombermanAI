# -*- coding: utf-8 -*-
"""エージェント・評価・学習の煙テスト（小さな設定で動くこと、同じシードで同じ結果になること）"""
import os, sys, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from bomberman_ai.agents import make_agent, play_game
from bomberman_ai.evaluate import match
from bomberman_ai.learn import train
from bomberman_ai import defense as D, offense as F
from bomberman_ai.state import GameState, Bomb
from bomberman_ai.constants import FUSE


def test_random_vs_random_is_reproducible():
    s1, a1, _ = play_game(make_agent("random"), make_agent("random"), seed=7, max_frames=600)
    s2, a2, _ = play_game(make_agent("random"), make_agent("random"), seed=7, max_frames=600)
    assert a1 == a2 and s1.key() == s2.key()


def test_defense_escapes_from_bomb():
    s = GameState.initial(p0=(6, 4), p1=(12, 10))
    s.bombs.append(Bomb(id=0, c=6, r=5, owner=1, placed=0, explode_at=FUSE))
    a, f = D.choose_defense(s, 0)
    assert a in ("L", "R", "U")  # 爆風線から外れる方向
    assert f["dead"] == 0.0


def test_offense_prefers_bomb_next_to_cornered_opponent():
    s = GameState.initial(p0=(1, 0), p1=(0, 0))  # 相手は角、自分は隣
    s.players[0].face = "L"
    ranked = F.rank_candidates(s, 0, F.DEFAULT_WEIGHTS, top_k=2)
    assert ranked and any(a.endswith("/BOMB") for _, a, _, _ in ranked[:3])


def test_match_metrics_keys():
    r = match(make_agent("rule"), make_agent("random"), 2, seed=1, max_frames=300)
    for k in ("win_rate", "self_kill_rate", "attack_success_rate", "mean_routes_cut", "mean_frames"):
        assert k in r


def test_train_runs_and_saves():
    out = os.path.join(tempfile.gettempdir(), "bb_model_test.json")
    m = train("defense", iters=1, pop=2, games=1, seed=3, out=out, max_frames=240)
    assert os.path.exists(out) and "wD" in m and len(m["history"]) == 1
