# -*- coding: utf-8 -*-
"""エージェント（AIに渡す状態と返す行動）:
  agent.act(state: GameState, me: int, rng: random.Random) -> action: str
  state は engine の GameState（自分と相手の位置・爆弾・爆炎がすべて見える完全情報）。返す行動は actions.py の文字列。
AI は「マスの中心にいる時」と「操作が可能な時」だけ考え、移動中は前回の移動を続ける（速さのため）。

- RandomAgent   合法行動から一様に選ぶ
- RuleAgent     単純なルール: 危険なら余裕が最大の移動、相手が同じ列/行で 4 マス以内なら設置、それ以外は相手へ近づく
- DefenseAgent  守備 D だけ（爆弾を置かない）
- OffenseAgent  攻撃 F だけ（自分の生存は F の self 項に任せる）
- CombinedAgent 攻守統合: 危険時は D、そうでなければ F と D を合わせて選ぶ。攻撃候補にも自分の生存可能性と相手の応手への頑健さを入れる"""
import random
from typing import Dict, List, Tuple, Optional
from .constants import SPEED, DIRS
from .state import GameState
from .actions import legal_actions, parse
from .safety import escape_area, time_slack, in_danger, INF
from . import defense as D
from . import offense as F


class Agent:
    name = "base"

    def act(self, s: GameState, me: int, rng: random.Random) -> str:
        raise NotImplementedError

    def stats(self) -> dict:
        return {}


def _continue_move(s: GameState, me: int) -> Optional[str]:
    """移動中なら続行する（判断はマスの中心で行う）"""
    p = s.players[me]
    if p.prog > 0:
        for k, v in DIRS.items():
            if v == (p.dc, p.dr):
                return k
    return None


class RandomAgent(Agent):
    name = "random"

    def act(self, s, me, rng):
        return rng.choice(legal_actions(s, me))


class RuleAgent(Agent):
    name = "rule"

    def __init__(self):
        self._last = -10 ** 9

    def act(self, s, me, rng):
        c = _continue_move(s, me)
        if c:
            return c
        if not in_danger(s, me) and s.frame - self._last < SPEED:
            return "STAY"
        self._last = s.frame
        p, q = s.players[me], s.players[1 - me]
        la = legal_actions(s, me)
        if in_danger(s, me) or len(escape_area(s, me)[0]) == 0:
            best, best_v = "STAY", -1
            for a in la:
                if "/" in a:
                    continue
                t = D.lookahead(s, me, a)
                if not t.players[me].alive:
                    continue
                v = len(escape_area(t, me)[0]) * 1000 + min(time_slack(t, me), 10 ** 6)
                if v > best_v:
                    best, best_v = a, v
            return best
        (mc, mr), (oc, orr) = p.tile(), q.tile()
        if (mc == oc or mr == orr) and abs(mc - oc) + abs(mr - orr) <= 4 and "STAY/BOMB" in la:
            t = D.lookahead(s, me, "STAY/BOMB")
            if len(escape_area(t, me)[0]) > 0:
                return "STAY/BOMB"
        # 相手へ近づく（安全な一歩だけ）
        opts = []
        for a in la:
            if "/" in a or a == "STAY":
                continue
            dx, dy = DIRS[a]
            t = D.lookahead(s, me, a)
            if not t.players[me].alive or len(escape_area(t, me)[0]) == 0:
                continue
            opts.append((abs(mc + dx - oc) + abs(mr + dy - orr), a))
        if opts:
            opts.sort()
            return opts[0][1]
        return "STAY"


class DefenseAgent(Agent):
    name = "defense"

    def __init__(self, weights: Dict[str, float] = None):
        self.w = dict(weights or D.DEFAULT_WEIGHTS)
        self.score_sum = 0.0
        self.n = 0
        self._last = -10 ** 9

    def act(self, s, me, rng):
        c = _continue_move(s, me)
        if c:
            return c
        if not in_danger(s, me) and s.frame - self._last < SPEED:
            return "STAY"
        self._last = s.frame
        a, f = D.choose_defense(s, me, self.w)
        self.score_sum += D.defense_score(f, self.w) if f else 0.0
        self.n += 1
        return a

    def stats(self):
        return {"mean_D": self.score_sum / max(1, self.n)}


