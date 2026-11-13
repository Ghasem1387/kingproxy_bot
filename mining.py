"""
استخراج بیت‌کوین داخل ربات (ضربه، باتری روزانه، دعوت) + درخواست برداشت.
تمام محاسبات با ساتوشی (عدد صحیح) انجام می‌شود تا خطای اعشار نداشته باشیم.
"""
import hashlib
import html
import json
import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import db
from config import (
    DAILY_BATTERY,
    LOCK_CHANNELS,
    MINER_URL,
    OTHER_BOT,
    REF_SAT,
    REF_TAPS,
    SAT,
    SUPPORT_USERNAME,
    TAP_SAT,
    WD_MIN_SAT,
)

log = logging.getLogger("kingproxy.mining")

LINE = "━━━━━━━━━━━━━━━━━━"
WD_NOTE = (
    "💸 <i>برداشت: وقتی موجودیت به حداقل رسید، آدرس کیف پول بیت‌کوین رو بفرست؛ "
    "بعد از بررسی، مبلغ واریز می‌شه.</i>"
)


def today():
    # روز استخراج بر اساس UTC است
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def fmt_btc(sat):
    """۱۰ ساتوشی → 0.0000001 ؛ ۵۰۰ → 0.000005 (حداقل ۶ رقم اعشار، حداکثر ۸)"""
    whole, dec = f"{sat / SAT:.8f}".split(".")
    dec = dec.rstrip("0").ljust(6, "0")
    return f"{whole}.{dec}"


def meter(v, m, n=10):
    k = round(n * min(max(v, 0), m) / m)
    return "▰" * k + "▱" * (n - k)


def get(uid):
    """رکورد استخراج کاربر (در صورت نبود ساخته می‌شود) + بازنشانی باتری روز جدید."""
    m = db.miner_get(uid)
    t = today()
    if m["day"] != t:
        m["day"], m["taps"] = t, 0
        db.miner_set(uid, day=t, taps=0)
    return m


def left(m):
    return max(0, DAILY_BATTERY - m["taps"])


def ref_link(bot_username, uid):
    return f"https://t.me/{bot_username}?start=ref_{uid}"


def set_ref(uid, inviter):
    """اگر کاربر تازه است و دعوت‌کننده معتبر، ثبت می‌کند. (فقط یک‌بار)"""
    if uid == inviter or db.miner_get(uid, create=False):
        return False
    if not db.miner_get(inviter, create=False):
        return False
    db.miner_get(uid)  # ساخت رکورد کاربر جدید
    db.miner_set(uid, ref=inviter)
    return True


def miner_url(uid, bot_username, name=""):
    """آدرس مینی‌اپ + وضعیت کاربر (موجودی، باتری، دعوت‌ها...) به‌صورت پارامتر."""
    m = get(uid)
    q = urlencode(
        {
            "b": m["sat"],
            "l": left(m),
            "i": m["inv"],
            "rs": m["ref_sat"],
            "bot": bot_username,
            "id": uid,
            "s": m["syncs"],
            "d": m["day"],
            "n": (name or "")[:30],
            "m": DAILY_BATTERY,
            "r": REF_SAT,
            "k": TAP_SAT,
            "w": WD_MIN_SAT,
            "sup": SUPPORT_USERNAME,
            "ch": ",".join(c.lstrip("@") for c in LOCK_CHANNELS),
            "ob": json.dumps(
                [{"t": "🌐 دنیای من", "u": OTHER_BOT, "d": "ربات دیگه‌ی ما"}],
                ensure_ascii=False,
            ),
        }
    )
    return f"{MINER_URL}?{q}"


