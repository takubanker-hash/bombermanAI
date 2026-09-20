"""Frame-accurate hazards; movement-only reachability under a fixed bomb forecast.

Stationary players are assumed for sliding-bomb stops. Future player actions are
NOT predicted. Landing cells are conservatively forbidden for that frame (stun
is not represented in the bitset). Never interpret an empty result as a forced
loss when kick/pickup/throw or player-dependent bomb stops could rescue a player.
"""
from dataclasses import dataclass
from .constants import COLS, ROWS, SPEED, FUSE, BURN, DIRS, is_pillar
from .engine import advance_environment

TILES = [(c, r) for r in range(ROWS) for c in range(COLS) if not is_pillar(c, r)]
BITS = {p: 1 << (p[1] * COLS + p[0]) for p in TILES}
BOARD = sum(BITS.values())
LEFT = sum(v for (c, r), v in BITS.items() if c > 0)
RIGHT = sum(v for (c, r), v in BITS.items() if c < COLS - 1)


def spread(bits, direction):
    if direction == 'U': return (bits >> COLS) & BOARD
    if direction == 'D': return (bits << COLS) & BOARD
    if direction == 'L': return ((bits & LEFT) >> 1) & BOARD
    return ((bits & RIGHT) << 1) & BOARD


def state_signature(s):
    return (s.frame, tuple((p.c, p.r, p.dc, p.dr, p.prog, p.alive, p.face,
            p.stun_until, p.lag_until, p.holding,
            (p.queued["kind"], p.queued["at"], p.queued["bomb_id"], tuple(p.queued["dir"]))
            if p.queued else None) for p in s.players),
            tuple((b.id, b.c, b.r, b.owner, b.explode_at, b.slide, b.slide_prog,
                   b.fly_to, b.land_at, b.held) for b in s.bombs),
            tuple(sorted((cell, tuple(value)) for cell, value in s.flames.items())))


def forecast_horizon(s):
    end = max([s.frame] + [v[0] for v in s.flames.values()])
    for b in s.bombs:
        if b.held: continue
        ex = b.explode_at
        if b.fly_to is not None and ex < b.land_at:
            ex = b.land_at + FUSE
        end = max(end, ex + BURN)
    from .constants import FLY_FRAMES
    for p in s.players:
        if p.queued and p.queued['kind'] in ('PUNCH', 'THROW'):
            # May reset an expired fuse on landing. A conservative horizon only;
            # the shared engine decides whether the queued operation misfires.
            end = max(end, p.queued['at']+FLY_FRAMES+FUSE+BURN)
    return max(SPEED, end - s.frame)


@dataclass
class Timeline:
    danger: list
    blocked: list
    landing: list
    first: dict
    bomb_tiles: set
    horizon: int
    complete: bool
    dynamic: bool


def forecast(s, horizon=None):
    """Reuse the engine's environment phases, never its deaths/game-over shortcut."""
    needed = forecast_horizon(s)
    horizon = needed if horizon is None else max(0, horizon)
    key = (state_signature(s), horizon)
    cache = getattr(s, '_forecast', None)
    if cache and cache[0] == key: return cache[1]
    t = s.copy(light=True)
    danger, blocked, landing, first = [], [], [], {}
    bomb_tiles = {(b.c, b.r) for b in s.bombs if b.on_ground()}
    dynamic = any(b.slide != (0, 0) or b.fly_to is not None for b in s.bombs)
    dt = 0
    while dt <= horizon:
        hits = 0
        if dt:
            before = {b.id for b in t.bombs if b.fly_to is not None and b.land_at <= s.frame + dt}
            t.frame = s.frame + dt
            advance_environment(t, t.frame)
            hits = sum(BITS.get((b.c, b.r), 0) for b in t.bombs if b.id in before)
        hot = 0
        for cell, (until, _) in t.flames.items():
            if until > t.frame:
                hot |= BITS.get(cell, 0)
                first.setdefault(cell, t.frame)
        block = sum(BITS.get((b.c, b.r), 0) for b in t.bombs if b.on_ground())
        # Static intervals can be filled without simulating every empty frame.
        moving = any(b.slide != (0, 0) or b.fly_to is not None for b in t.bombs) or any(p.queued for p in t.players)
        if moving or hits:
            span = 1
        else:
            events = [v[0] for v in t.flames.values() if v[0] > t.frame]
            events += [max(t.frame+1, b.explode_at) for b in t.bombs if b.on_ground() and b.explode_at >= 0]
            nxt = min(events, default=s.frame+horizon+1)
            span = max(1, min(horizon-dt+1, nxt-t.frame))
        danger.extend([hot] * span)
        blocked.extend([block] * span)
        landing.extend([hits] * span)
        dt += span
    result = Timeline(danger, blocked, landing, first, bomb_tiles, horizon,
                      horizon >= needed, dynamic)
    s._forecast = (key, result)
    return result


def survival(s, me, horizon=None):
    """Reachable centre cells at the horizon, including wait and half-tile exposure.

    Per-frame bitsets retain all routes without exponential path enumeration.
    No kick/punch/pickup/throw along the future path; those require engine search.
    """
    p = s.players[me]
    if not p.alive: return {'alive': False, 'count': 0, 'cells': set(), 'complete': True}
    tl = forecast(s, horizon)
    H = tl.horizon
    key = (state_signature(s), me, H)
    cache = getattr(s, '_survival', {})
    if key in cache: return cache[key]
    hot = [a | b for a, b in zip(tl.danger, tl.landing)]
    reach = [0] * (H + SPEED + 1)
    start = (p.c, p.r)
    dt = 0
    if p.prog:
        # Resolve the existing movement; STAY continues it in the engine.
        progress = p.prog
        while progress and dt < H:
            dt += 1
            if s.frame + dt > p.stun_until:
                progress += 1
                if progress >= SPEED:
                    start = (p.c + p.dc, p.r + p.dr)
                    progress = 0
            cell = start if not progress or progress * 2 < SPEED else (p.c+p.dc, p.r+p.dr)
            if hot[dt] & BITS.get(cell, 0):
                return {'alive': False, 'count': 0, 'cells': set(), 'complete': tl.complete}
    release = max(0, p.stun_until-s.frame, p.lag_until-s.frame) if not p.prog else max(dt, p.stun_until-s.frame)
    bit = BITS.get(start, 0)
    for k in range(dt + 1, min(release, H) + 1):
        if hot[k] & bit: bit = 0
    dt = min(H, max(dt, release))
    reach[dt] = bit
    for at in range(dt, H):
        origins = reach[at]
        if not origins: continue
        reach[at + 1] |= origins & ~hot[at + 1]  # wait one frame
        arrive = at + SPEED
        # Extra tail reaches certify in-flight survival at H too.
        if at + 1 > H: continue
        source_bad = 0
        target_bad = tl.blocked[at + 1]
        for k in range(1, SPEED + 1):
            if at + k > H: break
            if k < SPEED // 2: source_bad |= hot[at + k]
            else: target_bad |= hot[at + k]
        for d in DIRS:
            targets = spread(origins & ~source_bad, d) & ~target_bad
            if arrive <= H:
                reach[arrive] |= targets
            elif at + SPEED // 2 <= H:
                reach[H] |= targets
    cells = {cell for cell, bit in BITS.items() if reach[H] & bit}
    result = {'alive': bool(cells), 'count': len(cells), 'cells': cells,
              'complete': tl.complete, 'dynamic': tl.dynamic,
              'scope': 'fixed_bombs_movement_only'}
    cache[key] = result
    s._survival = cache
    return result
