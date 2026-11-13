"""
چون GitHub Actions بعد از هر اجرا همه‌چیز را پاک می‌کند، دیتابیس را داخل چت خودِ ادمین
(به صورت یک فایل پین‌شده) نگه می‌داریم و موقع روشن شدن دوباره از همان‌جا برمی‌گردانیم.
"""
import logging
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from telegram import InputMediaDocument
from telegram.error import BadRequest, TelegramError

import db
from config import ADMIN_IDS

log = logging.getLogger("kingproxy.backup")

NAME = "kingproxy-backup.db"
BACKUP_CHAT = sorted(ADMIN_IDS)[0]
TMP = Path(tempfile.gettempdir())

_msg_id = None
_last = 0.0


def _snapshot():
    out = TMP / NAME
    out.unlink(missing_ok=True)
    src = sqlite3.connect(db.DB_PATH)
    dst = sqlite3.connect(out)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return out


def _valid(path):
    try:
        c = sqlite3.connect(path)
        c.execute("SELECT COUNT(*) FROM users").fetchone()
        c.close()
        return True
    except Exception:
        return False


def restore_file(path):
    """یک فایل .db را جایگزین دیتابیس فعلی می‌کند."""
    if not _valid(path):
        return False
    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, db.DB_PATH)
    db.init()  # جدول‌های جدید (اگر نسخه عوض شده) اضافه می‌شوند
    return True


async def restore_latest(bot):
    """آخرین بکاپِ پین‌شده در چت ادمین را برمی‌گرداند. True اگر موفق بود."""
    global _msg_id
    try:
        chat = await bot.get_chat(BACKUP_CHAT)
        pm = chat.pinned_message
        if not (pm and pm.document and pm.document.file_name == NAME):
            log.info("no backup found")
            return False
        f = await bot.get_file(pm.document.file_id)
        tmp = TMP / "restore.db"
        await f.download_to_drive(tmp)
        if restore_file(tmp):
            _msg_id = pm.message_id
            log.info("database restored from backup")
            return True
    except TelegramError as e:
        log.warning("restore failed: %s", e)
    return False


async def backup_now(bot, force=False):
    """اگر دیتابیس عوض شده باشد (یا force) بکاپ را در چت ادمین بروز می‌کند."""
    global _msg_id, _last
    if not db.DB_PATH.exists():
        return False
    if not force and db.DB_PATH.stat().st_mtime <= _last:
        return False
    path = _snapshot()
    caption = f"💾 بکاپ دیتابیس\n🕒 {db.now_str()}\n👥 {db.stats()['total']} کاربر"
    if _msg_id:
        try:
            with open(path, "rb") as f:
                await bot.edit_message_media(
                    chat_id=BACKUP_CHAT,
                    message_id=_msg_id,
                    media=InputMediaDocument(f, caption=caption, filename=NAME),
                )
            _last = time.time()
            return True
        except BadRequest as e:
            if "not modified" in str(e).lower():
                _last = time.time()
                return True
            log.warning("edit backup failed (%s) → sending new", e)
            _msg_id = None
        except TelegramError as e:
            log.warning("backup failed: %s", e)
            return False
    try:
        with open(path, "rb") as f:
            m = await bot.send_document(
                BACKUP_CHAT, f, filename=NAME, caption=caption, disable_notification=True
            )
        _msg_id = m.message_id
        _last = time.time()
        try:
            await bot.pin_chat_message(BACKUP_CHAT, m.message_id, disable_notification=True)
        except TelegramError as e:
            log.warning("pin failed: %s", e)
        return True
    except TelegramError as e:
        log.warning("backup send failed: %s", e)
        return False
