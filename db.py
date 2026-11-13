import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Tehran")
DB_PATH = Path(__file__).parent / "data" / "users.db"
TABLES = ("configs", "proxies")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    username TEXT,
    joined TEXT,
    last_seen TEXT,
    notify INTEGER DEFAULT 1,
    banned INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS configs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE,
    link TEXT,
    source TEXT,
    added_at TEXT,
    alive INTEGER DEFAULT 1,
    posted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS proxies(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE,
    link TEXT,
    source TEXT,
    added_at TEXT,
    alive INTEGER DEFAULT 1,
    posted INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS withdrawals(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    sat INTEGER,
    address TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    decided_at TEXT
);
CREATE TABLE IF NOT EXISTS miners(
    user_id INTEGER PRIMARY KEY,
    sat INTEGER DEFAULT 0,
    day TEXT DEFAULT '',
    taps INTEGER DEFAULT 0,
    tot INTEGER DEFAULT 0,
    ref INTEGER DEFAULT 0,
    inv INTEGER DEFAULT 0,
    paid INTEGER DEFAULT 0,
    ref_sat INTEGER DEFAULT 0,
    syncs INTEGER DEFAULT 0
);
"""


def now_str():
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now(TZ).strftime("%Y-%m-%d")


@contextmanager
def tx():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with tx() as c:
        c.executescript(SCHEMA)
        try:  # دیتابیس‌های قدیمی ستون syncs ندارند
            c.execute("ALTER TABLE miners ADD COLUMN syncs INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass


def _check_table(t):
    if t not in TABLES:
        raise ValueError(t)


# ───────────── کاربران ─────────────
def upsert_user(user):
    with tx() as c:
        c.execute(
            "INSERT OR IGNORE INTO users(user_id,name,username,joined,last_seen) "
            "VALUES(?,?,?,?,?)",
            (user.id, user.full_name, user.username or "", today(), now_str()),
        )
        c.execute(
            "UPDATE users SET name=?, username=?, last_seen=? WHERE user_id=?",
            (user.full_name, user.username or "", now_str(), user.id),
        )


def get_user(user_id):
    with tx() as c:
        return c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def toggle_notify(user_id):
    with tx() as c:
        c.execute("UPDATE users SET notify = 1 - notify WHERE user_id=?", (user_id,))


def is_banned(user_id):
    u = get_user(user_id)
    return bool(u and u["banned"])


def toggle_ban(user_id):
    """وضعیت جدید را برمی‌گرداند (True = مسدود)؛ اگر کاربر نبود None."""
    u = get_user(user_id)
    if not u:
        return None
    new = 0 if u["banned"] else 1
    with tx() as c:
        c.execute("UPDATE users SET banned=? WHERE user_id=?", (new, user_id))
    return bool(new)


def all_user_ids(notify_only=False):
    q = "SELECT user_id FROM users WHERE banned=0"
    if notify_only:
        q += " AND notify=1"
    with tx() as c:
        return [r[0] for r in c.execute(q).fetchall()]


def export_users():
    with tx() as c:
        return c.execute(
            "SELECT user_id,name,username,joined,last_seen,banned,notify "
            "FROM users ORDER BY joined"
        ).fetchall()


def stats():
    cutoff = (datetime.now(TZ) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    with tx() as c:
        one = lambda q, a=(): c.execute(q, a).fetchone()[0]
        return {
            "total": one("SELECT COUNT(*) FROM users"),
            "new_today": one("SELECT COUNT(*) FROM users WHERE joined=?", (today(),)),
            "active_24h": one("SELECT COUNT(*) FROM users WHERE last_seen>=?", (cutoff,)),
            "banned": one("SELECT COUNT(*) FROM users WHERE banned=1"),
            "notify_on": one("SELECT COUNT(*) FROM users WHERE notify=1 AND banned=0"),
            "configs": one("SELECT COUNT(*) FROM configs WHERE alive=1"),
            "proxies": one("SELECT COUNT(*) FROM proxies WHERE alive=1"),
        }


# ───────────── تنظیمات ─────────────
def get_setting(key, default=""):
    with tx() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_setting(key, value):
    with tx() as c:
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


# ───────────── کانفیگ و پروکسی ─────────────
def known_keys(table):
    _check_table(table)
    with tx() as c:
        return {r[0] for r in c.execute(f"SELECT key FROM {table}").fetchall()}


def add_items(table, rows, source):
    """rows = [(key, link, alive)] ؛ تعداد موارد جدید را برمی‌گرداند."""
    _check_table(table)
    added = 0
    with tx() as c:
        for key, link, alive in rows:
            cur = c.execute(
                f"INSERT OR IGNORE INTO {table}(key,link,source,added_at,alive) "
                "VALUES(?,?,?,?,?)",
                (key, link, source, now_str(), int(alive)),
            )
            added += cur.rowcount
    return added


def pick_for_post(table, n):
    """اول موارد تازه‌ی پست‌نشده؛ اگر کم بود با جدیدترین‌های قبلی پر می‌شود."""
    _check_table(table)
    with tx() as c:
        rows = c.execute(
            f"SELECT * FROM {table} WHERE alive=1 AND posted=0 ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
        if len(rows) < n:
            ids = [r["id"] for r in rows] or [-1]
            marks = ",".join("?" * len(ids))
            rows += c.execute(
                f"SELECT * FROM {table} WHERE alive=1 AND id NOT IN ({marks}) "
                "ORDER BY id DESC LIMIT ?",
                (*ids, n - len(rows)),
            ).fetchall()
        if not rows:  # هیچ مورد «زنده‌ای» نبود؛ تست از سرور ممکنه دقیق نباشه
            rows = c.execute(
                f"SELECT * FROM {table} ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        return rows


def mark_posted(table, ids):
    _check_table(table)
    with tx() as c:
        c.executemany(f"UPDATE {table} SET posted=1 WHERE id=?", [(i,) for i in ids])


def random_alive(table, n):
    _check_table(table)
    with tx() as c:
        rows = c.execute(
            f"SELECT * FROM (SELECT * FROM {table} WHERE alive=1 ORDER BY id DESC LIMIT 60) "
            "ORDER BY RANDOM() LIMIT ?",
            (n,),
        ).fetchall()
        if not rows:  # اگر هیچ‌کدام زنده نبود، جدیدترین‌ها نشان داده شوند
            rows = c.execute(
                f"SELECT * FROM (SELECT * FROM {table} ORDER BY id DESC LIMIT 60) "
                "ORDER BY RANDOM() LIMIT ?",
                (n,),
            ).fetchall()
        return rows


def trim(keep=400):
    with tx() as c:
        for t in TABLES:
            c.execute(
                f"DELETE FROM {t} WHERE id NOT IN "
                f"(SELECT id FROM {t} ORDER BY id DESC LIMIT ?)",
                (keep,),
            )


# ───────────── استخراج (miners) ─────────────
def miner_get(user_id, create=True):
    with tx() as c:
        r = c.execute("SELECT * FROM miners WHERE user_id=?", (user_id,)).fetchone()
        if r is None and create:
            c.execute("INSERT INTO miners(user_id) VALUES(?)", (user_id,))
            r = c.execute("SELECT * FROM miners WHERE user_id=?", (user_id,)).fetchone()
        return dict(r) if r else None


def miner_set(user_id, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with tx() as c:
        c.execute(f"UPDATE miners SET {cols} WHERE user_id=?", (*fields.values(), user_id))


def miner_top(n=10):
    with tx() as c:
        return c.execute(
            "SELECT m.user_id, m.sat, m.inv, u.name FROM miners m "
            "LEFT JOIN users u ON u.user_id=m.user_id "
            "WHERE m.sat>0 ORDER BY m.sat DESC LIMIT ?",
            (n,),
        ).fetchall()


def miner_stats():
    with tx() as c:
        r = c.execute(
            "SELECT COUNT(*), COALESCE(SUM(sat),0), COALESCE(SUM(tot),0), COALESCE(SUM(inv),0) "
            "FROM miners WHERE tot>0 OR inv>0"
        ).fetchone()
        return {"miners": r[0], "sat": r[1], "taps": r[2], "invites": r[3]}


# ───────────── برداشت‌ها ─────────────
def wd_create(user_id, sat, address):
    with tx() as c:
        cur = c.execute(
            "INSERT INTO withdrawals(user_id,sat,address,created_at) VALUES(?,?,?,?)",
            (user_id, sat, address, now_str()),
        )
        return cur.lastrowid


def wd_get(wd_id):
    with tx() as c:
        r = c.execute("SELECT * FROM withdrawals WHERE id=?", (wd_id,)).fetchone()
        return dict(r) if r else None


def wd_set_status(wd_id, status):
    with tx() as c:
        c.execute(
            "UPDATE withdrawals SET status=?, decided_at=? WHERE id=?",
            (status, now_str(), wd_id),
        )


def wd_pending(limit=10):
    with tx() as c:
        return c.execute(
            "SELECT w.*, u.name FROM withdrawals w LEFT JOIN users u ON u.user_id=w.user_id "
            "WHERE w.status='pending' ORDER BY w.id LIMIT ?",
            (limit,),
        ).fetchall()


def wd_user_pending(user_id):
    with tx() as c:
        return c.execute(
            "SELECT COUNT(*) FROM withdrawals WHERE user_id=? AND status='pending'", (user_id,)
        ).fetchone()[0]


def wd_stats():
    with tx() as c:
        r = c.execute(
            "SELECT "
            "COALESCE(SUM(status='pending'),0), COALESCE(SUM(CASE WHEN status='pending' THEN sat END),0), "
            "COALESCE(SUM(status='paid'),0), COALESCE(SUM(CASE WHEN status='paid' THEN sat END),0) "
            "FROM withdrawals"
        ).fetchone()
        return {"pending": r[0], "pending_sat": r[1], "paid": r[2], "paid_sat": r[3]}
