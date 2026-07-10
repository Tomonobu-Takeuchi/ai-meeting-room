"""
scheduler.py - アプリ内蔵バックグラウンドスケジューラ（APScheduler）

Railway Hobbyプランはcronジョブ機能に非対応のため、既存のGunicornプロセス内で
BackgroundSchedulerを常時稼働させる方式を採用する（Procfile: --workers 1 のため
複数ワーカーによるジョブ多重登録は発生しない）。

毎日03:00(JST)に以下を実行:
  1. access_logsのうち保持期間(90日)を超えたレコードを削除
  2. pending_deletion_at（退会申請から90日経過）に達したユーザーの完全削除
"""
import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from src.database import purge_old_access_logs, get_users_pending_hard_delete, hard_delete_user

ACCESS_LOG_RETENTION_DAYS = 90

_scheduler = None


def daily_maintenance_job():
    """アクセスログ90日パージ＋退会90日経過アカウントの完全削除"""
    try:
        purge_old_access_logs(ACCESS_LOG_RETENTION_DAYS)
    except Exception as e:
        print(f"⚠ アクセスログパージ失敗: {e}")

    try:
        user_ids = get_users_pending_hard_delete()
    except Exception as e:
        print(f"⚠ 退会対象ユーザー取得失敗: {e}")
        user_ids = []

    for uid in user_ids:
        try:
            hard_delete_user(uid)
            print(f"✅ 退会90日経過アカウント削除完了: user_id={uid}")
        except Exception as e:
            print(f"⚠ アカウント削除失敗 user_id={uid}: {e}")


def init_scheduler():
    """スケジューラを起動する（二重起動防止ガード付き）"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    _scheduler.add_job(
        daily_maintenance_job, 'cron', hour=3, minute=0,
        id='daily_maintenance', replace_existing=True,
    )
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
    return _scheduler
