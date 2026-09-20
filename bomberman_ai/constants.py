# -*- coding: utf-8 -*-
"""ゲーム定数。出典は SPEC.md（「確認済み」= 動画解析の実測、「仮定」= 未確認の値）。"""
COLS = 13            # 確認済み: 盤面 13 列
ROWS = 11            # 確認済み: 盤面 11 行
FPS = 60             # 確認済み: 60 コマ/秒
FUSE = 150           # 確認済み: 設置から爆発まで 150 コマ（実測の中央値 148）
FIRE = 8             # 確認済み: 爆風は各方向に最大 8 マス（ギンギンパワー）
BURN = 30            # 確認済み: 爆炎の持続 30 コマ
CHAIN_DELAY = 10     # 確認済み: 爆風が別の爆弾に届くと、その爆弾は 10 コマ後に爆発
SPEED = 6            # 確認済み: 最大スピードで 1 マス 6 コマ（0.1 秒）
KICK_STEP = 5        # 仮定: 蹴られた爆弾は 1 マス 5 コマで滑る（実測: 1コマ0.1マス超）
PUNCH_DIST = 3       # 確認済み（中央値）: パンチで爆弾は 3 マス先に飛ぶ（実測 2〜5、着地先が塞がっていれば 1 マスずつ先へ）
THROW_DIST = 6       # 仮定: 抱えて投げた爆弾は 6 マス先に落ちる（実測の中央値 6、範囲 3〜9）
FLY_FRAMES = 20      # 仮定: パンチ・投げで飛んでいる時間 20 コマ（その間は爆発しない・当たらない）
STUN = 60            # 仮定: 頭に爆弾が落ちた側は 60 コマ動けない（「ぴよる」）
ACTION_LAG = 10      # 仮定: パンチ・投げの後 10 コマは移動できない（硬直）。設置は硬直なし
PUNCH_WINDUP = 6      # 仮定: パンチの振りかぶり動作。入力してから爆弾が実際に飛び出すまでの硬直（ユーザー確認: モーションによる硬直がある）
THROW_WINDUP = 6      # 仮定: 投げの振りかぶり動作。入力してから爆弾が実際に手を離れるまでの硬直
KICK_WINDUP = 6       # 仮定: キックの蹴り込み動作。入力してから爆弾が実際に滑り出すまでの硬直
                      # （ユーザー確認: 足元に置いた爆弾はその場では蹴れず、隣接マスから助走して蹴り込む必要があり、その蹴り込み動作自体にも時間がかかる）
MAX_BOMBS = 8        # 仮定: 同時に置ける爆弾 8 個（ギンギンパワー＝最大）
TIME_LIMIT = 120 * FPS   # 確認済み: 制限時間 2:00（時間切れは引き分け。ステージ縮小は未実装）
PICKUP_FRAMES = 6    # 仮定: 爆弾を拾い上げる動作 6 コマ

def is_pillar(c, r):
    """柱: 0始まりで奇数列×奇数行（確認済み）"""
    return (c % 2 == 1) and (r % 2 == 1)

def in_board(c, r):
    return 0 <= c < COLS and 0 <= r < ROWS

DIRS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# Calibration provenance: no measurement CSV/video was provided with this repo.
# Do not relabel these assumptions as measurements without sample/source evidence.
UNMEASURED_PARAMETERS = ("KICK_STEP", "FLY_FRAMES", "STUN", "ACTION_LAG",
                         "MAX_BOMBS", "THROW_DIST", "PICKUP_FRAMES",
                         "PUNCH_WINDUP", "THROW_WINDUP", "KICK_WINDUP")