class OffenseAgent(Agent):
    name = "offense"

    def __init__(self, weights: Dict[str, float] = None, with_robust: bool = True):
        self.w = dict(weights or F.DEFAULT_WEIGHTS)
        self.with_robust = with_robust
        self.score_sum = 0.0
        self.n = 0
        self.routes_cut_sum = 0.0
        self._last = -10 ** 9

    def act(self, s, me, rng):
        c = _continue_move(s, me)
        if c:
            return c
        if not in_danger(s, me) and s.frame - self._last < SPEED:
            return "STAY"
        self._last = s.frame
        a, f = F.choose_offense(s, me, self.w, with_robust=self.with_robust)
        if f:
            self.score_sum += F.offense_score(f, self.w)
            self.routes_cut_sum += f.get("routes_cut", 0.0) * 4
        self.n += 1
        return a

    def stats(self):
        return {"mean_F": self.score_sum / max(1, self.n), "mean_routes_cut": self.routes_cut_sum / max(1, self.n)}


class CombinedAgent(Agent):
    """攻守統合。危険（自分のマスが燃える予定）なら D で逃げる。安全なら全候補について
    score = F(相手の安全の減少・自分の生存・頑健さ) + mix * D(候補後の自分の守備特徴) を最大化する（2 段階評価）。
    判断はマスの中心で行い、危険が無い間は SPEED コマに 1 回だけ考える（速さのため）。"""
    name = "combined"

    def __init__(self, wD: Dict[str, float] = None, wF: Dict[str, float] = None, mix: float = 0.3, with_robust: bool = True):
        self.wD = dict(wD or D.DEFAULT_WEIGHTS)
        self.wF = dict(wF or F.DEFAULT_WEIGHTS)
        self.mix = mix
        self.with_robust = with_robust
        self.n = 0
        self.sumD = 0.0
        self.sumF = 0.0
        self.routes_cut_sum = 0.0
        self.attack_actions = 0
        self._last = (-10 ** 9, "STAY")

    def act(self, s, me, rng):
        c = _continue_move(s, me)
        if c:
            return c
        # A distant blast is an opportunity to prepare, not an immediate retreat.
        danger = time_slack(s, me) <= SPEED * 5 or not escape_area(s, me)[0]
        if not danger and s.frame - self._last[0] < SPEED:
            return "STAY"  # 安全なときは SPEED コマに 1 回だけ考える
        self.n += 1
        if danger:
            a, f = D.choose_defense(s, me, self.wD)
            self.sumD += D.defense_score(f, self.wD) if f else 0.0
            self._last = (s.frame, a)
            return a

        def extra(f, t, a):
            fd = D.defense_features(t, me)
            return -1e9 if fd["dead"] > 0 else self.mix * D.defense_score(fd, self.wD)

        ranked = F.rank_candidates(s, me, self.wF, extra=extra, top_k=F.TOP_K if self.with_robust else 0)
        ranked = [x for x in ranked if x[0] > -1e8]
        if not ranked:
            a, f = D.choose_defense(s, me, self.wD)
            self._last = (s.frame, a)
            return a
        sc, best, f, t = ranked[0]
        self.sumF += F.offense_score(f, self.wF)
        self.sumD += D.defense_score(D.defense_features(t, me), self.wD)
        if "/" in best or f["routes_cut"] > 0:
            self.attack_actions += 1
            self.routes_cut_sum += f["routes_cut"] * 4
        self._last = (s.frame, best)
        return best

    def stats(self):
        return {"mean_D": self.sumD / max(1, self.n), "mean_F": self.sumF / max(1, self.n),
                "mean_routes_cut": self.routes_cut_sum / max(1, self.attack_actions)}


def make_agent(kind: str, model: dict = None) -> Agent:
    model = model or {}
    if kind == "random":
        return RandomAgent()
    if kind == "rule":
        return RuleAgent()
    if kind == "defense":
        return DefenseAgent(model.get("wD"))
    if kind == "offense":
        return OffenseAgent(model.get("wF"))
    if kind == "combined":
        return CombinedAgent(model.get("wD"), model.get("wF"), model.get("mix", 0.3))
    raise ValueError(kind)


def play_game(a0: Agent, a1: Agent, seed: int = 0, max_frames: int = 7200, start=None) -> Tuple[GameState, List[Tuple[str, str]], GameState]:
    """1 試合。乱数は seed で固定。返り値: 最終状態, 行動列, 初期状態"""
    a0.placements = a1.placements = 0
    rng = random.Random(seed)
    s0 = start or GameState.initial()
    s = s0
    acts = []
    for _ in range(max_frames):
        x = a0.act(s, 0, rng)
        y = a1.act(s, 1, rng)
        acts.append((x, y))
        old_id = s.next_bomb_id
        s = step(s, x, y)
        for b in s.bombs:
            if b.id >= old_id:
                (a0 if b.owner == 0 else a1).placements += 1
        if s.done():
            break
    return s, acts, s0


from .engine import step  # noqa: E402  (循環を避けるため末尾で読み込む)
