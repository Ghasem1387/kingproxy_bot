import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv اختیاری است (روی Actions لازم نیست)
    pass

BASE = Path(__file__).parent
BANNER = BASE / "banner.png"

# ───────── اطلاعات اصلی ─────────
BOT_TOKEN = os.environ["BOT_TOKEN"]

# ادمین‌ها (آیدی عددی). اولین آیدی محل ذخیره‌ی بکاپ دیتابیس است.
ADMIN_IDS = {
    int(x)
    for x in os.getenv("ADMIN_IDS", "8564515287").replace(" ", "").split(",")
    if x
}
SUPPORT_USERNAME = "hechkim0122"

# کانال‌های قفل (کاربر باید عضو هر دو باشد)
LOCK_CHANNELS = ["@donyayeman0122", "@kingproxy0122"]

# کانالی که ربات هر روز در آن پست می‌گذارد (ربات باید ادمین باشد)
POST_CHANNEL = "@kingproxy0122"

# ربات‌های دیگر
OTHER_BOT = "donyayeman0122_bot"

# ───────── منبع‌های خودکار ─────────
CONFIG_SOURCE = "prrofile_purple"  # کانال کانفیگ
PROXY_SOURCE = "iRoProxy"  # کانال پروکسی

# ───────── زمان‌بندی (ساعت تهران) ─────────
PROXY_POST_HOUR = int(os.getenv("PROXY_POST_HOUR", "10"))
CONFIG_POST_HOUR = int(os.getenv("CONFIG_POST_HOUR", "18"))
PROXIES_PER_POST = 8
CONFIGS_PER_POST = 5
REFRESH_EVERY = 2 * 3600  # بروزرسانی منابع هر ۲ ساعت
BACKUP_EVERY = 300  # بررسی بکاپ هر ۵ دقیقه

BRAND_REMARK = "👑 KingProxy"

# ───────── استخراج بیت‌کوین ─────────
SAT = 100_000_000  # ۱ بیت‌کوین = ۱۰۰ میلیون ساتوشی (محاسبات با عدد صحیح، بدون خطای اعشار)
DAILY_BATTERY = 100  # باتری روزانه (تعداد ضربه)
TAP_SAT = 10  # هر ضربه = 0.0000001 BTC
REF_SAT = 500  # پاداش دعوت = 0.000005 BTC
WD_MIN_SAT = 25_000  # حداقل برداشت = 0.00025 BTC
REF_TAPS = 100  # دعوت وقتی فعال حساب می‌شود که دوست دعوت‌شده ۱۰۰ ضربه بزند

# صفحه‌ی استخراج (مینی‌اپ) روی GitHub Pages ← فایل miner.html باید در مخزن باشد و Pages فعال
# اگر نام کاربری یا مخزنت فرق دارد، اینجا یا با متغیر MINER_URL عوضش کن.
MINER_URL = os.getenv("MINER_URL", "https://ghasem1387.github.io/kingproxy_bot/miner.html")
