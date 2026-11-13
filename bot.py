import html
import json
import logging
import time
from urllib.parse import quote

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import admin
import backup
import db
import feeds
import jobs
import mining
import ui
from config import (
    ADMIN_IDS,
    BACKUP_EVERY,
    BANNER,
    BOT_TOKEN,
    BRAND_REMARK,
    LOCK_CHANNELS,
    POST_CHANNEL,
    REFRESH_EVERY,
    SUPPORT_USERNAME,
    WD_MIN_SAT,
)
from ui import BLUE, GREEN, KEYCAPS, LINE, btn, show, with_home

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("kingproxy")


# ───────────────────────── قفل کانال ─────────────────────────
async def is_member(context, user_id):
    """ربات باید در هر دو کانال ادمین باشد. نتیجه‌ی مثبت ۲ دقیقه کش می‌شود."""
    cache = context.application.bot_data.setdefault("member_cache", {})
    if cache.get(user_id, 0) > time.time():
        return True
    for ch in LOCK_CHANNELS:
        try:
            m = await context.bot.get_chat_member(ch, user_id)
        except TelegramError as e:
            log.warning("membership check failed for %s: %s", ch, e)
            return False
        ok = m.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        ) or (m.status == ChatMemberStatus.RESTRICTED and m.is_member)
        if not ok:
            return False
    cache[user_id] = time.time() + 120
    return True


async def alert(update, text):
    q = update.callback_query
    if q:
        await q.answer(text, show_alert=True)
    else:
        await update.effective_message.reply_text(text)


async def allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """ثبت کاربر + بررسی مسدودی، تعمیرات و عضویت در کانال‌ها."""
    user = update.effective_user
    if not user:
        return False
    db.upsert_user(user)
    if user.id in ADMIN_IDS:
        return True
    if db.is_banned(user.id):
        await alert(update, "⛔️ دسترسی شما به ربات محدود شده است.")
        return False
    if db.get_setting("maintenance") == "1":
        await alert(update, "🔧 ربات در حال بروزرسانیه؛ چند دقیقه دیگه برگرد 💙")
        return False
    if not await is_member(context, user.id):
        q = update.callback_query
        if q:
            await q.answer("🔒 اول باید عضو کانال‌ها بشی", show_alert=True)
        await update.effective_message.reply_text(
            ui.JOIN_TEXT, parse_mode=ParseMode.HTML, reply_markup=ui.join_keyboard()
        )
        return False
    return True


# ───────────────────────── صفحه اصلی ─────────────────────────
async def send_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    caption = ui.welcome(user.first_name or "دوست")
    markup = ui.main_menu(user.id in ADMIN_IDS)
    bot = context.bot

    fid = db.get_setting("banner_id")
    if fid:  # عکس قبلاً آپلود شده؛ فقط با file_id ارسال می‌شود (سریع)
        try:
            await bot.send_photo(
                chat_id, fid, caption=caption, parse_mode=ParseMode.HTML, reply_markup=markup
            )
            return
        except TelegramError:
            db.set_setting("banner_id", "")
    if BANNER.exists():
        with open(BANNER, "rb") as f:
            sent = await bot.send_photo(
                chat_id, f, caption=caption, parse_mode=ParseMode.HTML, reply_markup=markup
            )
        if sent.photo:
            db.set_setting("banner_id", sent.photo[-1].file_id)
        return
    await bot.send_message(chat_id, caption, parse_mode=ParseMode.HTML, reply_markup=markup)


