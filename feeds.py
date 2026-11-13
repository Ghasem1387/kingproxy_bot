"""دریافت کانفیگ و پروکسی از کانال‌های عمومی (صفحه‌ی t.me/s/...)، بررسی و برندسازی."""
import asyncio
import base64
import html
import json
import logging
import re
from datetime import datetime
from urllib.parse import quote, urlparse

from db import TZ

log = logging.getLogger("kingproxy.feeds")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_URL_CHARS = r"[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+"
CONFIG_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:vless|vmess|trojan|ss|socks|hysteria2|hy2|tuic)://" + _URL_CHARS
)
PROXY_RE = re.compile(r"(?:https?://t\.me/proxy|tg://proxy)\?" + _URL_CHARS, re.I)
POST_ID_RE = re.compile(r'data-post="[^"/]+/(\d+)"')

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(x):
    return str(x).translate(FA_DIGITS)


# ───────────────────────── تاریخ شمسی ─────────────────────────
WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]
MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


def jalali_str(dt=None):
    """مثال: «دوشنبه ۱۱ آبان ۱۴۰۵»"""
    dt = dt or datetime.now(TZ)
    try:
        import jdatetime

        j = jdatetime.datetime.fromgregorian(datetime=dt)
        return fa_digits(f"{WEEKDAYS[j.weekday()]} {j.day} {MONTHS[j.month - 1]} {j.year}")
    except Exception:
        return fa_digits(dt.strftime("%Y/%m/%d"))


def jalali_date(date_str):
    """'2026-11-02' → '۱۴۰۵/۰۸/۱۱'"""
    try:
        import jdatetime

        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return fa_digits(jdatetime.date.fromgregorian(date=d).strftime("%Y/%m/%d"))
    except Exception:
        return fa_digits(date_str)


# ───────────────────────── پارس ─────────────────────────
def decode_vmess(link):
    body = link[len("vmess://"):].split("#")[0]
    body += "=" * (-len(body) % 4)
    try:
        raw = base64.b64decode(body.replace("-", "+").replace("_", "/"))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def norm_config(raw):
    link = raw.rstrip(".,;)")
    scheme, _, rest = link.partition("://")
    if len(rest) < 8:
        return None
    if scheme.lower() == "vmess" and decode_vmess(link) is None:
        return None
    base = link.split("#", 1)[0]  # اسم (remark) اصلی حذف می‌شود
    return base, base


def unescape_all(text):
    """گاهی لینک‌ها دوبار escape شده‌اند (&amp;amp;)؛ تا پایدار شدن باز می‌کنیم."""
    for _ in range(3):
        new = html.unescape(text)
        if new == text:
            break
        text = new
    return text


def norm_proxy(raw):
    raw = unescape_all(raw)

    def param(name):
        m = re.search(rf"[?&]{name}=([^&#\s]+)", raw)
        return m.group(1) if m else None

    server, port, secret = param("server"), param("port"), param("secret")
    if not (server and port and secret and port.isdigit()):
        return None
    key = f"{server}:{port}"
    return key, f"https://t.me/proxy?server={server}&port={port}&secret={secret}"


def extract(pages, kind, stats=None):
    """از چند صفحه‌ی HTML لیست [(key, link)] جدیدترین‌ها اول برمی‌گرداند."""
    regex, norm = (CONFIG_RE, norm_config) if kind == "config" else (PROXY_RE, norm_proxy)
    out, seen, raw_count = [], set(), 0
    for page in pages:
        text = html.unescape(page)
        found = regex.findall(text)
        raw_count += len(found)
        for raw in reversed(found):
            item = norm(raw)
            if item and item[0] not in seen:
                seen.add(item[0])
                out.append(item)
    if stats is not None:
        stats["raw"] = raw_count
    return out


async def _fetch(client, channel, before):
    """صفحه را می‌گیرد؛ با تلاش مجدد و آینه‌ی telegram.me. (متن یا None، توضیح)"""
    last = "بدون پاسخ"
    for host in ("t.me", "telegram.me"):
        for _ in range(2):
            try:
                r = await client.get(
                    f"https://{host}/s/{channel}",
                    params={"before": before} if before else None,
                )
                if r.status_code == 200:
                    return r.text, "200"
                last = f"HTTP {r.status_code}"
            except Exception as e:
                last = type(e).__name__
            await asyncio.sleep(1.5)
    return None, last


async def scrape(channel, kind, pages=2):
    """(لیست [(key, link)], گزارش متنی برای عیب‌یابی)"""
    import httpx

    htmls, before, notes = [], None, []
    async with httpx.AsyncClient(
        timeout=25, headers={"User-Agent": UA}, follow_redirects=True
    ) as client:
        for _ in range(pages):
            text, status = await _fetch(client, channel, before)
            notes.append(status)
            if text is None:
                break
            htmls.append(text)
            ids = [int(x) for x in POST_ID_RE.findall(text)]
            if not ids:
                break
            before = min(ids)
    stats = {}
    items = extract(htmls, kind, stats)
    diag = (
        f"صفحه‌ها: {len(htmls)} ({'، '.join(notes)}) | "
        f"لینک خام: {stats.get('raw', 0)} | معتبر: {len(items)}"
    )
    log.info("%s → %s", channel, diag)
    return items, diag


# ───────────────────────── بررسی زنده بودن ─────────────────────────
def config_target(link):
    scheme = link.split("://", 1)[0].lower()
    if scheme in ("hysteria2", "hy2", "tuic"):  # UDP — با TCP قابل تست نیست
        return None
    if scheme == "vmess":
        d = decode_vmess(link)
        try:
            return (d["add"], int(d["port"])) if d else None
        except Exception:
            return None
    try:
        u = urlparse(link)
        if u.hostname and u.port:
            return u.hostname, u.port
    except ValueError:
        pass
    return None


def proxy_target(key):
    host, _, port = key.rpartition(":")
    return host, int(port)


async def tcp_alive(host, port, timeout=4.0):
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        w.close()
        try:
            await w.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def check_alive(items, kind):
    """items=[(key, link)] → [(key, link, alive)]"""
    sem = asyncio.Semaphore(40)

    async def one(key, link):
        target = proxy_target(key) if kind == "proxy" else config_target(link)
        if not target:
            return key, link, 1  # قابل تست نیست؛ سالم فرض می‌شود
        async with sem:
            return key, link, int(await tcp_alive(*target))

    res = await asyncio.gather(*(one(k, l) for k, l in items))
    # اگر هیچ‌کدام زنده نبود، احتمالاً خود تست مشکل دارد؛ همه را قبول کن
    if len(res) >= 5 and not any(r[2] for r in res):
        res = [(k, l, 1) for k, l, _ in res]
    return res


# ───────────────────────── برندسازی ─────────────────────────
def rebrand(link, remark):
    """اسم کانفیگ را با برند خودمان عوض می‌کند."""
    if link.split("://", 1)[0].lower() == "vmess":
        d = decode_vmess(link)
        if d is None:
            return link
        d["ps"] = remark
        raw = json.dumps(d, ensure_ascii=False, separators=(",", ":"))
        return "vmess://" + base64.b64encode(raw.encode()).decode()
    return link.split("#", 1)[0] + "#" + quote(remark, safe="")
