import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

from config import LOCK_CHANNELS, OTHER_BOT, POST_CHANNEL, SUPPORT_USERNAME

LINE = "━━━━━━━━━━━━━━━━━━"
KEYCAPS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

# رنگ دکمه‌ها (Bot API 9.4): primary=آبی ، success=سبز ، danger=قرمز
BLUE, GREEN, RED = "primary", "success", "danger"


def btn(text, cb=None, url=None, style=None):
    kw = {"style": style} if style else {}
    return InlineKeyboardButton(text, callback_data=cb, url=url, **kw)


def kb(*rows):
    return InlineKeyboardMarkup([list(r) for r in rows])


def home_row():
    return [btn("🏠 صفحه اصلی", "home", style=BLUE)]


def with_home(*rows):
    return kb(*rows, home_row())


# ───────────────────────── منو‌ها ─────────────────────────
def main_menu(is_admin=False):
    rows = [
        [btn("🔑 کانفیگ", "config", style=GREEN), btn("🛡 پروکسی", "proxy", style=BLUE)],
        [
            btn("👤 حساب من", "account", style=BLUE),
            btn("⚙️ تنظیمات", "settings", style=BLUE),
            btn("🎧 پشتیبانی", "support", style=GREEN),
        ],
        [
            btn("🤖 ربات‌های دیگمون", "bots", style=BLUE),
            btn("📲 دانلود برنامه‌ها", "apps", style=GREEN),
        ],
        [btn("₿ استخراج بیت‌کوین", "mining", style=BLUE)],
    ]
    if is_admin:
        rows.append([btn("🛠 پنل مدیریت", "adm:panel", style=RED)])
    return kb(*rows)


def join_keyboard():
    rows = [
        [btn(f"📢 عضویت در {ch}", url=f"https://t.me/{ch[1:]}", style=BLUE)]
        for ch in LOCK_CHANNELS
    ]
    rows.append([btn("✅ عضو شدم", "check_join", style=GREEN)])
    return kb(*rows)


# ───────────────────────── متن‌ها ─────────────────────────
def welcome(name):
    return (
        "👑 <b>KING PROXY</b> | <i>همیشه یک قدم جلوتر</i>\n\n"
        f"سلام <b>{html.escape(name)}</b> عزیز 👋\n"
        "به خانواده‌ی کینگ پروکسی خوش اومدی!\n\n"
        f"{LINE}\n"
        "✨ <b>خدمات ما</b>\n"
        "🔑 کانفیگ‌های روزانه و به‌روز\n"
        "🛡 پروکسی‌های سریع و پایدار\n"
        "📲 آموزش اتصال و دانلود برنامه‌ها\n"
        "🎧 پشتیبانی همیشگی\n"
        f"{LINE}\n"
        "👇 یکی از گزینه‌های زیر رو انتخاب کن"
    )


JOIN_TEXT = (
    "🔒 <b>برای استفاده از ربات، اول باید عضو کانال‌های ما بشی</b>\n\n"
    "1️⃣ روی دکمه‌های زیر بزن و عضو شو\n"
    "2️⃣ بعد دکمه «✅ عضو شدم» رو بزن\n\n"
    "💙 ممنون از همراهیت"
)

HELP_TEXT = (
    "📖 <b>راهنمای ربات</b>\n"
    f"{LINE}\n"
    "♻️ /start — شروع دوباره\n"
    "🏠 /menu — صفحه اصلی\n"
    "🔑 /config — دریافت کانفیگ\n"
    "🛡 /proxy — دریافت پروکسی\n"
    "👤 /account — حساب من\n"
    "⚙️ /settings — تنظیمات\n"
    "🎧 /support — پشتیبانی\n"
    "🤖 /bots — ربات‌های دیگر ما\n"
    "📲 /apps — دانلود برنامه‌ها\n"
    "₿ /mining — استخراج بیت‌کوین\n"
    "📖 /help — همین راهنما\n"
    f"{LINE}\n"
    f"📢 {POST_CHANNEL}"
)

APPS_TEXT = (
    "📲 <b>دانلود برنامه‌ها</b>\n"
    f"{LINE}\n"
    "برای استفاده از کانفیگ‌ها یکی از برنامه‌های زیر رو نصب کن:\n\n"
    "🤖 <b>V2rayNG</b> — اندروید\n"
    "🚀 <b>NPV Tunnel</b> — اندروید و آیفون\n"
    "🍏 <b>V2Box</b> — آیفون و مک\n\n"
    "📌 <b>طرز اتصال:</b>\n"
    "1️⃣ کانفیگ رو از ربات یا کانال کپی کن\n"
    "2️⃣ برنامه رو باز کن و گزینه‌ی ➕ رو بزن\n"
    "3️⃣ «Import from clipboard» رو انتخاب کن\n"
    "4️⃣ روی دکمه‌ی اتصال بزن ✅"
)

APPS_KB_ROWS = [
    [
        btn(
            "🤖 V2rayNG",
            url="https://play.google.com/store/apps/details?id=com.v2ray.ang",
            style=GREEN,
        )
    ],
    [
        btn(
            "🚀 NPV Tunnel",
            url="https://play.google.com/store/search?q=NPV%20Tunnel&c=apps",
            style=BLUE,
        ),
        btn(
            "🍏 V2Box",
            url="https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690",
            style=BLUE,
        ),
    ],
]


def support_rows():
    return [
        [btn("💬 ارتباط با پشتیبانی", url=f"https://t.me/{SUPPORT_USERNAME}", style=GREEN)]
    ]


def bots_rows():
    return [
        [btn(f"🤖 @{OTHER_BOT}", url=f"https://t.me/{OTHER_BOT}", style=GREEN)],
        [
            btn("📢 کینگ پروکسی", url=f"https://t.me/{POST_CHANNEL[1:]}", style=BLUE),
            btn("🌐 دنیای من", url="https://t.me/donyayeman0122", style=BLUE),
        ],
    ]


# ───────────────────────── ارسال/ویرایش ─────────────────────────
async def show(update, text, markup):
    """از دکمه آمده → همان پیام ویرایش می‌شود (یا اگر عکس بود، پیام متنی جدید)."""
    q = update.callback_query
    msg = update.effective_message
    if q and msg:
        if msg.photo:
            try:
                await msg.delete()
            except Exception:
                pass
            await msg.chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            try:
                await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
            except BadRequest as e:
                if "not modified" not in str(e).lower():
                    raise
    else:
        await msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