# ───────────────────────── متن‌ها ─────────────────────────
def info_text(uid, bot_username):
    m = get(uid)
    lf = left(m)
    return (
        "⛏ <b>استخراج بیت‌کوین</b>\n"
        f"{LINE}\n"
        f"💰 موجودی: <b>{fmt_btc(m['sat'])}</b> BTC\n"
        f"🔋 باتری امروز: <b>{lf}</b> از {DAILY_BATTERY}\n{meter(lf, DAILY_BATTERY)}\n\n"
        f"👥 دعوت موفق: <b>{m['inv']}</b>  •  🎁 پاداش دعوت: <b>{fmt_btc(m['ref_sat'])}</b> BTC\n"
        f"{LINE}\n"
        "📌 <b>طرز کار</b>\n"
        f"• هر ضربه = <b>{fmt_btc(TAP_SAT)}</b> BTC (روزی {DAILY_BATTERY} ضربه)\n"
        f"• هر دعوت فعال = <b>{fmt_btc(REF_SAT)}</b> BTC\n"
        f"• دعوت وقتی فعال می‌شه که دوستت عضو کانال‌ها بشه و {REF_TAPS} ضربه بزنه\n"
        f"• حداقل برداشت: <b>{fmt_btc(WD_MIN_SAT)}</b> BTC\n\n"
        "👇 برای باز کردن صفحه‌ی استخراج، دکمه‌ی «⛏ استخراج» پایین صفحه رو بزن.\n\n"
        "🔗 لینک دعوت تو:\n"
        f"<code>{ref_link(bot_username, uid)}</code>\n\n"
        f"{WD_NOTE}"
    )


def game_text(uid, flash=""):
    m = get(uid)
    lf = left(m)
    status = (
        "🔋 باتری تموم شد؛ فردا دوباره پر می‌شه ⏳"
        if lf == 0
        else "👇 روی «⛏ ضربه» بزن"
    )
    return (
        "⛏ <b>استخراج بیت‌کوین</b>\n"
        f"{LINE}\n"
        f"💰 موجودی: <b>{fmt_btc(m['sat'])}</b> BTC\n"
        f"🔋 باتری: <b>{lf}</b> از {DAILY_BATTERY}\n{meter(lf, DAILY_BATTERY)}\n\n"
        f"{flash}هر ضربه = <b>{fmt_btc(TAP_SAT)}</b> BTC\n{status}"
    )


def top_text():
    rows = db.miner_top(10)
    if not rows:
        return "🏆 <b>برترین استخراج‌کننده‌ها</b>\n\nهنوز کسی شروع نکرده؛ اولین نفر باش! ⛏"
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines = []
    for i, r in enumerate(rows):
        name = html.escape((r["name"] or "کاربر")[:18])
        lines.append(f"{medals[i]} <b>{name}</b> — {fmt_btc(r['sat'])} BTC  (👥 {r['inv']})")
    return f"🏆 <b>برترین استخراج‌کننده‌ها</b>\n{LINE}\n" + "\n".join(lines)


# ───────────────────────── ثبت ضربه‌ها ─────────────────────────
async def handle_sync(uid, data, joined):
    """
    data = {"t": تعداد ضربه, "s": شمارنده‌ی ثبت‌های قبلی کاربر (فقط مینی‌اپ می‌فرستد؛ ضد ثبت تکراری)}
    joined: async fn(uid) → True اگر کاربر عضو کانال‌هاست.
    خروجی: (متن پاسخ، اعلان برای دعوت‌کننده یا None)
    """
    m = get(uid)
    try:
        t = int(data.get("t", 0))
        seen = int(data["s"]) if data.get("s") is not None else None
    except (TypeError, ValueError):
        t, seen = 0, None
    if seen is not None and seen < m["syncs"]:
        return (
            "ℹ️ <b>این ضربه‌ها قبلاً ثبت شده بود</b>\n"
            f"💰 موجودی: <b>{fmt_btc(m['sat'])}</b> BTC"
        ), None

    t = max(0, min(t, DAILY_BATTERY - m["taps"]))  # سقف روزانه سمت ربات اعمال می‌شود
    m["taps"] += t
    m["tot"] += t
    m["sat"] += t * TAP_SAT

    notify = None
    inviter = m["ref"]
    if inviter and not m["paid"] and m["tot"] >= REF_TAPS and await joined(uid):
        r = db.miner_get(inviter, create=False)
        if r:
            m["paid"] = 1
            r["sat"] += REF_SAT
            r["inv"] += 1
            r["ref_sat"] += REF_SAT
            db.miner_set(inviter, sat=r["sat"], inv=r["inv"], ref_sat=r["ref_sat"])
            notify = (
                inviter,
                "🎉 <b>یکی از دعوت‌هات فعال شد!</b>\n"
                f"➕ <b>{fmt_btc(REF_SAT)}</b> BTC به موجودیت اضافه شد\n"
                f"💰 موجودی: <b>{fmt_btc(r['sat'])}</b> BTC\n"
                f"👥 دعوت موفق: <b>{r['inv']}</b>",
            )

    syncs = m["syncs"] + (1 if seen is not None else 0)
    db.miner_set(uid, sat=m["sat"], taps=m["taps"], tot=m["tot"], day=m["day"], paid=m["paid"], syncs=syncs)
    lf = left(m)
    return (
        "⛏ <b>پاداش ثبت شد</b>\n"
        f"{LINE}\n"
        f"➕ {t} ضربه = <b>+{fmt_btc(t * TAP_SAT)}</b> BTC\n"
        f"💰 موجودی: <b>{fmt_btc(m['sat'])}</b> BTC\n\n"
        f"🔋 باتری امروز: <b>{lf}</b> از {DAILY_BATTERY}\n{meter(lf, DAILY_BATTERY)}"
    ), notify


