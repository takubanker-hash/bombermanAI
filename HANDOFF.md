# HANDOFF — GPT への引き継ぎ

作成: 2026-09-20（Claude）。リポジトリ: https://github.com/takubanker-hash/bombermanAI 、対象ブランチ: `main`。

## いま動く範囲

- シミュレータ `engine.step`: 移動、柱・爆弾の当たり判定、設置、爆発（8マス・柱で停止）、誘爆（10コマ後）、爆炎30コマ、
  キック（滑走・停止）、パンチ（3マス飛行・着地・気絶）、拾う／投げる（抱え中は爆発しない・着地からカウント）、硬直、死亡・勝敗・時間切れ。
  乱数を使わず決定論的。リプレイの保存・再生で同一結果を確認済み（`tests/test_engine.py::test_determinism_and_replay_roundtrip`）。
- Safety Solver `safety.py`: 燃え始め時刻 L（誘爆の連結つき）、逃げ込めるマス、逃走路数、時間余裕、到達可能マス。幅優先で 1 回 約1ms。
- D（守備）・F（攻撃）: 特徴量／重み／選択を分離。`CombinedAgent` は危険時 D、安全時 F + mix×D。攻撃候補にも自分の生存（`self_area`, `self_dead` 拒否）と
  相手の応手への頑健さ（`robust`）を入れている。
- 学習 `learn.py`: 進化戦略で wD / wF を更新。反復ごとに勝率・自爆率・mean_D・mean_F・mean_routes_cut を記録（評価点稼ぎの確認用）。
- 評価 `evaluate.py`: ランダム・ルール・学習前（手動重み）との対戦で勝率・自爆率・攻撃成功率・逃走路の削減量。シード固定で再現可能。
- 橋渡し `bridge/from_analysis.py`: 動画解析の場面データ → GameState。実戦局面（試合11 の詰みパターン）で読み込みと安全ソルバーの実行を確認済み。
- テスト 22 件（ルール 12・安全ソルバー 5・エージェント/学習の煙テスト 5）。`python -m pytest -q` 約10秒。

## 実測した学習前後の結果（小さな設定、1試合 1800 コマ = 30 秒、各 4 試合、シード 100）

学習前（手動の初期重み）:

| 相手 | win_rate | draw_rate | self_kill_rate | attack_success_rate | mean_routes_cut | mean_frames |
|---|---|---|---|---|---|---|
| random | 1.000 | 0.000 | 0.000 | 0.000 | 0.667 | 185.500 |
| rule | 0.000 | 1.000 | 0.000 | 0.000 | 1.333 | 1800.000 |
| untrained | 0.000 | 1.000 | 0.000 | 0.000 | 1.698 | 1800.000 |

学習（守備 2 反復 → 攻撃 2 反復、母集団 4、各 2 試合、相手 rule。合計約 3.5 分）の反復ログ:

  - {"iter": 0, "role": "defense", "base_reward": 0.256, "pop_mean_reward": 0.267, "win_rate": 0.0, "self_kill_rate": 0.0, "mean_D": 1.12, "mean_F": 0.576, "mean_routes_cut": 1.333, "seconds": 52.0}
  - {"iter": 1, "role": "defense", "base_reward": 0.279, "pop_mean_reward": 0.269, "win_rate": 0.0, "self_kill_rate": 0.0, "mean_D": 2.383, "mean_F": 0.384, "mean_routes_cut": 1.592, "seconds": 53.8}
  - {"iter": 0, "role": "offense", "base_reward": 0.219, "pop_mean_reward": 0.27, "win_rate": 0.0, "self_kill_rate": 0.0, "mean_D": 2.811, "mean_F": 0.125, "mean_routes_cut": 1.143, "seconds": 53.5}
  - {"iter": 1, "role": "offense", "base_reward": 0.254, "pop_mean_reward": 0.264, "win_rate": 0.0, "self_kill_rate": 0.0, "mean_D": 2.495, "mean_F": 0.209, "mean_routes_cut": 1.393, "seconds": 43.1}

学習後（`runs/model.json`）:

| 相手 | win_rate | draw_rate | self_kill_rate | attack_success_rate | mean_routes_cut | mean_frames |
|---|---|---|---|---|---|---|
| random | 1.000 | 0.000 | 0.000 | 0.000 | 0.667 | 185.500 |
| rule | 0.000 | 1.000 | 0.000 | 0.000 | 1.286 | 1800.000 |
| untrained | 0.000 | 1.000 | 0.000 | 0.000 | 0.893 | 1800.000 |

重みの変化（初期値との差）: wD: safe_area -0.92, routes +0.98, slack -0.89, on_line +1.09, mobility +1.58, deadend -1.70, own_danger -0.97, dist_opp -0.18 / wF: area_cut +1.99, routes_cut -0.57, future_cut -0.64, chain -0.33, timing -1.03, self_area -1.71, lag_danger +0.82, kill +0.41, robust +0.31, approach -0.40, proximity -0.05

注意: 母集団 4・各 2 試合・学習率 0.5 なので、この重みの変化はほぼ雑音（報酬差が小さい）。実運用では母集団と試合数を増やし学習率を下げること。

結論: 学習処理は動き、重みは更新される（報酬は形づくり項で差が付く）が、この設定では勝率・攻撃成功率は 0 のまま。
「評価点（mean_D・mean_routes_cut）は動くのに勝率が動かない」状態で、そのまま学習を続けると評価点稼ぎになり得る。まず下記 1〜2 の改善が必要。

読み方: ランダム相手は自分の爆弾で自滅するため勝率 1.0 になるが「攻撃で倒した」わけではない（attack_success_rate を見る）。
ルール相手・学習前の手動重み相手は引き分けが多い。**現状の主な課題は「誰も死なない」こと**で、学習の勾配が出にくい。

