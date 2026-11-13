"""
متن‌های متنوع برای پست‌های روزانه‌ی کانال.
هر بخش (تیتر، توضیح، نکته، پایان...) از بین چند گزینه انتخاب می‌شود و گزینه‌ی دیروز تکرار نمی‌شود.
"""
import random
from datetime import datetime

import db
import feeds
from config import POST_CHANNEL

DIVIDERS = [
    "━━━━━━━━━━━━━━━━━━",
    "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬",
    "✦ ━━━━━━━━━━━━ ✦",
    "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈",
    "◈━━━━━━━━━━━━━━━◈",
    "•⎯⎯⎯⎯⎯⎯⎯⚡️⎯⎯⎯⎯⎯⎯⎯•",
]

HEADERS = [
    "👑 <b>KING PROXY</b> 👑",
    "⚡️ <b>KING PROXY</b> ⚡️",
    "💎 <b>KING PROXY</b> 💎",
    "🚀 <b>KING PROXY</b> 🚀",
    "🛡 <b>KING PROXY</b> | <i>همیشه یک قدم جلوتر</i>",
    "🔥 <b>KING PROXY</b> 🔥",
]

GREETINGS = {
    "morning": ["☀️ صبحتون بخیر", "🌅 صبح قشنگتون بخیر", "☕️ صبح بخیر؛ روزتون پر از اینترنت آزاد"],
    "noon": ["🌤 ظهر بخیر", "🍽 ظهرتون بخیر", "☀️ روز بخیر دوستان"],
    "evening": ["🌇 عصر بخیر", "🌆 عصرتون بخیر دوستان", "🍃 عصر بخیر؛ وقتشه وصل بشید"],
    "night": ["🌙 شبتون بخیر", "✨ شب بخیر دوستان", "🌃 شب‌زنده‌دارها سلام"],
}

PROXY_TITLES = [
    "🛡 پروکسی‌های جدید و پرسرعت",
    "⚡️ پروکسی‌های تازه‌ی امروز",
    "🔥 لیست داغ پروکسی‌ها",
    "🚀 پروکسی‌های پرسرعت و پایدار",
    "💎 پروکسی‌های ویژه‌ی کینگ",
    "🌐 پروکسی‌های آماده‌ی اتصال",
]
PROXY_BODY = [
    "👇 روی دکمه‌ها بزن تا مستقیم وصل بشی",
    "📲 فقط یه ضربه تا اتصال؛ دکمه‌ها رو امتحان کن",
    "🔗 هر دکمه یه پروکسی جداست؛ هرکدوم بهتر بود بمون",
    "⚡️ دکمه‌ی پروکسی رو بزن و «Connect» رو انتخاب کن",
]
CONFIG_TITLES = [
    "🔑 کانفیگ‌های جدید امروز",
    "⚡️ کانفیگ‌های تازه‌ی V2rayNG",
    "🔥 کانفیگ‌های داغ و به‌روز",
    "🚀 کانفیگ‌های پرسرعت امروز",
    "💎 کانفیگ‌های ویژه‌ی کینگ",
    "🌐 کانفیگ‌های آماده‌ی استفاده",
]
CONFIG_BODY = [
    "👆 روی هر کانفیگ بزن تا کپی بشه",
    "📋 لمس کن تا کپی بشه، بعد داخل برنامه Import کن",
    "📲 کپی کن و از داخل برنامه «Import from clipboard» رو بزن",
    "⚡️ یه ضربه روی کانفیگ = کپی؛ بقیه‌ش با برنامه",
]
CONFIG_APPS = [
    "📲 مناسب: <b>V2rayNG • NPV Tunnel • V2Box</b>",
    "📲 برنامه‌ها: <b>V2rayNG | V2Box | Hiddify</b>",
    "📲 اندروید و آیفون: <b>V2rayNG • V2Box</b>",
]
TIPS = [
    "💡 <i>اگه یکی وصل نشد، بعدی رو امتحان کن</i>",
    "💡 <i>سرعت بعضی‌ها بسته به اینترنتت فرق می‌کنه؛ چند‌تا رو تست کن</i>",
    "💡 <i>اینترنت همراه و ثابت ممکنه جواب‌های متفاوتی بدن</i>",
    "💡 <i>اگه کند بود، یه کانفیگ یا پروکسی دیگه رو امتحان کن</i>",
]
OUTROS = [
    "🔁 برای دوستات هم بفرست ❤️",
    "❤️ اگه کمکت کرد، به بقیه هم معرفی کن",
    "🤝 با فوروارد کردن، به بقیه هم کمک کن",
    "💙 حمایتتون انگیزه‌ی ماست؛ فوروارد یادتون نره",
    "🙏 ممنون که همراه کینگ پروکسی هستید",
]
PROMOS = [
    "⛏ توی ربات هر روز بیت‌کوین استخراج کن و دوستات رو دعوت کن 🎁",
    "₿ استخراج بیت‌کوین و برداشت مستقیم؛ همین الان توی ربات شروع کن",
    "",
    "",
]


