import asyncio
import csv
import html
import io
import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, RetryAfter
from telegram.ext import ContextTypes

import backup
import db
import jobs
import mining
from config import ADMIN_IDS, POST_CHANNEL
from feeds import fa_digits, jalali_date
from ui import BLUE, GREEN, LINE, RED, btn, kb, show

log = logging.getLogger("kingproxy.admin")


def is_admin(update: Update) -> bool:
    u = update.effective_user
    return bool(u and u.id in ADMIN_IDS)


# ───────────────────────── صفحه‌ها ─────────────────────────
def panel_text():
    s = db.stats()
    auto = "روشن ✅" if db.get_setting("autopost", "1") == "1" else "خاموش ❌"
    maint = "روشن 🔧" if db.get_setting("maintenance") == "1" else "خاموش ✅"
    return (
        "🛠 <b>پنل مدیریت KING PROXY</b>\n"
        f"{LINE}\n"
        f"👥 کاربران: <b>{fa_digits(s['total'])}</b>   🆕 امروز: <b>{fa_digits(s['new_today'])}</b>\n"
        f"🔑 کانفیگ آماده: <b>{fa_digits(s['configs'])}</b>   🛡 پروکسی آماده: <b>{fa_digits(s['proxies'])}</b>\n"
        f"⏰ ارسال خودکار: {auto}\n"
        f"🔧 حالت تعمیرات: {maint}\n"
        f"{LINE}\n"
        "یکی از گزینه‌ها را انتخاب کن 👇"
    )


def panel_kb():
    auto_on = db.get_setting("autopost", "1") == "1"
    maint_on = db.get_setting("maintenance") == "1"
    return kb(
        [btn("📊 آمار کامل", "adm:stats", style=BLUE), btn("🔄 بروزرسانی منابع", "adm:refresh", style=BLUE)],
        [btn("📢 پیام همگانی", "adm:bc", style=GREEN), btn("📤 ارسال به کانال", "adm:post", style=GREEN)],
        [
            btn(f"⏰ ارسال خودکار: {'روشن' if auto_on else 'خاموش'}", "adm:auto", style=GREEN if auto_on else RED),
            btn(f"🔧 تعمیرات: {'روشن' if maint_on else 'خاموش'}", "adm:maint", style=RED if maint_on else BLUE),
        ],
        [
            btn(f"💸 برداشت‌ها ({db.wd_stats()['pending']})", "adm:wdlist", style=GREEN),
            btn("🚫 مسدود / آزادسازی", "adm:ban", style=RED),
        ],
        [btn("👥 خروجی کاربران", "adm:export", style=BLUE), btn("💾 بکاپ دیتابیس", "adm:backup", style=BLUE)],
        [btn("🧪 تست صفحه استخراج", "adm:minertest", style=BLUE)],
        [btn("🏠 صفحه اصلی", "home", style=BLUE)],
    )


def back_kb():
    return kb([btn("⬅️ بازگشت به پنل", "adm:panel", style=BLUE)])


