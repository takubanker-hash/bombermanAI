from bomberman_ai.agents import Agent, make_agent
from bomberman_ai.evaluate import match
from bomberman_ai.learn import reward_of, train
from bomberman_ai.state import GameState
from bomberman_ai.temporal import survival


class BombOnce(Agent):
    def __init__(self): self.calls = 0
    def act(self, s, me, rng):
        self.calls += 1
        return 'STAY/BOMB' if self.calls == 1 else 'STAY'


class RepeatBomb(Agent):
    def act(self, s, me, rng): return 'STAY/BOMB'


def test_agent_state_is_reset_between_games_and_input_untouched():
    a = BombOnce()
    result = match(a, make_agent('defense'), 2, max_frames=3)
    assert result['bombs_placed'] == 2
    assert a.calls == 0


def test_invalid_placement_attempts_not_counted_as_bombs():
    result = match(RepeatBomb(), make_agent('defense'), 2, max_frames=3)
    assert result['bombs_placed'] == 2  # six requests, only two placements


def test_no_default_reward_for_score_or_bomb_spam():
    base = dict(win_rate=0, loss_rate=0, self_kill_rate=0, games=2, kills=0,
                mean_routes_cut=0, bombs_placed=0, mean_D=1, mean_F=1)
    spam = dict(base, mean_routes_cut=4, bombs_placed=2000, mean_D=100, mean_F=100)
    assert reward_of(base) == reward_of(spam) == 0


def test_roundtrip_flames_supported_by_safety():
    s = GameState.initial()
    s.flames[(2, 0)] = (10, 0)
    t = GameState.from_dict(__import__('json').loads(s.to_json()))
    assert survival(t, 0, 20)['alive']


def test_zero_outcome_signal_does_not_change_weights(tmp_path):
    # Two frames cannot produce a death; unlike old normalized noise updates,
    # all identical outcome rewards MUST leave weights unchanged.
    m = train(iters=1, pop=2, games=2, max_frames=2, opponent='self',
              out=str(tmp_path/'model.json'))
    from bomberman_ai.defense import DEFAULT_WEIGHTS
    assert m['wD'] == DEFAULT_WEIGHTS
    assert not m['history'][0]['accepted']
    assert m['history'][0]['no_terminal_signal']
