"""Antithetic evolution strategy with frozen opponents and holdout acceptance.

Fitness is a measured outcome, never D/F themselves. Common random seeds and
paired perturbations reduce evaluation noise; archived policies avoid moving
opponents within an iteration. Optional scenario starts provide terminal
signals when the open-board duel is all draws.
"""
import copy
import json
import os
import random
import time
from . import defense as D, offense as F
from .agents import CombinedAgent, make_agent
from .evaluate import match
from .state import GameState, Bomb


def outcome(result):
    return (result['win_rate'] - result['loss_rate'] - 0.5*result['self_kill_rate']
            + 0.25*result.get('kills', 0)/max(1, result['games']))


def reward_of(result, shaping=0.0):
    # No bomb-spam or survival-duration bonus. Optional bounded auxiliary term.
    return outcome(result) + shaping * max(-1, min(1, result['mean_routes_cut']/4))


def curriculum_start(seed):
    """Synthetic tactical exercises, explicitly separate from normal evaluation."""
    rng = random.Random(seed)
    layouts = [((0, 0), (2, 0)), ((2, 2), (4, 2)), ((6, 4), (6, 6)), ((10, 8), (12, 8))]
    p0, p1 = layouts[rng.randrange(len(layouts))]
    s = GameState.initial(p0, p1)
    # A live bomb creates an actual terminal challenge, not a shaped score.
    owner = rng.randrange(2)
    p = s.players[owner]
    s.bombs = [Bomb(0, p.c, p.r, owner, 0, rng.choice((24, 42, 60)))]
    s.next_bomb_id = 1
    return s


def _average(results):
    n = sum(r['games'] for r in results)
    out = {key: sum(r.get(key, 0)*r['games'] for r in results)/n
           for key in ('win_rate', 'loss_rate', 'draw_rate', 'self_kill_rate',
                       'mean_D', 'mean_F', 'mean_routes_cut', 'mean_frames')}
    out.update(games=n, kills=sum(r['kills'] for r in results),
               bombs_placed=sum(r['bombs_placed'] for r in results))
    out['attack_success_rate'] = out['kills']/max(1, out['bombs_placed'])
    return out


def train(role='defense', iters=3, pop=8, games=8, seed=0, sigma=0.2, lr=0.1,
          opponent='self', model=None, out='runs/model.json', log_path=None,
          max_frames=7200, curriculum=False, shaping=0.0, pool_size=4):
    if role not in ('defense', 'offense'): raise ValueError('invalid role')
    if pop < 2 or pop % 2 or games < 1 or iters < 0 or sigma <= 0 or lr < 0 or pool_size < 1:
        raise ValueError('positive sigma/games/pool; even population >= 2 required')
    rng = random.Random(seed)
    model = copy.deepcopy(model or {})
    wD = {**D.DEFAULT_WEIGHTS, **model.get('wD', {})}
    wF = {**F.DEFAULT_WEIGHTS, **model.get('wF', {})}
    mix = model.get('mix', 0.3)
    history = list(model.get('history', []))
    pool = copy.deepcopy(model.get('pool', []))[-pool_size:]
    target = wD if role == 'defense' else wF
    keys = [k for k in target if k not in ('dead', 'self_dead')]
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    if log_path: os.makedirs(os.path.dirname(log_path) or '.', exist_ok=True)

    for it in range(iters):
        started = time.monotonic()
        # Both current and previous self policies are immutable for this round.
        frozen = [{'wD': dict(wD), 'wF': dict(wF), 'mix': mix}] + copy.deepcopy(pool)
        if opponent == 'self':
            rivals = [('combined', frozen[0]), ('rule', {}), ('combined', {})] + [('combined', m) for m in frozen[1:]]
        else:
            rivals = [(opponent, {})]

        def evaluate_weights(weights, holdout=False):
            aD = weights if role == 'defense' else wD
            aF = weights if role == 'offense' else wF
            rows = []
            # Identical opponent schedule, seeds and starting states for every
            # perturbation. Seats alternate independently of opponent selection.
            for g in range(games):
                kind, rival = rivals[(g//2+it) % len(rivals)]
                gs = seed*10000 + it*100 + g//2 + (1000000 if holdout else 0)
                start = curriculum_start(gs) if curriculum else None
                rows.append(match(CombinedAgent(aD, aF, mix), make_agent(kind, rival),
                                  1, seed=gs, max_frames=max_frames, swap_sides=False,
                                  first_seat=g % 2, start=start))
            return _average(rows)

        base = evaluate_weights(target)
        eps, rewards = [], []
        terminal_signal = base["win_rate"] + base["loss_rate"] + base["self_kill_rate"] > 0
        for _ in range(pop//2):
            e = {k: rng.gauss(0, 1) for k in keys}
            for sign in (1, -1):
                perturb = {k: sign*v for k, v in e.items()}
                candidate = dict(target)
                candidate.update({k: target[k]+sigma*perturb[k] for k in keys})
                res = evaluate_weights(candidate)
                terminal_signal |= res["win_rate"] + res["loss_rate"] + res["self_kill_rate"] > 0
                eps.append(perturb)
                rewards.append(reward_of(res, shaping))
        proposal = dict(target)
        centre = sum(rewards)/pop
        for key in keys:
            gradient = sum((r-centre)*e[key] for r, e in zip(rewards, eps))/(pop*sigma)
            delta = max(-0.25, min(0.25, lr*gradient))
            proposal[key] = max(-10, min(10, target[key]+delta))
        validation_before = evaluate_weights(target, holdout=True)
        validation_after = evaluate_weights(proposal, holdout=True) if proposal != target else validation_before
        accepted = (outcome(validation_after) > outcome(validation_before)+1e-12
                    and validation_after['self_kill_rate'] <= validation_before['self_kill_rate'])
        score_rise = (validation_after['mean_D'] > validation_before['mean_D']+1e-6
                      or validation_after['mean_F'] > validation_before['mean_F']+1e-6)
        score_only = score_rise and outcome(validation_after) <= outcome(validation_before)+1e-12
        if accepted:
            pool.append({'wD': dict(wD), 'wF': dict(wF), 'mix': mix})
            pool = pool[-pool_size:]
            target.update(proposal)
        after = validation_after if accepted else validation_before
        rec = {'iter': len(history), 'role': role, 'opponent': opponent,
               'curriculum': curriculum, 'population': pop, 'games': games,
               'pool_policies': len(frozen), 'base_reward': reward_of(base, shaping),
               'pop_mean_reward': centre, 'reward_spread': max(rewards)-min(rewards),
               'accepted': accepted, 'score_only_improvement': score_only,
               'flat_fitness': all(r == rewards[0] for r in rewards),
               'no_terminal_signal': not terminal_signal,
               'before': validation_before, 'proposed': validation_after,
               **{k: after[k] for k in ('win_rate', 'self_kill_rate', 'attack_success_rate',
                                       'mean_D', 'mean_F', 'mean_routes_cut')},
               'seconds': round(time.monotonic()-started, 2)}
        history.append(rec)
        print(json.dumps(rec, ensure_ascii=False), flush=True)
        if log_path:
            with open(log_path, 'a', encoding='utf-8') as f: f.write(json.dumps(rec)+'\n')
        model = {'wD': wD, 'wF': wF, 'mix': mix, 'history': history, 'pool': pool,
                 'seed': seed, 'role_last': role,
                 'training': {'sigma': sigma, 'lr': lr, 'pop': pop, 'games': games,
                              'opponent': opponent, 'curriculum': curriculum, 'shaping': shaping}}
        with open(out, 'w', encoding='utf-8') as f: json.dump(model, f, indent=2)
    return model