def stats_text():
    s = db.stats()
    ms = db.miner_stats()
    ws = db.wd_stats()
    f = fa_digits
    return (
        "📊 <b>آمار کامل ربات</b>\n"
        f"{LINE}\n"
        f"👥 کل کاربران: <b>{f(s['total'])}</b>\n"
        f"🆕 عضو شده امروز: <b>{f(s['new_today'])}</b>\n"
        f"🔥 فعال در ۲۴ ساعت: <b>{f(s['active_24h'])}</b>\n"
        f"🔔 اعلان روشن: <b>{f(s['notify_on'])}</b>\n"
        f"🚫 مسدود: <b>{f(s['banned'])}</b>\n"
        f"{LINE}\n"
        f"🔑 کانفیگ زنده: <b>{f(s['configs'])}</b>\n"
        f"🛡 پروکسی زنده: <b>{f(s['proxies'])}</b>\n"
        f"{LINE}\n"
        f"⛏ استخراج‌کننده‌ها: <b>{f(ms['miners'])}</b>   👆 کل ضربه‌ها: <b>{f(ms['taps'])}</b>\n"
        f"👥 دعوت‌های موفق: <b>{f(ms['invites'])}</b>   ₿ مجموع موجودی‌ها: <b>{mining.fmt_btc(ms['sat'])}</b>\n"
        f"💸 برداشت در انتظار: <b>{f(ws['pending'])}</b> ({mining.fmt_btc(ws['pending_sat'])} BTC)\n"
        f"✅ پرداخت‌شده: <b>{f(ws['paid'])}</b> ({mining.fmt_btc(ws['paid_sat'])} BTC)\n"
        f"🔄 آخرین بروزرسانی منابع: {db.get_setting('last_refresh') or '—'}\n"
        f"{LINE}\n"
        f"📤 آخرین پست پروکسی: {jalali_date(db.get_setting('last_proxy_post')) if db.get_setting('last_proxy_post') else '—'}\n"
        f"📤 آخرین پست کانفیگ: {jalali_date(db.get_setting('last_config_post')) if db.get_setting('last_config_post') else '—'}\n"
        f"📢 کانال: {POST_CHANNEL}"
    )


# ───────────────────────── دستور /admin ─────────────────────────
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    context.user_data.pop("await", None)
    await update.effective_message.reply_text(
        panel_text(), parse_mode=ParseMode.HTML, reply_markup=panel_kb()
    )