# ───────────────────────── بخش‌ها ─────────────────────────
async def page_config(update, context):
    rows = db.random_alive("configs", 3)
    head = (
        "🔑 <b>کانفیگ‌های شما</b>\n"
        f"{LINE}\n"
        "👆 روی هر کانفیگ بزن تا کپی بشه، بعد داخل برنامه وارد کن.\n\n"
    )
    tail = (
        "\n\n⚠️ <i>این کانفیگ‌ها عمومی و رایگان‌اند؛ برای کارهای حساس (بانکی و...) استفاده نکن.</i>\n"
        f"{LINE}\n📢 {POST_CHANNEL}"
    )
    if rows:
        blocks = []
        for i, r in enumerate(rows, 1):
            link = feeds.rebrand(r["link"], f"{BRAND_REMARK} {i} | {POST_CHANNEL}")
            block = f"{KEYCAPS[i - 1]} <code>{html.escape(link)}</code>"
            if len(head) + len("\n\n".join(blocks + [block])) + len(tail) > 3900:
                break
            blocks.append(block)
        text = head + "\n\n".join(blocks) + tail
    else:
        text = "🔑 <b>کانفیگ</b>\n\n⏳ فعلاً کانفیگی آماده نیست؛ چند دقیقه دیگه امتحان کن."
    await show(
        update,
        text,
        with_home(
            [btn("🔄 کانفیگ‌های دیگر", "config", style=GREEN)],
            [btn("📲 آموزش و دانلود برنامه", "apps", style=BLUE)],
        ),
    )


async def page_proxy(update, context):
    rows = db.random_alive("proxies", 4)
    if rows:
        text = (
            "🛡 <b>پروکسی‌های شما</b>\n"
            f"{LINE}\n"
            "👇 روی دکمه‌ها بزن تا مستقیم وصل بشی\n"
            "💡 اگه یکی وصل نشد، بعدی رو امتحان کن\n\n"
            f"📢 {POST_CHANNEL}"
        )
        buttons = [
            [btn(f"🔗 اتصال به پروکسی {feeds.fa_digits(i)}", url=r["link"], style=BLUE)]
            for i, r in enumerate(rows, 1)
        ]
    else:
        text = "🛡 <b>پروکسی</b>\n\n⏳ فعلاً پروکسی‌ای آماده نیست؛ چند دقیقه دیگه امتحان کن."
        buttons = []
    buttons.append([btn("🔄 پروکسی‌های دیگر", "proxy", style=GREEN)])
    await show(update, text, with_home(*buttons))


async def page_account(update, context):
    user = update.effective_user
    row = db.get_user(user.id)
    joined = feeds.jalali_date(row["joined"]) if row else "—"
    notify = bool(row["notify"]) if row else True
    text = (
        "👤 <b>حساب من</b>\n"
        f"{LINE}\n"
        f"🙍‍♂️ نام: <b>{html.escape(user.full_name)}</b>\n"
        f"🆔 آیدی عددی: <code>{user.id}</code>\n"
        f"📅 تاریخ عضویت: <b>{joined}</b>\n"
        f"🔔 اعلان‌ها: {'روشن ✅' if notify else 'خاموش ❌'}\n"
        f"💎 وضعیت: <b>{'ادمین 👑' if user.id in ADMIN_IDS else 'عضو فعال'}</b>\n"
        f"{LINE}\n"
        f"₿ موجودی استخراج: <b>{mining.fmt_btc(mining.get(user.id)['sat'])}</b> BTC\n"
        f"👥 دعوت موفق: <b>{mining.get(user.id)['inv']}</b>"
    )
    await show(update, text, with_home())


async def page_settings(update, context):
    row = db.get_user(update.effective_user.id)
    notify = bool(row["notify"]) if row else True
    text = (
        "⚙️ <b>تنظیمات</b>\n"
        f"{LINE}\n"
        "🔔 <b>اعلان‌ها:</b> دریافت پیام‌های همگانی و خبرهای ویژه\n\n"
        f"وضعیت فعلی: {'روشن ✅' if notify else 'خاموش ❌'}"
    )
    toggle = btn(
        "🔕 خاموش کردن اعلان‌ها" if notify else "🔔 روشن کردن اعلان‌ها",
        "toggle_notify",
        style=ui.RED if notify else GREEN,
    )
    await show(update, text, with_home([toggle]))


async def page_support(update, context):
    text = (
        "🎧 <b>پشتیبانی</b>\n"
        f"{LINE}\n"
        "سؤال یا مشکلی داری؟ تیم ما همیشه کنارته 💙\n"
        "روی دکمه‌ی زیر بزن و پیامت رو بفرست."
    )
    await show(update, text, with_home(*ui.support_rows()))


async def page_bots(update, context):
    text = (
        "🤖 <b>ربات‌ها و کانال‌های ما</b>\n"
        f"{LINE}\n"
        "از لیست زیر انتخاب کن 👇"
    )
    await show(update, text, with_home(*ui.bots_rows()))


