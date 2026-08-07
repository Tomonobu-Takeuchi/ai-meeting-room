"""
AI-PERSONA会議室 - 設定定数

AIモデル名を一元管理する。モデルを変更する場合は本ファイルのみを修正すること。
（2026年8月7日 MODEL-CONST-1 にて新設。従来はsrc/main.py・src/meeting/meeting_room.py
　の計11箇所にハードコードされていた）
"""

# 会議中のペルソナ・ファシリテータ発言、およびLayer1〜3レポート生成に使用
MODEL_SONNET = "claude-sonnet-4-6"

# 推奨ペルソナ提案・危機検知・課題抽出・収束抽出など、補助的な処理に使用
MODEL_HAIKU = "claude-haiku-4-5"