# ───────────────────────── دکمه‌ها ─────────────────────────
async def on_admin_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(update):
        return await q.answer("⛔️ دسترسی ندارید", show_alert=True)
    action = q.data.split(":", 1)[1]
    ud = context.user_data

    if action == "panel":
        ud.pop("await", None)
        await q.answer()
        return await show(update, panel_text(), panel_kb())

    if action == "wdlist":
        await q.answer()
        rows = db.wd_pending(8)
        if not rows:
            return await show(update, "💸 <b>درخواست‌های برداشت</b>\n\nدرخواستی در انتظار نیست ✅", back_kb())
        lines, buttons = [], []
        for r in rows:
            lines.append(
                f"<b>#{r['id']}</b> — {html.escape(r['name'] or '')} (<code>{r['user_id']}</code>)\n"
                f"💰 {mining.fmt_btc(r['sat'])} BTC\n👛 <code>{html.escape(r['address'])}</code>"
            )
            buttons.append(
                [
                    btn(f"✅ پرداخت #{r['id']}", f"adm:wdok:{r['id']}", style=GREEN),
                    btn(f"❌ رد #{r['id']}", f"adm:wdno:{r['id']}", style=RED),
                ]
            )
        return await show(
            update,
            "💸 <b>درخواست‌های برداشت</b>\n" + LINE + "\n" + "\n\n".join(lines),
            kb(*buttons, [btn("⬅️ بازگشت به پنل", "adm:panel", style=BLUE)]),
        )

    if action.startswith(("wdok:", "wdno:")):
        kind, _, raw = action.partition(":")
        approve = kind == "wdok"
        w = mining.decide_withdrawal(int(raw), approve) if raw.isdigit() else None
        if not w:
            return await q.answer("این درخواست قبلاً بررسی شده یا پیدا نشد", show_alert=True)
        await q.answer("✅ ثبت شد")
        try:
            if approve:
                note = (
                    f"✅ <b>برداشت #{w['id']} پرداخت شد</b>\n"
                    f"💰 {mining.fmt_btc(w['sat'])} BTC به آدرس <code>{html.escape(w['address'])}</code> ارسال شد.\n"
                    "💙 ممنون از همراهیت"
                )
            else:
                note = (
                    f"❌ <b>برداشت #{w['id']} رد شد</b>\n"
                    f"💰 {mining.fmt_btc(w['sat'])} BTC به موجودیت برگشت.\n"
                    f"برای اطلاعات بیشتر با پشتیبانی در ارتباط باش."
                )
            await context.bot.send_message(w["user_id"], note, parse_mode=ParseMode.HTML)
        except Exception as e:
            log.warning("notify user %s failed: %s", w["user_id"], e)
        text = ("✅ پرداخت‌شده" if approve else "❌ ردشده") + f" — درخواست #{w['id']} ({mining.fmt_btc(w['sat'])} BTC)"
        return await show(update, text, kb([btn("💸 درخواست‌ها", "adm:wdlist", style=GREEN)], [btn("⬅️ پنل", "adm:panel", style=BLUE)]))

    if action == "minertest":
        await q.answer("⏳ در حال بررسی...")
        ok, info = await jobs.check_miner_page()
        return await show(update, ("✅ " if ok else "❌ ") + html.escape(info), back_kb())

    if action == "stats":
        await q.answer()
        return await show(update, stats_text(), back_kb())

    if action == "refresh":
        await q.answer("⏳ در حال بروزرسانی...")
        r = await jobs.refresh_feeds(context.bot)
        text = (
            "🔄 <b>بروزرسانی انجام شد</b>\n"
            f"{LINE}\n"
            f"🔑 کانفیگ جدید: <b>{fa_digits(r['configs'])}</b>\n"
            f"🛡 پروکسی جدید: <b>{fa_digits(r['proxies'])}</b>\n"
        )
        if r["diag"]:
            text += "\n🔎 <b>گزارش:</b>\n" + "\n".join(html.escape(d) for d in r["diag"])
        if r["errors"]:
            text += "\n⚠️ خطاها:\n" + "\n".join(html.escape(e) for e in r["errors"])
        return await show(update, text, back_kb())

    if action == "post":
        await q.answer()
        return await show(
            update,
            "📤 <b>ارسال دستی به کانال</b>\nکدام پست الان در کانال ارسال شود؟",
            kb(
                [btn("🛡 پست پروکسی", "adm:post_proxy", style=BLUE), btn("🔑 پست کانفیگ", "adm:post_config", style=GREEN)],
                [btn("⬅️ بازگشت به پنل", "adm:panel", style=BLUE)],
            ),
        )

    if action in ("post_proxy", "post_config"):
        await q.answer("⏳ در حال ارسال...")
        poster = {
            "post_proxy": jobs.post_proxies,
            "post_config": jobs.post_configs,
        }[action]
        ok, info = await poster(context.bot)
        text = ("✅ " if ok else "❌ ") + html.escape(info)
        return await show(update, text, back_kb())

    if action == "auto":
        new = "0" if db.get_setting("autopost", "1") == "1" else "1"
        db.set_setting("autopost", new)
        await q.answer("ارسال خودکار " + ("روشن شد ✅" if new == "1" else "خاموش شد ❌"))
        return await show(update, panel_text(), panel_kb())

    if action == "maint":
        new = "0" if db.get_setting("maintenance") == "1" else "1"
        db.set_setting("maintenance", new)
        await q.answer("حالت تعمیرات " + ("روشن شد 🔧" if new == "1" else "خاموش شد ✅"))
        return await show(update, panel_text(), panel_kb())

    if action == "bc":
        ud["await"] = "broadcast"
        await q.answer()
        n = len(db.all_user_ids(notify_only=True))
        return await show(
            update,
            "📢 <b>پیام همگانی</b>\n"
            f"{LINE}\n"
            f"به <b>{fa_digits(n)}</b> کاربر (اعلان روشن) ارسال می‌شود.\n\n"
            "✍️ پیامت را همین‌جا بفرست (متن، عکس، ویدیو، فایل... هرچیزی).",
            kb([btn("❌ لغو", "adm:panel", style=RED)]),
        )

    if action == "bc_go":
        src = ud.pop("bc", None)
        if not src:
            return await q.answer("پیامی برای ارسال نیست", show_alert=True)
        await q.answer("⏳ ارسال شروع شد")
        status = await context.bot.send_message(q.message.chat_id, "⏳ در حال ارسال پیام همگانی...")
        context.application.create_task(run_broadcast(context.bot, src, status))
        return await show(update, panel_text(), panel_kb())

    if action == "ban":
        ud["await"] = "ban"
        await q.answer()
        return await show(
            update,
            "🚫 <b>مسدود / آزادسازی کاربر</b>\n\n"
            "آیدی عددی کاربر را بفرست.\n"
            "اگر مسدود باشد آزاد می‌شود و برعکس.",
            kb([btn("❌ لغو", "adm:panel", style=RED)]),
        )

    if action == "export":
        await q.answer("⏳ در حال ساخت فایل...")
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["user_id", "name", "username", "joined", "last_seen", "banned", "notify"])
        for r in db.export_users():
            w.writerow(list(r))
        data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
        await context.bot.send_document(
            q.message.chat_id, data, filename="users.csv", caption="👥 لیست کاربران"
        )
        return

    if action == "backup":
        ok = await backup.backup_now(context.bot, force=True)
        return await q.answer("💾 بکاپ انجام شد ✅" if ok else "❌ بکاپ ناموفق بود", show_alert=True)

    await q.answer()


