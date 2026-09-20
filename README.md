# bomberman-ai — 対戦AI研究用シミュレータと攻守評価

スーパーボンバーマンR2（ギンギンパワー、1対1、壊せるブロック無し）のルールを、動画解析プロジェクト
（`../bomberman-analysis`）の実測から整理し、決定論的に再現できる Python シミュレータと、
守備評価 D・攻撃評価 F・簡単な学習と評価の土台を提供する。純Python、依存は pytest だけ。

- ルールの整理（確認済み／仮定、1コマ内の処理順序）: [SPEC.md](SPEC.md)
- 引き継ぎ（動く範囲、実測結果、残る不具合、最初に直すべき所）: [HANDOFF.md](HANDOFF.md)

## 起動・テスト・学習・評価

```bash
cd bomberman-ai
python -m pip install -r requirements.txt
python -m pytest -q                                   # ルール・安全ソルバー・エージェントのテスト（約10秒）

# 対戦（rule vs random を 4 試合、シード 0、リプレイを保存）
python -m bomberman_ai.cli match --a rule --b random --games 4 --seed 0 --replay runs/last.json
python -m bomberman_ai.cli replay --file runs/last.json          # 保存したリプレイを再生（同じ結果になる）

# 学習（守備の重みを更新 → 攻撃の重みを更新。1試合は 1800 コマ = 30 秒に短縮すると速い）
python -m bomberman_ai.cli train --role defense --iters 2 --pop 4 --games 2 --seed 0 --max-frames 1800 --out runs/model.json
python -m bomberman_ai.cli train --role offense --iters 2 --pop 4 --games 2 --seed 0 --max-frames 1800 --model runs/model.json --out runs/model.json

# 評価（ランダム・ルール・学習前の手動重みと対戦。学習前後の比較は --model の有無で）
python -m bomberman_ai.cli evaluate --games 6 --seed 100 --max-frames 1800 --out runs/eval_before.json
python -m bomberman_ai.cli evaluate --games 6 --seed 100 --max-frames 1800 --model runs/model.json --out runs/eval_after.json
```

再現性: 乱数は `random.Random(seed)` だけ（エンジンは乱数を使わない）。同じシード・同じ設定・同じモデルなら同じ結果になる。
モデル（重み）は JSON（`runs/model.json`: `wD`, `wF`, `mix`, `history`）。

## ファイルごとの役割

| ファイル | 役割 |
|---|---|
| `bomberman_ai/constants.py` | ゲーム定数（確認済み／仮定の印つき）。柱の判定 |
| `bomberman_ai/state.py` | 状態（プレイヤー・爆弾・爆炎）。複製、JSON 化、同一性キー |
| `bomberman_ai/actions.py` | 行動の文字列表現と合法行動 `legal_actions(state, i)` |
| `bomberman_ai/engine.py` | 1コマ進める `step(state, a0, a1)`。爆発・誘爆・キック・パンチ・投げ・気絶・硬直・死亡・勝敗 |
| `bomberman_ai/replay.py` | リプレイの保存・再生 |
| `bomberman_ai/safety.py` | Safety Solver。燃え始め時刻 L、逃げ込めるマス、逃走路、時間余裕、到達可能マス |
| `bomberman_ai/defense.py` | 守備評価 D: 特徴量 `defense_features` / 重み `DEFAULT_WEIGHTS` / 選択 `choose_defense`。先読み `lookahead` |
| `bomberman_ai/offense.py` | 攻撃評価 F: 特徴量 `offense_features` / 重み / 2段階の候補評価 `rank_candidates` / 頑健さ `robustness` |
| `bomberman_ai/agents.py` | RandomAgent / RuleAgent / DefenseAgent / OffenseAgent / CombinedAgent、`play_game` |
| `bomberman_ai/evaluate.py` | 対戦評価（勝率・自爆率・攻撃成功率・逃走路の削減量）と学習前後の比較表 |
| `bomberman_ai/learn.py` | 初期学習処理（進化戦略で D・F の重みを更新、報酬ハックの確認用ログ） |
| `bomberman_ai/cli.py` | コマンド入口（match / train / evaluate / replay） |
| `bridge/from_analysis.py` | 動画解析の replay_data.js の 1 コマを GameState に変換（解析側との接続） |
| `tests/` | ルール（12）、安全ソルバー（5）、エージェント・学習の煙テスト（5） |

## AI に渡す状態と返す行動

- 状態: `GameState`（完全情報）。`players[i]`: マス `(c, r)`、移動方向 `(dc, dr)` と進み `prog`（0..5）、向き `face`、`alive`、
  `stun_until`、`lag_until`、`holding`。`bombs`: `(c, r)`、`owner`、`explode_at`（抱え中は -1）、滑り `slide`、飛行 `fly_to/land_at`。
  `flames`: `{(c, r): (消えるコマ, 持ち主)}`。`frame`、`winner`（None/0/1/-1）。
- 行動: 文字列 `"<移動>/<操作>"`。移動 = `STAY/U/D/L/R`（移動先に爆弾があればキック）、操作 = `BOMB/PUNCH/PICKUP/THROW`。
  例 `"R"`, `"L/BOMB"`, `"STAY/PUNCH"`。合法行動は `actions.legal_actions(state, i)`。
- エージェント: `agent.act(state, me, rng) -> str`。移動中は前の移動を続け、判断はマスの中心で行う。

## 評価関数の構成

- D（守備）: `safe_area`, `routes`, `slack`, `on_line`, `mobility`, `deadend`, `own_danger`, `dist_opp`, `dead`（拒否）。
- F（攻撃）: `area_cut`, `routes_cut`, `future_cut`, `chain`, `timing`, `self_area`, `self_dead`（拒否）, `lag_danger`, `kill`, `robust`。
- 統合（CombinedAgent）: 危険時は D で逃げる。安全時は全候補について `F + mix × D(候補後)` を最大化。
  `robust` は相手の各移動に対して自分の逃げ場が残る割合で、「相手の行動を固定して得た安全」を保証と扱わないための項。

## ルールの未確定事項（仮定として実装）

キックの滑る速さ（1マス5コマ）、パンチ／投げの飛行時間（20コマ）、気絶の長さ（60コマ）、硬直（10コマ）、同時設置数（8）、
投げの距離（6マス）、着地先が塞がっている時の処理、盤外への飛行（端で止まる）、移動途中の方向転換（反転のみ）、
プレイヤー同士のすり抜け、両者同時行動の処理順序。詳細は SPEC.md。

## 動画解析プロジェクトとの接続

`bridge/from_analysis.py` が `report/replay_data.js` の場面の 1 コマを GameState にする。
`python bridge/from_analysis.py ../bomberman-analysis/report/replay_data.js 600` で、実戦の局面を AI に見せて行動を比べられる。
解析側の「逃げ込めるマス」（`analysis/escape.py`）と `safety.py` は同じ定義なので、値を突き合わせて検証できる。
