import html
import logging
import time
from datetime import datetime

from telegram.constants import ParseMode

import backup
import db
import feeds
import templates
from config import (
    ADMIN_IDS,
    BRAND_REMARK,
    CONFIG_POST_HOUR,
    CONFIG_SOURCE,
    CONFIGS_PER_POST,
    MINER_URL,
    POST_CHANNEL,
    PROXIES_PER_POST,
    PROXY_POST_HOUR,
    PROXY_SOURCE,
)
from ui import BLUE, GREEN, KEYCAPS, btn, kb

log = logging.getLogger("kingproxy.jobs")


async def notify_admins(bot, text):
    for uid in ADMIN_IDS:
        try:
            await bot.send_message(uid, text, parse_mode=ParseMode.HTML)
        except Exception as e:
            log.warning("notify %s failed: %s", uid, e)


# ───────────────────────── بروزرسانی منابع ─────────────────────────
async def refresh_feeds(bot=None):
    """کانفیگ و پروکسی جدید را از کانال‌های منبع بروز می‌کند."""
    result = {"configs": 0, "proxies": 0, "errors": [], "diag": []}
    plan = (
        ("configs", "config", CONFIG_SOURCE),
        ("proxies", "proxy", PROXY_SOURCE),
    )
    for table, kind, channel in plan:
        try:
            found, diag = await feeds.scrape(channel, kind)
            known = db.known_keys(table)
            new = [(k, l) for k, l in found if k not in known]
            checked = await feeds.check_alive(new, kind) if new else []
            alive = sum(1 for _, _, a in checked if a)
            result[table] = db.add_items(table, checked, channel)
            result["diag"].append(f"{channel}: {diag} | جدید: {len(new)} | زنده: {alive}")
        except Exception as e:
            log.exception("refresh %s failed", channel)
            result["errors"].append(f"{channel}: {e}")
    db.set_setting("last_refresh", db.now_str())
    db.set_setting("last_diag", "\n".join(result["diag"] + result["errors"]))
    db.trim()
    return result


async def refresh_job(context):
    await refresh_feeds(context.bot)


async def backup_job(context):
    await backup.backup_now(context.bot)


# ───────────────────────── ساخت پست‌ها ─────────────────────────
def build_proxy_post(rows, bot_username):
    text = templates.proxy_post(len(rows), bot_username)
    buttons = [
        btn(templates.proxy_button_label(i), url=r["link"], style=BLUE)
        for i, r in enumerate(rows, 1)
    ]
    grid = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    grid.append(
        [
            btn("🤖 ربات کینگ پروکسی", url=f"https://t.me/{bot_username}", style=GREEN),
            btn("📲 آموزش و دانلود", url=f"https://t.me/{bot_username}?start=apps", style=BLUE),
        ]
    )
    return text, kb(*grid)


def build_config_post(rows, bot_username):
    head, tail = templates.config_parts(bot_username)
    blocks = []
    for i, r in enumerate(rows, 1):
        link = feeds.rebrand(r["link"], f"{BRAND_REMARK} {i} | {POST_CHANNEL}")
        block = f"{KEYCAPS[(i - 1) % 10]} <code>{html.escape(link)}</code>"
        if len(head) + len("\n\n".join(blocks + [block])) + len(tail) > 3900:
            break  # محدودیت ۴۰۹۶ کاراکتر تلگرام
        blocks.append(block)
    text = head + "\n\n".join(blocks) + tail
    markup = kb(
        [
            btn("🤖 دریافت کانفیگ بیشتر", url=f"https://t.me/{bot_username}", style=GREEN),
            btn("📲 آموزش و دانلود", url=f"https://t.me/{bot_username}?start=apps", style=BLUE),
        ]
    )
    return text, markup, len(blocks)


# ───────────────────────── ارسال به کانال ─────────────────────────
async def post_proxies(bot):
    await refresh_feeds(bot)
    rows = db.pick_for_post("proxies", PROXIES_PER_POST)
    if not rows:
        return False, "هیچ پروکسی‌ای موجود نیست\n" + db.get_setting("last_diag")
    text, markup = build_proxy_post(rows, bot.username)
    try:
        await bot.send_message(POST_CHANNEL, text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except Exception as e:
        return False, f"ارسال به کانال ناموفق بود: {e}"
    db.mark_posted("proxies", [r["id"] for r in rows])
    db.set_setting("last_proxy_post", db.today())
    await backup.backup_now(bot)
    return True, f"{len(rows)} پروکسی ارسال شد"


async def post_configs(bot):
    await refresh_feeds(bot)
    rows = db.pick_for_post("configs", CONFIGS_PER_POST)
    if not rows:
        return False, "هیچ کانفیگی موجود نیست\n" + db.get_setting("last_diag")
    text, markup, used = build_config_post(rows, bot.username)
    try:
        await bot.send_message(POST_CHANNEL, text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except Exception as e:
        return False, f"ارسال به کانال ناموفق بود: {e}"
    db.mark_posted("configs", [r["id"] for r in rows[:used]])
    db.set_setting("last_config_post", db.today())
    await backup.backup_now(bot)
    return True, f"{used} کانفیگ ارسال شد"


async def _run_daily(bot, name, hour, poster, label):
    now = datetime.now(db.TZ)
    if now.hour < hour or db.get_setting(f"last_{name}_post") == db.today():
        return
    # اگر قبلاً شکست خورده، هر ۳۰ دقیقه یک‌بار دوباره تلاش کن
    last_try = float(db.get_setting(f"try_{name}", "0") or 0)
    if time.time() - last_try < 1800:
        return
    db.set_setting(f"try_{name}", time.time())
    ok, info = await poster(bot)
    if ok:
        await notify_admins(bot, f"✅ پست روزانه‌ی {label} در کانال ارسال شد.\n{info}")
    elif db.get_setting(f"notified_{name}") != db.today():  # روزی فقط یک اعلان خطا
        db.set_setting(f"notified_{name}", db.today())
        await notify_admins(bot, f"⚠️ پست روزانه‌ی {label} انجام نشد:\n{html.escape(info)}")


async def autopost_tick(context):
    if db.get_setting("autopost", "1") != "1":
        return
    await _run_daily(context.bot, "proxy", PROXY_POST_HOUR, post_proxies, "پروکسی")
    await _run_daily(context.bot, "config", CONFIG_POST_HOUR, post_configs, "کانفیگ")


async def check_miner_page():
    """بررسی می‌کند صفحه‌ی استخراج روی GitHub Pages در دسترس است. (ok، توضیح)"""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.get(MINER_URL.split("?")[0])
        if r.status_code == 200 and "<html" in r.text.lower():
            return True, "صفحه‌ی استخراج در دسترس است ✅"
        return False, (
            f"صفحه‌ی استخراج باز نمی‌شود (HTTP {r.status_code}).\n"
            f"آدرس: {MINER_URL}\n"
            "۱) فایل miner.html باید در مخزن باشد\n"
            "۲) Settings ← Pages ← Source: Deploy from a branch ← main / (root) ← Save\n"
            "۳) ۱ تا ۲ دقیقه صبر کن و دوباره تست کن"
        )
    except Exception as e:
        return False, f"اتصال به صفحه‌ی استخراج ممکن نشد: {type(e).__name__}\n{MINER_URL}"
