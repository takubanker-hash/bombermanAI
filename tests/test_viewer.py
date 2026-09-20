import json
import re

from bomberman_ai.engine import step
from bomberman_ai.state import GameState
from bomberman_ai.viewer import snapshots, write_html


def test_browser_snapshots_follow_engine_and_preserve_events(tmp_path):
    initial = GameState.initial(p0=(0, 0), p1=(12, 10))
    actions = [("STAY/BOMB", "STAY")] + [("STAY", "STAY")] * 150
    frames = snapshots(initial, actions)
    state = initial
    for i, pair in enumerate(actions, 1):
        state = step(state, *pair)
        assert frames[i]["t"] == state.frame
        assert frames[i]["players"][0]["alive"] == state.players[0].alive
        assert len(frames[i]["bombs"]) == len(state.bombs)
    assert any("exploded" in event for frame in frames for event in frame["events"])
    assert frames[-1]["winner"] == 1
    out = write_html(tmp_path / "match.html", initial, actions, {"a": "combined", "b": "rule"})
    page = out.read_text(encoding="utf-8")
    payload = json.loads(re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', page).group(1))
    assert payload["frames"] == json.loads(json.dumps(frames))
    assert payload["meta"]["a"] == "combined"