async def page_apps(update, context):
    await show(update, ui.APPS_TEXT, with_home(*ui.APPS_KB_ROWS))


async def page_help(update, context):
    await show(update, ui.HELP_TEXT, with_home())


async def page_mining(update, context):
    user = update.effective_user
    uid, bot_name = user.id, context.bot.username
    link = mining.ref_link(bot_name, uid)
    share = f"https://t.me/share/url?url={quote(link)}&text={quote('بیا با هم بیت‌کوین استخراج کنیم ⛏')}"
    await show(
        update,
        mining.info_text(uid, bot_name),
        with_home(
            [btn("⚡ استخراج سریع داخل ربات", "game", style=GREEN)],
            [btn("💸 برداشت", "wd", style=BLUE), btn("🏆 برترین‌ها", "top", style=BLUE)],
            [btn("📤 ارسال لینک دعوت به دوستان", url=share, style=GREEN)],
        ),
    )
    await send_kb(update, context, "⛏ برای باز کردن صفحه‌ی استخراج، دکمه‌ی «⛏ استخراج» پایین رو بزن 👇")


def game_kb(empty=False):
    rows = []
    if not empty:
        rows.append([btn("⛏ ضربه ⚡", "tap", style=GREEN)])
    rows.append([btn("💸 برداشت", "wd", style=BLUE), btn("📊 جزئیات و دعوت", "mining", style=BLUE)])
    return with_home(*rows)


async def page_game(update, context):
    uid = update.effective_user.id
    await show(update, mining.game_text(uid), game_kb(mining.left(mining.get(uid)) == 0))


async def do_tap(update, context):
    """یک ضربه داخل خود ربات. ضربه همیشه حساب می‌شود؛ ویرایش پیام کمی محدود است."""
    uid = update.callback_query.from_user.id
    if mining.left(mining.get(uid)) <= 0:
        return await show(update, mining.game_text(uid), game_kb(True))
    _, notify = await mining.handle_sync(uid, {"t": 1}, lambda u: is_member(context, u))
    if notify:
        inviter, note = notify
        try:
            await context.bot.send_message(inviter, note, parse_mode=ParseMode.HTML)
        except TelegramError:
            pass
    now = time.time()
    empty = mining.left(mining.get(uid)) == 0
    if not empty and now - context.user_data.get("tap_edit", 0) < 0.7:
        return  # تلگرام ویرایش خیلی سریع را محدود می‌کند؛ ضربه ثبت شده و در ویرایش بعدی دیده می‌شود
    context.user_data["tap_edit"] = now
    try:
        await show(update, mining.game_text(uid), game_kb(empty))
    except TelegramError:
        pass


async def page_wd(update, context):
    uid = update.effective_user.id
    m = mining.get(uid)
    mn = mining.fmt_btc(WD_MIN_SAT)
    back = with_home([btn("⛏ ادامه‌ی استخراج", "game", style=GREEN)])
    if db.wd_user_pending(uid):
        return await show(
            update,
            "💸 <b>برداشت</b>\n\n⏳ یک درخواست برداشت در حال بررسی داری؛ بعد از نتیجه‌اش می‌تونی درخواست جدید بدی.",
            back,
        )
    if m["sat"] < WD_MIN_SAT:
        return await show(
            update,
            "💸 <b>برداشت</b>\n"
            f"{LINE}\n"
            f"💰 موجودی: <b>{mining.fmt_btc(m['sat'])}</b> BTC\n"
            f"🎯 حداقل برداشت: <b>{mn}</b> BTC\n"
            f"📉 مونده تا حداقل: <b>{mining.fmt_btc(WD_MIN_SAT - m['sat'])}</b> BTC\n\n"
            "⛏ استخراج کن و دوستانت رو دعوت کن تا زودتر برسی!",
            back,
        )
    context.user_data["await"] = "wd_addr"
    await show(
        update,
        "💸 <b>درخواست برداشت</b>\n"
        f"{LINE}\n"
        f"💰 مبلغ: <b>{mining.fmt_btc(m['sat'])}</b> BTC\n\n"
        "✍️ <b>آدرس کیف پول بیت‌کوین (BTC)</b> خودت رو بفرست.\n"
        "⚠️ آدرس رو با دقت بفرست؛ پرداخت اشتباه قابل برگشت نیست.",
        kb_cancel_wd(),
    )