def pick(key, options):
    """یک گزینه‌ی تصادفی؛ همان گزینه‌ی دفعه‌ی قبل تکرار نمی‌شود."""
    if len(options) == 1:
        return options[0]
    last = db.get_setting(f"tpl_{key}", "-1")
    choices = [i for i in range(len(options)) if str(i) != last]
    i = random.choice(choices)
    db.set_setting(f"tpl_{key}", i)
    return options[i]


def greeting():
    h = datetime.now(db.TZ).hour
    part = "morning" if 5 <= h < 12 else "noon" if 12 <= h < 16 else "evening" if 16 <= h < 20 else "night"
    return pick(f"greet_{part}", GREETINGS[part])


def _head(kind, title_opts):
    div = pick(f"div_{kind}", DIVIDERS)
    top = pick(f"head_{kind}", HEADERS)
    title = pick(f"title_{kind}", title_opts)
    text = (
        f"{top}\n{div}\n{greeting()}\n\n"
        f"<b>{title}</b>\n📅 {feeds.jalali_str()}\n{div}\n\n"
    )
    return text, div


def footer(bot_username, div):
    promo = pick("promo", PROMOS)
    parts = [div, f"📢 <b>{POST_CHANNEL}</b>", f"🤖 @{bot_username}"]
    if promo:
        parts.insert(1, promo)
    return "\n".join(parts)


# ───────────────────────── پست پروکسی ─────────────────────────
def proxy_post(n, bot_username):
    head, div = _head("proxy", PROXY_TITLES)
    return (
        head
        + f"⚡️ <b>{feeds.fa_digits(n)}</b> پروکسی تازه و بررسی‌شده\n"
        + pick("body_proxy", PROXY_BODY)
        + "\n\n"
        + pick("tip", TIPS)
        + "\n"
        + pick("outro", OUTROS)
        + "\n\n"
        + footer(bot_username, div)
    )


def proxy_button_label(i):
    style = pick("pbtn", ["🔗 پروکسی {n}", "⚡️ اتصال {n}", "🛡 پروکسی {n}", "🚀 سرور {n}"])
    return style.format(n=feeds.fa_digits(i))


# ───────────────────────── پست کانفیگ ─────────────────────────
def config_parts(bot_username):
    """(head, tail) برای پست کانفیگ؛ بین این دو، خود کانفیگ‌ها قرار می‌گیرند."""
    head, div = _head("config", CONFIG_TITLES)
    head += pick("apps_cfg", CONFIG_APPS) + "\n" + pick("body_cfg", CONFIG_BODY) + "\n\n"
    tail = (
        "\n\n"
        + pick("tip", TIPS)
        + "\n"
        + pick("outro", OUTROS)
        + "\n\n"
        + footer(bot_username, div)
    )
    return head, tail