## 残る不具合・未完成（完成扱いにしていない）

1. **決着が付かない**: 両者とも安全ソルバーで確実に逃げるため、30 秒〜2 分の対戦でほぼ引き分け。トラップ（相手の逃走路を蹴りで塞ぐ、投げで頭に当てる等）を
   F がまだ選べていない。`kill` は 6 コマの先読みでしか検出しないので、150 コマ先の爆発で倒す計画が立たない。
2. **学習の信号が弱い**: 引き分けだと報酬が同じになり更新がゼロになる。形づくり（逃走路の削減・設置数）を小さく足したが、これだけが伸びる「評価点稼ぎ」に注意。
3. **速度**: CombinedAgent は 30 秒の対戦に約 8〜12 秒（rule 相手）、combined 同士は約 60 秒。学習は小さな設定でも数分〜十数分。
   高価な特徴（`future_cut`, `robust`）は上位 4 候補にしか計算していない。
4. **ルールの仮定**（SPEC.md）: キック速度、飛行時間、気絶、硬直、同時設置数、投げ距離、着地の処理、移動途中の方向転換、両者同時行動の順序。
   映像で確かめられるものは bomberman-analysis の実測に置き換える（例: `all_moves.csv` の蹴り区間の時間、`all_bombs.csv` の held_f）。
5. **未実装**: 時間切れ前のステージ縮小、READY/GO の演出、プレイヤー同士の衝突、盤外へ飛んだ爆弾の折り返し。
6. `escape_routes` の「最初の一歩」は最短経路の第一歩で数える近似（同じ方向から入る別経路は 1 本と数える）。

## GPT が最初に更新すべきファイルと改善課題

1. `bomberman_ai/offense.py` — F の改善。(a) 相手の逃げ場を「爆発時刻まで」評価する長い先読み（例: 150 コマ後の L を使った相手の生存可否）、
   (b) キック／投げで相手の逃走路を塞ぐ候補の生成（現状は移動先に爆弾があれば自動キックになるだけ）、(c) `robust` を相手の設置・キックも含めて評価。
2. `bomberman_ai/defense.py` — D の改善。`routes` の数え方、`mobility` の窓、相手の位置を踏まえた「詰まされにくさ」。
3. `bomberman_ai/safety.py` — 相手のキック・パンチ・投げで爆弾が動く可能性を考慮した「保証つき安全」（min-max 版）。
4. `bomberman_ai/learn.py` — 学習方法。自己対戦（`--opponent self`）、報酬の設計、反復ごとの評価点と勝率の突き合わせ。
5. `bomberman_ai/constants.py` / `SPEC.md` — 仮定の値を映像の実測で更新。

## 共有

- GitHub: https://github.com/takubanker-hash/bombermanAI （main に push 済み）。`git clone https://github.com/takubanker-hash/bombermanAI.git`
- リポジトリ一式（履歴つき）を渡す場合: `git bundle create bomberman-ai.bundle --all`（受け取り側は `git clone bomberman-ai.bundle`）。
- 秘密情報・個人データは含めていない（配信者名は SPEC.md にも書いていない）。

## 動画解析プロジェクトとの接続

- 仕様の出典は `../bomberman-analysis`（analysis/escape.py, events.py, link_throws.py, RECIPES.md）。
- `bridge/from_analysis.py` で `report/replay_data.js` の場面を GameState にでき、実戦局面で AI の行動と人間の行動を比べられる。
- 解析側の統計（負けの決め手: 自滅／キック／パンチ被弾、逃げ場の推移、有利時間）は評価指標の目標値になる。

## 手動検証（2026-09-21、ユーザー依頼「爆弾のタイミングやパンチ・キックが正しく反映されているか確認したい」）

`python verify_manual.py` で、盤面を実際に描きながら1コマずつ確認できる（pytest とは別に、目で追える形の検証）。
確認した項目と結果:

1. **爆弾のタイマー**: 設置コマ + FUSE(150) でちょうど爆発し、その場にいた本人が own_bomb で死亡する。
2. **キック**: キックした本人は動かず、爆弾だけ KICK_STEP(5) コマで1マスずつ滑る。盤の端で正しく止まる。
3. **パンチ**: PUNCH_DIST(3) マス先へ飛ぶ。飛行中も着地後も爆発予定コマ(explode_at)は変化しない（タイマーは動き続けるだけ）。
4. **拾って投げる**: 抱えている間は explode_at=-1 になり、本来の爆発予定コマを過ぎても爆発しない。投げて THROW_DIST(6) マス先へ着地すると、
   着地コマ + FUSE で新しく爆発予定が入り、着地マスにいた相手は STUN(60) コマ気絶する。
5. **誘爆**: 爆風が別の爆弾に当たると、その爆弾は着弾コマ + CHAIN_DELAY(10) コマ後に爆発する。

**動画解析（bomberman-analysis）の実測との照合**（`all_bombs.csv` / `all_moves.csv`）:

| 項目 | シミュレータの定数 | 映像の実測（中央値） |
|---|---|---|
| 爆弾の寿命（設置→爆発） | FUSE=150 | 148（n=2556） |
| パンチの飛距離 | PUNCH_DIST=3 | 3.0（n=843） |
| 投げの飛距離 | THROW_DIST=6 | 6.0（n=47） |

いずれも一致しており、既存の pytest 22件と合わせて、爆弾のタイミング・キック・パンチ・投げの実装は仕様どおりに動いていることを確認した。
GPT が仕様を変更する場合は `verify_manual.py` も併せて実行し、数値がずれていないか確認すること。

