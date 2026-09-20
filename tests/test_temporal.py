"""Regression tests for hazards, adversarial scope and evaluation isolation."""
from bomberman_ai.state import GameState, Bomb
from bomberman_ai.engine import step, advance_environment
from bomberman_ai.constants import SPEED, BURN, CHAIN_DELAY, FUSE
from bomberman_ai.temporal import forecast, survival, BITS
from bomberman_ai.safety import burn_schedule, bounded_minimax, escape_area
from bomberman_ai.defense import lookahead


def test_chain_delay_and_newly_open_blast_ray():
    s = GameState.initial()
    s.bombs = [Bomb(0, 2, 0, 0, 0, 5), Bomb(1, 5, 0, 1, 0, 150)]
    tl = forecast(s)
    assert tl.first[(5, 0)] == 5
    assert tl.first[(6, 0)] == 5 + CHAIN_DELAY
    assert not (tl.danger[5+BURN+CHAIN_DELAY] & BITS[(6, 0)])


def test_forecast_matches_environment_through_flight_and_slide():
    s = GameState.initial(p0=(0, 10), p1=(12, 10))
    s.bombs = [Bomb(0, 2, 0, 0, 0, 70, slide=(1, 0)),
               Bomb(1, 0, 2, 1, 0, -1, slide=(1, 0), fly_to=(6, 2), land_at=20)]
    original = s.key()
    tl = forecast(s)
    t = s.copy(light=True)
    for frame in range(1, tl.horizon+1):
        t.frame = frame
        advance_environment(t, frame)
        expected = sum(BITS[x] for x in t.flames)
        assert expected == tl.danger[frame]
    assert tl.first[(6, 2)] == 20+FUSE
    assert s.key() == original


def test_flame_cache_uses_positions_not_only_count():
    s = GameState.initial()
    s.flames = {(2, 0): (10, 0)}
    assert (2, 0) in burn_schedule(s, 0)[0]
    s.flames = {(4, 0): (10, 0)}
    assert (2, 0) not in burn_schedule(s, 0)[0]


def test_cannot_wait_on_burning_source_or_leave_after_ignition():
    s = GameState.initial(p0=(0, 0))
    s.bombs = [Bomb(0, 0, 1, 1, 0, 1)]
    assert not survival(s, 0, 12)['alive']
    assert not escape_area(s, 0)[0]


def test_can_wait_for_flame_to_clear_then_cross():
    s = GameState.initial(p0=(0, 0))
    s.flames = {(1, 0): (5, 1)}
    result = survival(s, 0, 20)
    assert result['alive'] and (2, 0) in result['cells']


def test_stun_prevents_fictional_escape():
    s = GameState.initial(p0=(0, 0))
    s.players[0].stun_until = 30
    s.bombs = [Bomb(0, 0, 2, 1, 0, 10)]
    assert not survival(s, 0)['alive']
    assert not escape_area(s, 0)[0]


def test_minimax_budget_is_unknown_and_certificate_is_bounded():
    s = GameState.initial()
    assert bounded_minimax(s, 0, frames=4, max_nodes=1)['status'] == 'unknown'
    assert bounded_minimax(s, 0, frames=1, max_nodes=100)['status'] == 'safe'
    s.bombs = [Bomb(0, 0, 1, 1, 0, 1)]
    assert bounded_minimax(s, 0, action='STAY', frames=1)['status'] == 'unsafe'


def test_opponent_operation_is_issued_once_in_lookahead():
    s = GameState.initial()
    t = lookahead(s, 0, 'STAY', 18, opp_action='L/BOMB')
    assert len(t.bombs) == 1


def test_survival_agrees_with_exhaustive_movement_on_static_short_horizon():
    # Exhaustive engine oracle, including partial movement and flame expiry.
    for fuse in (1, 4, 9):
        s = GameState.initial(p0=(0, 0), p1=(12, 10))
        s.bombs = [Bomb(0, 0, 2, 1, 0, fuse)]
        frontier = [s]
        for _ in range(9):
            out = {}
            for t in frontier:
                p = t.players[0]
                actions = ['STAY'] if p.prog else ['STAY', 'U', 'D', 'L', 'R']
                for a in actions:
                    u = step(t, a, 'STAY')
                    if u.players[0].alive:
                        q = u.players[0]
                        out[(q.c, q.r, q.dc, q.dr, q.prog)] = u
            frontier = list(out.values())
        assert survival(s, 0, 9)['alive'] == bool(frontier)


def test_waiting_does_not_create_fake_long_term_attack_pressure():
    from bomberman_ai.offense import offense_features
    s = GameState.initial(p0=(0, 5), p1=(12, 5))
    f, _ = offense_features(s, 0, 'STAY')
    assert f['long_cut'] == 0


def test_navigation_does_not_get_stuck_across_a_pillar():
    from bomberman_ai.offense import navigation_distance
    assert navigation_distance((0, 5), (12, 5)) == 14
    assert navigation_distance((0, 4), (12, 5)) == 13


def test_defense_uses_temporal_escape_when_no_permanent_refuge_exists():
    import json
    from pathlib import Path
    from bomberman_ai.defense import choose_defense
    s = GameState.from_dict(json.loads((Path(__file__).parent/'fixtures/late_escape.json').read_text()))
    assert not escape_area(s, 0)[0]
    action, _ = choose_defense(s, 0)
    assert action in ('L', 'R')  # waiting here caused the old policy's death
    from bomberman_ai.agents import DefenseAgent
    import random
    agent, rng = DefenseAgent(), random.Random(0)
    for _ in range(80):
        a = agent.act(s, 0, rng)
        s = step(s, a, 'STAY')
        if s.done(): break
    assert s.players[0].alive


def test_queued_throw_extends_forecast_past_landing_and_fuse():
    from bomberman_ai.constants import FLY_FRAMES
    s = GameState.initial()
    s.bombs = [Bomb(0, 0, 0, 0, 0, -1, held=True)]
    p = s.players[0]
    p.holding = 0
    p.queued = {'kind': 'THROW', 'at': 7, 'bomb_id': 0, 'dir': (1, 0)}
    p.lag_until = 17
    original = s.key()
    tl = forecast(s)
    assert tl.first[(6, 0)] == 7+FLY_FRAMES+FUSE
    assert tl.horizon >= 7+FLY_FRAMES+FUSE+BURN
    assert s.key() == original


def test_queued_kick_changes_forecast_and_cache_key():
    s = GameState.initial()
    s.bombs = [Bomb(0, 1, 0, 1, 0, 50)]
    p = s.players[0]
    p.queued = {'kind': 'KICK', 'at': 7, 'bomb_id': 0, 'dir': (1, 0)}
    p.lag_until = 7
    assert (0, 0) not in forecast(s).first
    p.queued = None
    assert forecast(s).first[(0, 0)] == 50


def test_queued_punch_misfire_does_not_invent_later_explosion():
    s = GameState.initial()
    s.bombs = [Bomb(0, 1, 0, 1, 0, 3)]
    s.players[0].queued = {'kind': 'PUNCH', 'at': 7, 'bomb_id': 0, 'dir': (1, 0)}
    tl = forecast(s)
    assert not any(tl.danger[3+BURN:])