def kb_cancel_wd():
    return ui.kb([btn("❌ انصراف", "wd_cancel", style=ui.RED)])


async def submit_withdrawal(context, user, chat_id, addr):
    """ثبت درخواست برداشت (از چت یا از صفحه‌ی استخراج) و خبر دادن به ادمین‌ها."""
    wd_id, err = mining.request_withdrawal(user.id, addr)
    if wd_id is None:
        return await context.bot.send_message(chat_id, err)
    w = db.wd_get(wd_id)
    await context.bot.send_message(
        chat_id,
        "✅ <b>درخواست برداشت ثبت شد</b>\n"
        f"{LINE}\n"
        f"🧾 شماره: <b>#{wd_id}</b>\n"
        f"💰 مبلغ: <b>{mining.fmt_btc(w['sat'])}</b> BTC\n"
        f"👛 آدرس: <code>{html.escape(addr)}</code>\n\n"
        "⏳ بعد از بررسی ادمین واریز می‌شه و بهت خبر می‌دیم.",
        parse_mode=ParseMode.HTML,
        reply_markup=with_home(),
    )
    text = (
        f"💸 <b>درخواست برداشت جدید #{wd_id}</b>\n"
        f"👤 {html.escape(user.full_name)} — <code>{user.id}</code>\n"
        f"💰 <b>{mining.fmt_btc(w['sat'])}</b> BTC\n"
        f"👛 <code>{html.escape(addr)}</code>"
    )
    markup = ui.kb(
        [
            btn("✅ پرداخت شد", f"adm:wdok:{wd_id}", style=ui.GREEN),
            btn("❌ رد", f"adm:wdno:{wd_id}", style=ui.RED),
        ]
    )
    for a in ADMIN_IDS:
        try:
            await context.bot.send_message(a, text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except TelegramError:
            pass


async def handle_wd_address(update, context):
    msg = update.effective_message
    addr = (msg.text or "").strip()
    if not mining.valid_btc_address(addr):
        return await msg.reply_text(
            "❌ آدرس بیت‌کوین معتبر نیست؛ دوباره بفرست (آدرس‌هایی که با 1 ، 3 یا bc1 شروع می‌شن).",
            reply_markup=kb_cancel_wd(),
        )
    context.user_data.pop("await", None)
    await submit_withdrawal(context, update.effective_user, msg.chat_id, addr)


async def page_top(update, context):
    await show(update, mining.top_text(), with_home([btn("⛏ استخراج", "mining", style=GREEN)]))


PAGES = {
    "game": page_game,
    "wd": page_wd,
    "mining": page_mining,
    "top": page_top,
    "config": page_config,
    "proxy": page_proxy,
    "account": page_account,
    "settings": page_settings,
    "support": page_support,
    "bots": page_bots,
    "apps": page_apps,
    "help": page_help,
}


# ───────────────────────── کیبورد ثابت پایین ─────────────────────────
KB_LABELS = {
    "🔑 کانفیگ": "config",
    "🛡 پروکسی": "proxy",
    "👤 حساب من": "account",
    "⚙️ تنظیمات": "settings",
    "🎧 پشتیبانی": "support",
    "🤖 ربات‌های دیگمون": "bots",
    "📲 دانلود برنامه‌ها": "apps",
}
HOME_LABEL = "🏠 صفحه اصلی"
ADMIN_LABEL = "🛠 پنل مدیریت"


def kbtn(text, style=None, **kw):
    # رنگ دکمه‌ها (Bot API 9.4) از طریق api_kwargs؛ روی نسخه‌های قدیمی نادیده گرفته می‌شود
    return KeyboardButton(text, api_kwargs={"style": style} if style else None, **kw)


def bottom_kb(uid, name, bot_username):
    miner = kbtn(
        "⛏ استخراج",
        "success",
        web_app=WebAppInfo(url=mining.miner_url(uid, bot_username, name)),
    )
    rows = [
        [kbtn(HOME_LABEL, "primary"), miner],
        [kbtn("🔑 کانفیگ", "success"), kbtn("🛡 پروکسی", "primary")],
        [kbtn("👤 حساب من", "primary"), kbtn("⚙️ تنظیمات", "primary"), kbtn("🎧 پشتیبانی", "success")],
        [kbtn("🤖 ربات‌های دیگمون", "primary"), kbtn("📲 دانلود برنامه‌ها", "success")],
    ]
    if uid in ADMIN_IDS:
        rows.append([kbtn(ADMIN_LABEL, "danger")])
    return ReplyKeyboardMarkup(
        rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="یکی از بخش‌ها رو انتخاب کن…",
    )


async def send_kb(update: Update, context: ContextTypes.DEFAULT_TYPE, text="👇 از دکمه‌های پایین هم می‌تونی استفاده کنی."):
    user = update.effective_user
    await context.bot.send_message(
        update.effective_chat.id,
        text,
        reply_markup=bottom_kb(user.id, user.first_name or "", context.bot.username),
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه‌های کیبورد ثابت پایین (متن ساده می‌فرستند)."""
    t = (update.effective_message.text or "").strip()
    is_label = t in (HOME_LABEL, ADMIN_LABEL) or t in KB_LABELS
    if context.user_data.get("await") == "wd_addr":
        if not is_label:
            if await allowed(update, context):
                await handle_wd_address(update, context)
            return
        context.user_data.pop("await", None)  # کاربر یکی از دکمه‌های پایین را زد؛ انصراف
    elif context.user_data.get("await"):  # ادمین وسط یک عملیات است
        return
    if not is_label:
        return
    if not await allowed(update, context):
        return
    if t == HOME_LABEL:
        return await send_home(update, context)
    if t == ADMIN_LABEL:
        return await admin.cmd_admin(update, context)
    await PAGES[KB_LABELS[t]](update, context)


async def on_webapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """داده‌ای که صفحه‌ی استخراج می‌فرستد: ثبت ضربه‌ها (sync) یا درخواست برداشت (wd)."""
    if not await allowed(update, context):
        return
    msg = update.effective_message
    try:
        data = json.loads(msg.web_app_data.data)
    except Exception:
        return
    user = update.effective_user
    bot_name = context.bot.username
    kb_now = lambda uid: bottom_kb(uid, user.first_name or "", bot_name)

    if data.get("a") == "sync":
        text, notify = await mining.handle_sync(user.id, data, lambda u: is_member(context, u))
        await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb_now(user.id))
        if notify:
            inviter, note = notify
            try:
                await context.bot.send_message(
                    inviter, note, parse_mode=ParseMode.HTML, reply_markup=bottom_kb(inviter, "", bot_name)
                )
            except TelegramError:
                pass
    elif data.get("a") == "wd":
        addr = str(data.get("ad", "")).strip()
        if not mining.valid_btc_address(addr):
            return await msg.reply_text("❌ آدرس بیت‌کوین معتبر نیست؛ دوباره از تب «کیف پول» امتحان کن.")
        await submit_withdrawal(context, user, msg.chat_id, addr)
        await send_kb(update, context, "👇 دکمه‌ی استخراج به‌روز شد.")


# ───────────────────────── هندلرها ─────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    arg = context.args[0] if context.args else ""
    # دعوت: فقط برای کاربر کاملاً تازه ثبت می‌شود
    if arg.startswith("ref_") and arg[4:].isdigit() and user and db.get_user(user.id) is None:
        mining.set_ref(user.id, int(arg[4:]))
    if not await allowed(update, context):
        return
    if arg == "apps":
        return await page_apps(update, context)
    await send_home(update, context)
    await send_kb(update, context)


def command_page(key):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await allowed(update, context):
            return
        if key == "home":
            return await send_home(update, context)
        await PAGES[key](update, context)

    return handler


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data

    if data == "check_join":
        db.upsert_user(q.from_user)
        context.application.bot_data.setdefault("member_cache", {}).pop(q.from_user.id, None)
        if await is_member(context, q.from_user.id):
            await q.answer("✅ عضویتت تأیید شد!")
            try:
                await q.message.delete()
            except TelegramError:
                pass
            await send_home(update, context)
            await send_kb(update, context)
        else:
            await q.answer("❌ هنوز عضو هر دو کانال نشدی!", show_alert=True)
        return

    if not await allowed(update, context):
        return
    await q.answer()

    if data == "home":
        try:
            await q.message.delete()
        except TelegramError:
            pass
        return await send_home(update, context)

    if data == "tap":
        return await do_tap(update, context)

    if data == "wd_cancel":
        context.user_data.pop("await", None)
        return await page_mining(update, context)

    if data == "toggle_notify":
        db.toggle_notify(q.from_user.id)
        return await page_settings(update, context)

    if data in PAGES:
        await PAGES[data](update, context)


async def on_error(update, context):
    log.error("handler error", exc_info=context.error)


# ───────────────────────── راه‌اندازی ─────────────────────────
USER_COMMANDS = [
    BotCommand("start", "♻️ شروع دوباره"),
    BotCommand("menu", "🏠 صفحه اصلی"),
    BotCommand("config", "🔑 دریافت کانفیگ"),
    BotCommand("proxy", "🛡 دریافت پروکسی"),
    BotCommand("account", "👤 حساب من"),
    BotCommand("settings", "⚙️ تنظیمات"),
    BotCommand("support", "🎧 پشتیبانی"),
    BotCommand("bots", "🤖 ربات‌های دیگر ما"),
    BotCommand("apps", "📲 دانلود برنامه‌ها"),
    BotCommand("mining", "₿ استخراج بیت‌کوین"),
    BotCommand("help", "📖 راهنما"),
]


async def post_init(app: Application):
    # ۱) دیتابیس را از بکاپ برگردان (چون Actions هر بار از صفر شروع می‌کند)
    restored = await backup.restore_latest(app.bot)
    db.init()

    # ۲) منوی دستورات (پایین سمت چپ)
    await app.bot.set_my_commands(USER_COMMANDS)
    for uid in ADMIN_IDS:
        try:
            await app.bot.set_my_commands(
                USER_COMMANDS + [BotCommand("admin", "🛠 پنل مدیریت")],
                scope=BotCommandScopeChat(uid),
            )
        except TelegramError as e:
            log.warning("admin commands for %s: %s", uid, e)

    # ۳) کارهای زمان‌بندی‌شده
    jq = app.job_queue
    jq.run_repeating(jobs.refresh_job, interval=REFRESH_EVERY, first=15)
    jq.run_repeating(jobs.autopost_tick, interval=300, first=90)
    jq.run_repeating(jobs.backup_job, interval=BACKUP_EVERY, first=180)

    s = db.stats()
    await jobs.notify_admins(
        app.bot,
        "🟢 <b>ربات روشن شد</b>\n"
        f"💾 بازیابی دیتابیس: {'انجام شد ✅' if restored else 'بکاپی پیدا نشد (شروع از صفر)'}\n"
        f"👥 کاربران: {s['total']}",
    )
    ok, info = await jobs.check_miner_page()
    if not ok:
        await jobs.notify_admins(app.bot, "⚠️ <b>صفحه‌ی استخراج در دسترس نیست</b>\n" + html.escape(info))
    log.info("KING PROXY bot is running...")


async def post_stop(app: Application):
    # قبل از خاموش شدن یک بکاپ نهایی بگیر
    await backup.backup_now(app.bot, force=True)


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )

    # پنل مدیریت (قبل از هندلرهای عمومی)
    app.add_handler(CommandHandler("admin", admin.cmd_admin))
    app.add_handler(CallbackQueryHandler(admin.on_admin_button, pattern=r"^adm:"))
    app.add_handler(
        MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, admin.on_admin_document)
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & ~filters.COMMAND & ~filters.Document.ALL,
            admin.on_admin_message,
        ),
        group=1,  # گروه جدا، تا با کیبورد پایین (on_text) تداخل نکند
    )
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, on_text))

    # کاربران
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", command_page("home")))
    for key in PAGES:
        app.add_handler(CommandHandler(key, command_page(key)))
    app.add_handler(CallbackQueryHandler(on_button, pattern=r"^(?!adm:)"))
    app.add_error_handler(on_error)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
