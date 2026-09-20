"""Render the checked-in measured JSON results; does not simulate missing runs."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
STAGES = [
 ('00_original.json', '0. 受領時の実装・評価'),
 ('01_metrics_fixed.json', '1. 試合間リセット・設置実数の修正'),
 ('02_temporal_attack.json', '2. 時間付き予測・攻撃継続：守備の退行あり'),
 ('03_optimized.json', '3. 予測の高速化：2と同じ対戦結果'),
 ('04_counterfactual_defense.json', '4. 時間差バイアス・柱迂回・炎消滅後の逃走を修正'),
 ('05_after_training.json', '5. 守備・攻撃の学習後：改善が検証されず重みを据え置き'),
 ('06_aggressive_trial.json', '6. 攻撃重みを強めた手動候補の予備比較（2試合）'),
 ('07_aggressive_suite.json', '7. 手動候補の通常評価（各4試合）'),
 ('08_frozen_opponents.json', '8. 改修前コミットの相手を固定した追加評価'),
 ('09_trained_aggressive.json', '9. 攻撃候補を自己対戦学習した後の評価'),
 ('10_windup_default.json', '10. 発動前硬直を統合後：手動初期重み'),
 ('11_windup_transferred_model.json', '11. 発動前硬直を統合後：旧学習モデルの移植'),
 ('12_windup_trained.json', '12. 新ルールで自己対戦学習した後の評価'),
]
lines = ['# 対戦AI改修の実測結果', '',
 '00〜09は発動前硬直の追加前。10以降は上流c2380f7の発動前硬直を含む（統合コミット6f25f23）。',
 '基準コミット：`bd8048b049543a034fbe3c41ff23eeff9812a35d`。実装コミット：`fd964ee7c9cda38bc4751fcbd3504e9de7b2177f`。', '',
 '通常評価はseed=100、上限1800コマ、左右交代、各4試合（予備比較のみ2試合）。',
 '4試合は小規模な退行確認。決定論的な相手は左右2条件の繰り返しで、独立4標本ではない。',
 'ステージ0は旧計測、1以降は各試合でAIをリセットし設置成功数で集計する。',
 'rule/untrainedは各版の安全判定を使用するため、旧相手そのものとの比較はステージ8を参照。',
 'mean_D/Fは重みと特徴量の変更にも影響される。数値の上昇だけで強くなったとは判断しない。', '']
for filename, title in STAGES:
    path = ROOT/filename
    if not path.exists(): continue
    data = json.loads(path.read_text())
    lines += ['## '+title, '', f'原データ：[{filename}]({filename})', '',
              '| 相手 | 試合 | 勝率 | 敗率 | 分率 | 自爆率 | 攻撃成功率 | 逃走路削減 | mean_D | mean_F | 秒 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for opponent, r in data.items():
        keys = ('win_rate','loss_rate','draw_rate','self_kill_rate','attack_success_rate','mean_routes_cut','mean_D','mean_F','seconds')
        lines += ['| '+opponent+' | '+str(r['games'])+' | '+' | '.join(f'{r.get(k,0):.3f}' for k in keys)+' |']
    lines.append('')
lines += ['## 学習の実測', '',
          '| モデル | 反復 | 役割 | 母集団 | 試合/候補 | 検証前勝率 | 提案勝率 | 採用 | 評価点のみ改善 | 報酬差 |',
          '|---|---:|---|---:|---:|---:|---:|---|---|---:|']
for filename in ('model_defense.json','model_offense.json','model_aggressive_trained.json','model_windup.json'):
    path=ROOT/filename
    if not path.exists(): continue
    model=json.loads(path.read_text())
    # The most recent entry belongs to this run; previous entries are inherited.
    for h in model.get('history', [])[-1:]:
        lines += [f"| {filename} | {h['iter']} | {h['role']} | {h['population']} | {h['games']} | {h['before']['win_rate']:.3f} | {h['proposed']['win_rate']:.3f} | {h['accepted']} | {h['score_only_improvement']} | {h['reward_spread']:.3f} |"]
lines += ['', '学習は人工近接局面（`--curriculum`）。通常初期盤面の勝率とは混ぜない。',
          '検証で採用されなかった重みは保存モデルに反映しない。手動候補の改善を学習の成果と呼ばない。',
          '新ルールでは初期重みの自爆率は0だがrule/untrainedに全引き分け。移植モデルはuntrainedに自爆2件で非推奨。通常対戦の勝率改善は未達。', '',
          '## 再実行', '', '```bash',
          'python -m bomberman_ai.cli evaluate --games 4 --seed 100 --max-frames 1800 --model experiments/aggressive_candidate.json --out runs/candidate_eval.json',
          'git worktree add --detach ../bomberman-ai-baseline bd8048b',
          'python experiments/compare_original.py --model experiments/aggressive_candidate.json --out runs/frozen_eval.json',
          'python experiments/make_report.py', '```', '',
          '旧ルールの00〜09は履歴上の測定。旧ルールの比較再実行には334dd95のworktreeを使用する。現在のコードは10以降の硬直ルールで動く。',
          '定数の実測置換は未実施。入力CSV・元映像がないためSPECの仮定値を維持した。', '']
(ROOT/'RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