# ───────────────────────── آدرس بیت‌کوین ─────────────────────────
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _base58check(addr):
    n = 0
    for ch in addr:
        i = _B58.find(ch)
        if i < 0:
            return False
        n = n * 58 + i
    try:
        raw = n.to_bytes(25, "big")
    except OverflowError:
        return False
    if raw[0] not in (0x00, 0x05):  # P2PKH (1...) و P2SH (3...)
        return False
    return hashlib.sha256(hashlib.sha256(raw[:21]).digest()).digest()[:4] == raw[21:]


def _polymod(values):
    gen = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= gen[i]
    return chk


def _bech32(addr):
    if addr != addr.lower() and addr != addr.upper():
        return False
    a = addr.lower()
    if not a.startswith("bc1") or not 14 <= len(a) <= 90:
        return False
    data = [_B32.find(c) for c in a[3:]]
    if -1 in data or len(data) < 7:
        return False
    hrp_exp = [ord(c) >> 5 for c in "bc"] + [0] + [ord(c) & 31 for c in "bc"]
    const = _polymod(hrp_exp + data)
    witver = data[0]
    return (witver == 0 and const == 1) or (1 <= witver <= 16 and const == 0x2BC830A3)


def valid_btc_address(addr):
    addr = addr.strip()
    if addr[:1] in ("1", "3") and 26 <= len(addr) <= 35:
        return _base58check(addr)
    return _bech32(addr)


# ───────────────────────── برداشت ─────────────────────────
def request_withdrawal(uid, address):
    """موجودی را (تا تصمیم ادمین) نگه می‌دارد و درخواست می‌سازد. (id یا None، پیام خطا)"""
    m = get(uid)
    if db.wd_user_pending(uid):
        return None, "⏳ یک درخواست برداشت در حال بررسی داری؛ تا نتیجه‌اش مشخص نشده درخواست جدید نده."
    if m["sat"] < WD_MIN_SAT:
        return None, f"❌ حداقل برداشت {fmt_btc(WD_MIN_SAT)} BTC است."
    sat = m["sat"]
    db.miner_set(uid, sat=0)  # موجودی تا زمان تصمیم‌گیری کسر می‌شود (در صورت رد، برمی‌گردد)
    return db.wd_create(uid, sat, address.strip()), ""


def decide_withdrawal(wd_id, approve):
    """ادمین تأیید/رد می‌کند. رکورد را برمی‌گرداند (یا None اگر قبلاً تصمیم گرفته شده)."""
    w = db.wd_get(wd_id)
    if not w or w["status"] != "pending":
        return None
    if approve:
        db.wd_set_status(wd_id, "paid")
    else:
        m = db.miner_get(w["user_id"])
        db.miner_set(w["user_id"], sat=m["sat"] + w["sat"])  # برگشت موجودی
        db.wd_set_status(wd_id, "rejected")
    return db.wd_get(wd_id)
