"""Deterministic match/replay to a self-contained browser viewer."""
import json
from pathlib import Path

from .engine import step


def snapshots(initial, actions):
    """Keep only visual data; use engine.step for every recorded action."""
    state = initial
    result = [snapshot(state, ("STAY", "STAY"), [])]
    for pair in actions:
        before = len(state.log)
        state = step(state, *pair)
        result.append(snapshot(state, pair, state.log[before:]))
        if state.done():
            break
    return result


def snapshot(state, actions, events):
    return {
        "t": state.frame, "winner": state.winner, "actions": list(actions), "events": events,
        "players": [{"c": p.c, "r": p.r, "dc": p.dc, "dr": p.dr, "prog": p.prog,
                     "alive": p.alive, "face": p.face, "stun": p.stun_until,
                     "lag": p.lag_until, "holding": p.holding, "queued": p.queued}
                    for p in state.players],
        "bombs": [{"id": b.id, "c": b.c, "r": b.r, "owner": b.owner,
                   "explode_at": b.explode_at, "held": b.held, "fly_to": b.fly_to,
                   "land_at": b.land_at, "slide": b.slide}
                  for b in state.bombs],
        "flames": [[c, r, until, owner] for (c, r), (until, owner) in state.flames.items()],
    }


def write_html(path, initial, actions, meta=None):
    from .constants import COLS, ROWS, FPS, FUSE, SPEED, is_pillar

    frames = snapshots(initial, actions)
    data = {"meta": meta or {}, "fps": FPS, "fuse": FUSE, "speed": SPEED,
            "cols": COLS, "rows": ROWS, "pillars": [[c, r] for c in range(COLS)
                                                  for r in range(ROWS) if is_pillar(c, r)],
            "frames": frames}
    # JSON in a script element must not be able to terminate the script tag.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    template = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
    out = template.replace("__REPLAY_DATA__", payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(out, encoding="utf-8")
    return target