# ───────────────────────── پیام‌های ادمین (حالت انتظار) ─────────────────────────
async def on_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    mode = context.user_data.get("await")
    msg = update.effective_message

    if mode == "broadcast":
        context.user_data.pop("await", None)
        context.user_data["bc"] = (msg.chat_id, msg.message_id)
        await msg.reply_text(
            "👆 این پیام برای همه ارسال شود؟",
            reply_markup=kb(
                [btn("✅ بله، ارسال کن", "adm:bc_go", style=GREEN), btn("❌ لغو", "adm:panel", style=RED)]
            ),
        )
        return

    if mode == "ban":
        context.user_data.pop("await", None)
        text = (msg.text or "").strip()
        if not text.isdigit():
            return await msg.reply_text("❌ آیدی عددی معتبر نیست.", reply_markup=back_kb())
        uid = int(text)
        if uid in ADMIN_IDS:
            return await msg.reply_text("😅 ادمین را نمی‌شود مسدود کرد.", reply_markup=back_kb())
        res = db.toggle_ban(uid)
        if res is None:
            return await msg.reply_text("❌ این کاربر در ربات پیدا نشد.", reply_markup=back_kb())
        word = "🚫 مسدود شد" if res else "✅ آزاد شد"
        return await msg.reply_text(f"کاربر <code>{uid}</code> {word}.", parse_mode=ParseMode.HTML, reply_markup=back_kb())


async def on_admin_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اگر ادمین فایل .db بفرستد، دیتابیس از روی آن بازیابی می‌شود."""
    if not is_admin(update):
        return
    doc = update.effective_message.document
    name = (doc.file_name or "") if doc else ""
    if not name.endswith(".db"):
        return
    f = await doc.get_file()
    tmp = Path(tempfile.gettempdir()) / "manual-restore.db"
    await f.download_to_drive(tmp)
    if backup.restore_file(tmp):
        s = db.stats()
        await update.effective_message.reply_text(
            f"✅ دیتابیس بازیابی شد.\n👥 {s['total']} کاربر"
        )
    else:
        await update.effective_message.reply_text("❌ فایل معتبر نیست.")


# ───────────────────────── ارسال همگانی ─────────────────────────
async def run_broadcast(bot, src, status):
    chat_id, msg_id = src
    ids = db.all_user_ids(notify_only=True)
    ok = fail = 0
    for i, uid in enumerate(ids, 1):
        for attempt in range(2):
            try:
                await bot.copy_message(uid, chat_id, msg_id)
                ok += 1
                break
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Forbidden:
                fail += 1
                break
            except Exception:
                fail += 1
                break
        else:
            fail += 1
        await asyncio.sleep(0.05)
        if i % 50 == 0:
            try:
                await status.edit_text(f"⏳ ارسال... {i}/{len(ids)}")
            except Exception:
                pass
    try:
        await status.edit_text(
            "✅ <b>ارسال همگانی تمام شد</b>\n"
            f"📬 موفق: <b>{ok}</b>\n❌ ناموفق: <b>{fail}</b>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass
