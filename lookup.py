import os
import sqlite3
import threading
import time
import tempfile
import urllib3
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple

import requests
import telebot
from flask import Flask
from telebot.types import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

try:
    from telebot.types import KeyboardButtonRequestUsers
except Exception:
    KeyboardButtonRequestUsers = None

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================================================
# CONFIG
# =========================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8673660611:AAGfh5XtqXPFj1mZyn4T-farsHQaaefvsl8")
DB_PATH = os.environ.get("DB_PATH", os.path.join(tempfile.gettempdir(), "mam_lookup.db"))

BACKUP_CHAT_ID = int(os.environ.get("BACKUP_CHAT_ID", "-1003810437182"))
DEVELOPER_ID = int(os.environ.get("DEVELOPER_ID", "8124982995"))
DEVELOPER_USERNAME = os.environ.get("DEVELOPER_USERNAME", "@Why_Mam")
DEFAULT_LOG_CHAT_ID = int(os.environ.get("LOG_CHAT_ID", BACKUP_CHAT_ID))
API_TIMEOUT = int(os.environ.get("API_TIMEOUT", "30"))
SELF_URL = os.environ.get("SELF_URL", "").strip()

BOT_NAME = "𓆩˚ᗰꫝꪑ •ᏝʘʘƙᏬթ ˚𓆪"

os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# =========================================================
# KEEP ALIVE
# =========================================================
app = Flask(__name__)

@app.route("/")
def home():
    return "OK"

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

def keep_alive():
    threading.Thread(target=run_web, daemon=True).start()

def self_ping():
    while True:
        try:
            if SELF_URL:
                requests.get(SELF_URL, timeout=20)
        except Exception:
            pass
        time.sleep(300)

# =========================================================
# DB HELPERS
# =========================================================
CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
CONN.row_factory = sqlite3.Row
LOCK = threading.Lock()

def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

def parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def execute(query, params=()):
    with LOCK:
        cur = CONN.cursor()
        cur.execute(query, params)
        CONN.commit()
        return cur

def fetchone(query, params=()):
    with LOCK:
        cur = CONN.cursor()
        cur.execute(query, params)
        return cur.fetchone()

def fetchall(query, params=()):
    with LOCK:
        cur = CONN.cursor()
        cur.execute(query, params)
        return cur.fetchall()

# =========================================================
# INIT DB
# =========================================================
def init_db():
    execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            join_date TEXT,
            is_approved INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            current_limit INTEGER DEFAULT 0,
            total_lookup INTEGER DEFAULT 0,
            last_bonus_at TEXT DEFAULT NULL,
            today_lookup INTEGER DEFAULT 0,
            ref_points INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS pending_requests (
            chat_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            requested_at TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            limit_value INTEGER NOT NULL,
            max_uses INTEGER NOT NULL,
            used_count INTEGER DEFAULT 0,
            expires_at TEXT,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS redeem_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            user_chat_id INTEGER NOT NULL,
            used_at TEXT NOT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS lookup_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_chat_id INTEGER NOT NULL,
            target_id TEXT NOT NULL,
            target_name TEXT,
            phone_masked TEXT,
            country TEXT,
            api_used TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_user INTEGER,
            extra_data TEXT,
            created_at TEXT NOT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS broadcast_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            message_text TEXT NOT NULL,
            total_users INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS user_states (
            chat_id INTEGER PRIMARY KEY,
            state TEXT,
            temp_id TEXT,
            temp_text TEXT,
            temp_code TEXT,
            temp_limit INTEGER,
            temp_uses INTEGER,
            temp_expiry TEXT,
            temp_user_id INTEGER,
            panel_message_id INTEGER,
            page INTEGER DEFAULT 0
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS bot_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS force_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_username TEXT NOT NULL,
            channel_link TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS api_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url_template TEXT NOT NULL,
            api_key TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            is_fallback INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 100,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            last_success_at TEXT,
            last_fail_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            referred_user INTEGER PRIMARY KEY,
            referrer_user INTEGER NOT NULL,
            points INTEGER DEFAULT 3,
            counted_at TEXT NOT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS admins (
            chat_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            is_active INTEGER DEFAULT 1,
            is_full_access INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    execute("""
        CREATE TABLE IF NOT EXISTS admin_permissions (
            admin_chat_id INTEGER PRIMARY KEY,
            can_approve_users INTEGER DEFAULT 0,
            can_manage_users INTEGER DEFAULT 0,
            can_manage_limits INTEGER DEFAULT 0,
            can_manage_redeem INTEGER DEFAULT 0,
            can_broadcast INTEGER DEFAULT 0,
            can_view_logs INTEGER DEFAULT 0,
            can_manage_apis INTEGER DEFAULT 0,
            can_manage_settings INTEGER DEFAULT 0,
            can_manage_admins INTEGER DEFAULT 0,
            can_backup_restore INTEGER DEFAULT 0
        )
    """)

    seed_default_settings()
    seed_default_admin()
    seed_default_api()

def seed_default_api():
    if fetchone("SELECT id FROM api_configs LIMIT 1"):
        return

    execute("""
        INSERT INTO api_configs
        (name, url_template, api_key, is_active, is_fallback, priority, success_count, fail_count, created_at)
        VALUES (?, ?, '', 1, 0, 1, 0, 0, ?)
    """, (
        "V1",
        "http://api.igfollows.site/user/?key=KP&number={user_id}",
        now_str()
    ))

def seed_default_settings():
    defaults = {
        "initial_limit": "5",
        "daily_bonus": "3",
        "daily_bonus_enabled": "1",
        "force_join_enabled": "0",
        "bot_enabled": "1",
        "admin_approval_enabled": "1",
        "maintenance_text": "⚠️ Bot is temporarily OFF by Admin...",
        "backup_interval_hours": "1",
        "log_chat_id": str(DEFAULT_LOG_CHAT_ID),
        "log_success_enabled": "1",
        "log_fail_enabled": "1",
    }

    for k, v in defaults.items():
        if not fetchone("SELECT key FROM bot_settings WHERE key = ?", (k,)):
            execute(
                "INSERT INTO bot_settings (key, value, updated_at) VALUES (?, ?, ?)",
                (k, v, now_str())
            )

def seed_default_admin():
    execute("""
        INSERT OR IGNORE INTO admins
        (chat_id, full_name, username, is_active, is_full_access, created_at)
        VALUES (?, ?, ?, 1, 1, ?)
    """, (
        DEVELOPER_ID,
        "Developer",
        DEVELOPER_USERNAME.lstrip("@"),
        now_str()
    ))

    execute("""
        INSERT OR IGNORE INTO admin_permissions
        (
            admin_chat_id,
            can_approve_users,
            can_manage_users,
            can_manage_limits,
            can_manage_redeem,
            can_broadcast,
            can_view_logs,
            can_manage_apis,
            can_manage_settings,
            can_manage_admins,
            can_backup_restore
        )
        VALUES (?,1,1,1,1,1,1,1,1,1,1)
    """, (DEVELOPER_ID,))

# =========================================================
# SETTINGS
# =========================================================
def get_setting(key, default=""):
    row = fetchone("SELECT value FROM bot_settings WHERE key = ?", (key,))
    return row["value"] if row else default

def set_setting(key, value):
    execute(
        "INSERT OR REPLACE INTO bot_settings (key, value, updated_at) VALUES (?, ?, ?)",
        (key, str(value), now_str())
    )

def get_int_setting(key, default):
    try:
        return int(get_setting(key, str(default)))
    except Exception:
        return default

def is_setting_on(key, default=False):
    return get_setting(key, "1" if default else "0") == "1"

# =========================================================
# ADMIN / PERMISSION
# =========================================================
def is_admin(chat_id):
    return bool(fetchone(
        "SELECT 1 FROM admins WHERE chat_id = ? AND is_active = 1",
        (chat_id,)
    ))

def has_permission(chat_id, perm):
    if chat_id == DEVELOPER_ID:
        return True

    admin = fetchone(
        "SELECT * FROM admins WHERE chat_id = ? AND is_active = 1",
        (chat_id,)
    )

    if not admin:
        return False

    if int(admin["is_full_access"]) == 1:
        return True

    row = fetchone(
        "SELECT * FROM admin_permissions WHERE admin_chat_id = ?",
        (chat_id,)
    )

    if not row:
        return False

    return int(row[perm]) == 1 if perm in row.keys() else False

# =========================================================
# USER HELPERS
# =========================================================
def get_user(chat_id):
    return fetchone("SELECT * FROM users WHERE chat_id = ?", (chat_id,))

def create_user_if_missing(message):
    chat_id = message.from_user.id

    if get_user(chat_id):
        return

    execute("""
        INSERT INTO users
        (chat_id, full_name, username, join_date, is_approved, is_blocked, current_limit, total_lookup)
        VALUES (?, ?, ?, ?, 0, 0, 0, 0)
    """, (
        chat_id,
        message.from_user.full_name or "Unknown",
        message.from_user.username or "",
        now_str()
    ))

def ensure_pending(message):
    create_user_if_missing(message)
    execute("""
        INSERT OR REPLACE INTO pending_requests
        (chat_id, full_name, username, requested_at)
        VALUES (?, ?, ?, ?)
    """, (
        message.from_user.id,
        message.from_user.full_name or "Unknown",
        message.from_user.username or "",
        now_str()
    ))

def ensure_pending_user(user_id, full_name, username):
    execute("""
        INSERT OR REPLACE INTO pending_requests
        (chat_id, full_name, username, requested_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        full_name or "Unknown",
        username or "",
        now_str()
    ))

def approve_user(chat_id):
    user = get_user(chat_id)
    if not user:
        return False

    current_limit = int(user["current_limit"] or 0)
    initial_limit = get_int_setting("initial_limit", 5)
    new_limit = current_limit if int(user["is_approved"]) == 1 else max(current_limit, initial_limit)

    execute(
        "UPDATE users SET is_approved = 1, is_blocked = 0, current_limit = ? WHERE chat_id = ?",
        (new_limit, chat_id)
    )

    execute("DELETE FROM pending_requests WHERE chat_id = ?", (chat_id,))

    try:
        count_referral_if_valid(chat_id)
    except Exception:
        pass

    return True

def reject_user(chat_id):
    execute("DELETE FROM pending_requests WHERE chat_id = ?", (chat_id,))
    execute("DELETE FROM users WHERE chat_id = ? AND is_approved = 0", (chat_id,))
    return True

def block_user(chat_id):
    return execute(
        "UPDATE users SET is_blocked = 1 WHERE chat_id = ?",
        (chat_id,)
    ).rowcount > 0

def unblock_user(chat_id):
    return execute(
        "UPDATE users SET is_blocked = 0 WHERE chat_id = ?",
        (chat_id,)
    ).rowcount > 0

def add_limit(chat_id, amount):
    return execute(
        "UPDATE users SET current_limit = current_limit + ? WHERE chat_id = ?",
        (amount, chat_id)
    ).rowcount > 0

def remove_limit(chat_id, amount):
    user = get_user(chat_id)
    if not user:
        return False

    new_limit = max(0, int(user["current_limit"] or 0) - amount)
    execute(
        "UPDATE users SET current_limit = ? WHERE chat_id = ?",
        (new_limit, chat_id)
    )
    return True

# =========================================================
# REFERRAL
# =========================================================
def count_referral_if_valid(user_id):
    user = get_user(user_id)

    if not user or not user["referred_by"]:
        return False

    referrer_id = int(user["referred_by"])

    if referrer_id == user_id:
        return False

    if not get_user(referrer_id):
        return False

    if fetchone("SELECT 1 FROM referrals WHERE referred_user = ?", (user_id,)):
        return False

    execute("""
        INSERT INTO referrals
        (referred_user, referrer_user, points, counted_at)
        VALUES (?, ?, 3, ?)
    """, (user_id, referrer_id, now_str()))

    execute(
        "UPDATE users SET ref_points = ref_points + 2, current_limit = current_limit + 2 WHERE chat_id = ?",
        (referrer_id,)
    )

    try:
        bot.send_message(
            referrer_id,
            "🎉 <b>New Referral Success!</b>\n\n"
            f"✅ User ID: <code>{user_id}</code>\n"
            "⭐ You earned <b>2 limit</b>."
        )
    except Exception:
        pass

    return True

# =========================================================
# STATE
# =========================================================
def get_state(chat_id):
    return fetchone("SELECT * FROM user_states WHERE chat_id = ?", (chat_id,))

def set_state(chat_id, **kwargs):
    if not get_state(chat_id):
        execute("INSERT INTO user_states (chat_id) VALUES (?)", (chat_id,))

    for k, v in kwargs.items():
        execute(f"UPDATE user_states SET {k} = ? WHERE chat_id = ?", (v, chat_id))

def clear_state(chat_id):
    execute("""
        UPDATE user_states SET
            state = NULL,
            temp_id = NULL,
            temp_text = NULL,
            temp_code = NULL,
            temp_limit = NULL,
            temp_uses = NULL,
            temp_expiry = NULL,
            temp_user_id = NULL,
            panel_message_id = NULL
        WHERE chat_id = ?
    """, (chat_id,))

# =========================================================
# BONUS
# =========================================================
def can_claim_bonus(user_row):
    last_bonus_at = parse_dt(user_row["last_bonus_at"])

    if not last_bonus_at:
        return True

    return datetime.now(timezone.utc) >= (last_bonus_at + timedelta(hours=24))

# =========================================================
# MASK PHONE / API PARSE
# =========================================================
def mask_phone(phone):
    phone = str(phone or "").strip()

    if not phone:
        return None

    if len(phone) <= 6:
        return "*" * len(phone)

    return phone[:5] + "*" * max(3, len(phone) - 8) + phone[-3:]

def extract_lookup_result(data):
    phone = None
    country = None
    country_code = ""
    extra = []

    if isinstance(data, dict):
        inner = data.get("data")

        if isinstance(inner, dict):
            phone = inner.get("phone") or inner.get("phone_number") or inner.get("number") or inner.get("mobile")
            country = inner.get("country") or inner.get("country_name")
            country_code = inner.get("country_code") or ""
            for k in ["name", "username", "id", "user_id", "status", "message"]:
                if inner.get(k) not in [None, ""]:
                    extra.append(f"{k}: {inner.get(k)}")
        else:
            phone = data.get("phone") or data.get("phone_number") or data.get("number") or data.get("mobile")
            country = data.get("country") or data.get("country_name")
            country_code = data.get("country_code") or ""
            for k in ["name", "username", "id", "user_id", "status", "message"]:
                if data.get(k) not in [None, ""]:
                    extra.append(f"{k}: {data.get(k)}")

    if phone and country_code and not str(phone).startswith(str(country_code)):
        phone = f"{country_code}{phone}"

    return {
        "phone_masked": phone,
        "country": country,
        "country_code": country_code,
        "extra": "\n".join(extra[:8]) if extra else ""
    }

# =========================================================
# API
# =========================================================
def get_active_apis():
    return fetchall("""
        SELECT * FROM api_configs
        WHERE is_active = 1
        ORDER BY is_fallback ASC, priority ASC, id ASC
    """)

def call_lookup_api(user_id):
    apis = get_active_apis()

    if not apis:
        return False, None, None, None, "No active API found"

    for api in apis:
        api_name = api["name"]

        try:
            url = api["url_template"].format(user_id=user_id)

            headers = {
                "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/123.0 Mobile Safari/537.36",
                "Accept": "application/json,text/plain,*/*",
                "Connection": "close",
            }

            if api["api_key"]:
                headers["Authorization"] = f"Bearer {api['api_key']}"

            res = requests.get(
                url,
                timeout=API_TIMEOUT,
                headers=headers,
                verify=False
            )

            if res.status_code != 200:
                execute(
                    "UPDATE api_configs SET fail_count = fail_count + 1, last_fail_at = ?, last_error = ? WHERE id = ?",
                    (now_str(), f"HTTP {res.status_code}", api["id"])
                )
                continue

            try:
                data = res.json()
            except Exception:
                execute(
                    "UPDATE api_configs SET fail_count = fail_count + 1, last_fail_at = ?, last_error = ? WHERE id = ?",
                    (now_str(), "Invalid JSON response", api["id"])
                )
                continue

            result = extract_lookup_result(data)

            if result["phone_masked"] or result["country"] or result["extra"]:
                execute(
                    "UPDATE api_configs SET success_count = success_count + 1, last_success_at = ?, last_error = NULL WHERE id = ?",
                    (now_str(), api["id"])
                )
                return True, api_name, result["phone_masked"], result["country"], result["extra"]

            execute(
                "UPDATE api_configs SET fail_count = fail_count + 1, last_fail_at = ?, last_error = ? WHERE id = ?",
                (now_str(), "No useful result found", api["id"])
            )

        except Exception as e:
            execute(
                "UPDATE api_configs SET fail_count = fail_count + 1, last_fail_at = ?, last_error = ? WHERE id = ?",
                (now_str(), str(e)[:250], api["id"])
            )

    return False, None, None, None, "All APIs failed"

# =========================================================
# LOGGING
# =========================================================
def log_admin(actor_id, action, target_user=None, extra_data=""):
    execute("""
        INSERT INTO admin_logs
        (admin_id, action, target_user, extra_data, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (actor_id, action, target_user, extra_data, now_str()))

    log_chat = get_int_setting("log_chat_id", DEFAULT_LOG_CHAT_ID)

    text = (
        "👑 <b>Admin Action</b>\n\n"
        f"<b>Admin:</b> <code>{actor_id}</code>\n"
        f"<b>Action:</b> {action}\n"
    )

    if target_user:
        text += f"<b>Target:</b> <code>{target_user}</code>\n"

    if extra_data:
        text += f"<b>Extra:</b> <code>{extra_data}</code>\n"

    text += f"<b>Time:</b> {now_str()}"

    try:
        bot.send_message(log_chat, text)
    except Exception:
        pass

def log_lookup(user_chat_id, target_id, target_name, phone_masked, country, api_used, status):
    execute("""
        INSERT INTO lookup_logs
        (user_chat_id, target_id, target_name, phone_masked, country, api_used, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_chat_id,
        target_id,
        target_name,
        phone_masked,
        country,
        api_used,
        status,
        now_str()
    ))

    log_chat = get_int_setting("log_chat_id", DEFAULT_LOG_CHAT_ID)

    if status == "success" and not is_setting_on("log_success_enabled", True):
        return

    if status != "success" and not is_setting_on("log_fail_enabled", True):
        return

    user = get_user(user_chat_id)
    name = user["full_name"] if user else "Unknown"

    text = (
        "📞 <b>Lookup Log</b>\n\n"
        f"<b>User:</b> {name}\n"
        f"<b>User ID:</b> <code>{user_chat_id}</code>\n"
        f"<b>Target ID:</b> <code>{target_id}</code>\n"
        f"<b>Masked Phone:</b> <code>{phone_masked or '-'}</code>\n"
        f"<b>Country:</b> {country or '-'}\n"
        f"<b>API:</b> {api_used or '-'}\n"
        f"<b>Status:</b> {status}\n"
        f"<b>Time:</b> {now_str()}"
    )

    try:
        bot.send_message(log_chat, text)
    except Exception:
        pass

# =========================================================
# FORCE JOIN
# =========================================================
def get_active_channels():
    return fetchall("SELECT * FROM force_channels WHERE is_active = 1 ORDER BY id DESC")

def check_force_join(user_id):
    if is_admin(user_id):
        return True, []

    if not is_setting_on("force_join_enabled", False):
        return True, []

    channels = get_active_channels()

    if not channels:
        return True, []

    missing = []

    for ch in channels:
        try:
            member = bot.get_chat_member(ch["channel_username"], user_id)
            if member.status not in ["member", "administrator", "creator"]:
                missing.append(ch)
        except Exception:
            missing.append(ch)

    return len(missing) == 0, missing

# =========================================================
# UI
# =========================================================
def btn(text, cb, style=None):
    try:
        return InlineKeyboardButton(text, callback_data=cb, style=style) if style else InlineKeyboardButton(text, callback_data=cb)
    except TypeError:
        return InlineKeyboardButton(text, callback_data=cb)

def user_reply_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)

    # Row 1 (Both Green, Select User RIGHT)
    if KeyboardButtonRequestUsers:
        try:
            request = KeyboardButtonRequestUsers(
                request_id=1001,
                user_is_bot=False,
                max_quantity=1,
                request_name=True,
                request_username=True,
                request_photo=False
            )
            kb.row(
                KeyboardButton("🔍 Lookup by ID", style="success"),
                KeyboardButton("👤 Select User", request_users=request, style="success")
            )
        except TypeError:
            kb.row(
                KeyboardButton("🔍 Lookup by ID", style="success"),
                KeyboardButton("👤 Select User", style="success")
            )
    else:
        kb.row(
            KeyboardButton("🔍 Lookup by ID", style="success"),
            KeyboardButton("👤 Select User", style="success")
        )

    # Row 2 (Profile red, Daily blue)
    kb.row(
        KeyboardButton("🔵 Profile", style="danger"),
        KeyboardButton("🟢 Daily Bonus", style="primary")
    )

    # Row 3 (Help red, Redeem blue)
    kb.row(
        KeyboardButton("🔴 Help", style="danger"),
        KeyboardButton("🔵 Redeem", style="primary")
    )

    # Row 4 (Developer red, Refer blue)
    kb.row(
        KeyboardButton("🔴 Developer", style="danger"),
        KeyboardButton("🟣 Refer & Earn", style="primary")
    )

    return kb

def denied_kb(channels=None):
    kb = InlineKeyboardMarkup(row_width=1)

    if channels:
        for ch in channels:
            kb.add(InlineKeyboardButton(f"📢 Join {ch['channel_username']}", url=ch["channel_link"]))
        kb.add(btn("✅ Check Again", "force_join_recheck", "success"))
    else:
        kb.add(InlineKeyboardButton("Contact Developer", url=f"https://t.me/{DEVELOPER_USERNAME.lstrip('@')}"))

    return kb

def back_only_kb(back_cb="admin_home"):
    kb = InlineKeyboardMarkup()
    kb.add(btn("⬅️ Back", back_cb, "primary"))
    return kb

def admin_home_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(btn("👥 Users", "menu_users", "primary"), btn("🎁 Limits & Redeem", "menu_limits", "primary"))
    kb.add(btn("🌐 API Manager", "menu_apis", "primary"), btn("📢 Broadcast", "menu_broadcast", "primary"))
    kb.add(btn("📊 Stats", "menu_stats", "primary"), btn("📜 Logs", "menu_logs", "primary"))
    kb.add(btn("⚙️ Developer Settings", "menu_dev", "success"))
    return kb

def users_menu_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(btn("📋 All Users", "users_page:0", "primary"), btn("🚫 Blocked Users", "blocked_page:0", "danger"))
    kb.add(btn("⏳ Pending Requests", "admin_pending", "primary"))
    kb.add(btn("🔎 Find / Manage User", "admin_find_user", "primary"))
    kb.add(btn("⬅️ Back", "admin_home", "primary"))
    return kb

def limits_menu_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(btn("➕ Add Limit", "admin_add_limit", "success"), btn("➖ Remove Limit", "admin_remove_limit", "danger"))
    kb.add(btn("🎟 Create Redeem", "admin_create_redeem", "success"), btn("🎁 Redeem List", "admin_redeem_list", "primary"))
    kb.add(btn("🗑 Delete Redeem", "admin_delete_redeem", "danger"))
    kb.add(btn("⬅️ Back", "admin_home", "primary"))
    return kb

def api_menu_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(btn("➕ Add API", "api_add", "success"), btn("📃 List APIs", "api_list", "primary"))
    kb.add(btn("🔁 Set Fallback", "api_set_fallback", "success"), btn("🧪 Test API", "api_test_select", "primary"))
    kb.add(btn("📊 API Performance", "api_performance", "primary"), btn("🗑 Delete API", "api_delete_select", "danger"))
    kb.add(btn("⬅️ Back", "admin_home", "primary"))
    return kb

def logs_menu_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(btn("📞 Lookup Logs", "view_lookup_logs:0", "primary"), btn("👑 Admin Logs", "view_admin_logs:0", "primary"))
    kb.add(btn("📢 Broadcast Logs", "view_broadcast_logs:0", "primary"), btn("🧹 Clean Old Logs", "clean_old_logs", "danger"))
    kb.add(btn("⬅️ Back", "admin_home", "primary"))
    return kb

def dev_menu_kb():
    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(
        btn("🤖 Bot ON/OFF", "dev_bot_toggle", "success"),
        btn("🎁 Bonus Settings", "dev_bonus", "primary")
    )

    approval_text = "🔒 Approval OFF" if is_setting_on("admin_approval_enabled", True) else "🔓 Approval ON"
    approval_style = "danger" if is_setting_on("admin_approval_enabled", True) else "success"

    kb.add(btn(approval_text, "toggle_admin_approval", approval_style))

    kb.add(
        btn("📢 Force Join Settings", "dev_force_join", "primary"),
        btn("📢 Log Channel Settings", "dev_log_settings", "primary")
    )

    kb.add(
        btn("💾 Backup Settings", "dev_backup_settings", "primary"),
        btn("👑 Admin Manager", "dev_admins", "primary")
    )

    kb.add(btn("⬅️ Back", "admin_home", "primary"))

    return kb
    
def backup_settings_kb():
    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(
        btn("⏱ Set Interval", "backup_interval_menu", "primary"),
        btn("💾 Backup Now", "backup_now", "success")
    )

    kb.add(btn("⬅️ Back", "menu_dev", "primary"))
    return kb


def backup_interval_kb():
    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(btn("1h", "backup_interval:1", "primary"),
           btn("2h", "backup_interval:2", "primary"))

    kb.add(btn("6h", "backup_interval:6", "primary"),
           btn("12h", "backup_interval:12", "primary"))

    kb.add(btn("24h", "backup_interval:24", "success"))

    kb.add(btn("⬅️ Back", "dev_backup_settings", "primary"))

    return kb

def admin_manage_user_kb(target_id):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(btn("🟢 Approve", f"manual_approve:{target_id}", "success"), btn("🔴 Reject", f"manual_reject:{target_id}", "danger"))
    kb.add(btn("➕ Add Limit", f"manual_add_limit:{target_id}", "success"), btn("➖ Remove Limit", f"manual_remove_limit:{target_id}", "danger"))
    kb.add(btn("🚫 Ban", f"manual_ban:{target_id}", "danger"), btn("♻️ Unban", f"manual_unban:{target_id}", "success"))
    kb.add(btn("📄 User Details", f"manual_user_details:{target_id}", "primary"))
    kb.add(btn("⬅️ Back", "menu_users", "primary"))
    return kb

def pagination_kb(prefix, page, has_next, back_cb="menu_users"):
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = []

    if page > 0:
        buttons.append(btn("⬅️ Prev", f"{prefix}:{page-1}", "primary"))

    if has_next:
        buttons.append(btn("➡️ Next", f"{prefix}:{page+1}", "primary"))

    if buttons:
        kb.row(*buttons)

    kb.add(btn("⬅️ Back", back_cb, "primary"))

    return kb

# =========================================================
# TEXTS
# =========================================================
def approved_welcome_text(limit_value):
    return (
        "╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        f"║  🌟 <b>{BOT_NAME}</b> 🌟  ║\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝\n\n"
        "❱ <b>Hello! Welcome Back</b> 👋\n"
        "❱ Your lookup panel is live & ready.\n\n"
        "╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        "║  📊  <b>Account Overview</b>     ║\n"
        "╠━━━━━━━━━━━━━━━━━━━━━━━━━╣\n"
        f"║  ➤ Limit   ❱  <b>{limit_value}</b>\n"
        "║  ➤ Status  ❱  <b>🟢 Active</b>\n"
        "║  ➤ Access  ❱  <b>🔓 Granted</b>\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝\n\n"
        "⚡ <b>Fast  ·  Smart  ·  Powerful</b>\n\n"
        "╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        "║  ❱❱  <b>Choose an option</b>  ⬇️   ║\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝"
    )

def unapproved_text():
    return (
        f"❌ <b>Access Denied - {BOT_NAME}</b>\n\n"
        "You are not approved to use this bot yet.\n"
        "Please contact the admin and request access."
    )

def blocked_text():
    return (
        "🚫 <b>You are blocked</b>\n\n"
        "Your access to this bot has been restricted."
    )

def maintenance_text():
    return get_setting("maintenance_text", "⚠️ Bot is temporarily unavailable.")

def lookup_success_text(target_id, target_name, phone_masked, country, api_name, extra, remaining):
    text = (
        "╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        "║  ✅ <b>LOOKUP SUCCESS</b> ✅  ║\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝\n\n"
        f"❱ <b>Target</b> ❱ {target_name or 'Unknown'}\n"
        f"❱ <b>User ID</b> ❱ <code>{target_id}</code>\n"
        f"❱ <b>API</b> ❱ <b>{api_name}</b>\n\n"
        "╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        "║  📌  <b>Result</b>\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝\n"
        f"❱ <b>Phone</b> ❱ <code>{phone_masked or 'Not Found (Account must be 1-2 Yr Old)'}</code>\n"
        f"❱ <b>Country</b> ❱ {country or '-'}\n"
    )

    if extra:
        text += f"\n<code>{extra[:500]}</code>\n"

    text += (
        "\n╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        f"║  ➤ Remaining Limit ❱ <b>{remaining}</b>\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝"
    )

    return text

def lookup_fail_text(reason):
    return (
        "╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        "║  ❌ <b>LOOKUP FAILED</b> ❌  ║\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝\n\n"
        f"❱ <b>Reason</b> ❱ {reason}\n\n"
        "⚠️ <i>No limit was deducted.</i>"
    )

def help_text():
    return (
        "╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        f"║  📖 <b>{BOT_NAME} HELP</b> 📖  ║\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝\n\n"
        "🔍 <b>Lookup by ID</b>\n"
        "❱ You can lookup using a Telegram numeric user ID.\n\n"
        "👤 <b>Select User</b>\n"
        "❱ You can select a user using Telegram’s official user picker.\n\n"
        "💰 <b>Limit System</b>\n"
        "❱ Successful lookup = 1 limit.\n"
        "❱ Failed lookup = no limit deducted.\n\n"
        "🎁 <b>Daily Bonus</b>\n"
        "❱ You can claim bonus once every 24 hours.\n\n"
        "🟣 <b>Refer & Earn</b>\n"
        "❱ Get +2 limit for each successful referral.\n\n"
        "⚠️ <b>Note</b>\n"
        "❱ Even if API fails, the bot remains stable."
    )

def developer_text():
    return (
        "╔━━━━━━━━━━━━━━━━━━━━━━━━━╗\n"
        "║  👨‍💻 <b>DEVELOPER INFO</b> 👨‍💻  ║\n"
        "╚━━━━━━━━━━━━━━━━━━━━━━━━━╝\n\n"
        f"❱ <b>Developer</b> ❱ {DEVELOPER_USERNAME}\n"
        f"❱ <b>Bot</b> ❱ {BOT_NAME}\n\n"
        "⚡ <i>Fast support · Clean system · Secure flow</i>"
    )

# =========================================================
# ADMIN VIEWS
# =========================================================
def safe_edit(chat_id, message_id, text, reply_markup=None):
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except Exception:
        try:
            msg = bot.send_message(chat_id, text, reply_markup=reply_markup)
            set_state(chat_id, panel_message_id=msg.message_id)
        except Exception:
            pass

def show_admin_panel(chat_id, message_id=None):
    text = "👑 <b>Admin Panel</b>\n\nChoose a section below."

    if message_id:
        safe_edit(chat_id, message_id, text, admin_home_kb())
    else:
        msg = bot.send_message(chat_id, text, reply_markup=admin_home_kb())
        set_state(chat_id, panel_message_id=msg.message_id)

def render_stats():
    total_users = fetchone("SELECT COUNT(*) c FROM users")["c"]
    approved = fetchone("SELECT COUNT(*) c FROM users WHERE is_approved = 1 AND is_blocked = 0")["c"]
    pending = fetchone("SELECT COUNT(*) c FROM pending_requests")["c"]
    blocked = fetchone("SELECT COUNT(*) c FROM users WHERE is_blocked = 1")["c"]
    total_lookup = fetchone("SELECT COUNT(*) c FROM lookup_logs WHERE status = 'success'")["c"]
    active_apis = fetchone("SELECT COUNT(*) c FROM api_configs WHERE is_active = 1")["c"]

    return (
        "📊 <b>Bot Stats</b>\n\n"
        f"<b>Total Users:</b> {total_users}\n"
        f"<b>Approved:</b> {approved}\n"
        f"<b>Pending:</b> {pending}\n"
        f"<b>Blocked:</b> {blocked}\n"
        f"<b>Total Lookups:</b> {total_lookup}\n"
        f"<b>Active APIs:</b> {active_apis}"
    )

def show_user_list(chat_id, panel_message_id, page, blocked=False):
    limit = 20
    offset = page * limit

    rows = fetchall(
        "SELECT * FROM users WHERE is_blocked = ? ORDER BY join_date DESC LIMIT ? OFFSET ?",
        (1 if blocked else 0, limit + 1, offset)
    )

    has_next = len(rows) > limit
    rows = rows[:limit]

    title = "🚫 <b>Blocked Users</b>" if blocked else "👥 <b>All Users</b>"

    if not rows:
        safe_edit(chat_id, panel_message_id, f"{title}\n\nNo users found.", pagination_kb("blocked_page" if blocked else "users_page", page, False))
        return

    lines = [title, ""]

    for row in rows:
        name = row["full_name"] or "Unknown"
        uname = f"@{row['username']}" if row["username"] else "@none"
        status = "Approved" if int(row["is_approved"]) == 1 else "Pending"
        lines.append(f"■ {name} | {uname}\n🆔 <code>{row['chat_id']}</code> | Limit: {row['current_limit']} | {status}")

    safe_edit(
        chat_id,
        panel_message_id,
        "\n\n".join(lines),
        pagination_kb("blocked_page" if blocked else "users_page", page, has_next)
    )

def show_pending(chat_id, panel_message_id):
    execute("DELETE FROM pending_requests")

    try:
        bot_id = bot.get_me().id
    except Exception:
        bot_id = 0

    execute("""
        INSERT INTO pending_requests
        (chat_id, full_name, username, requested_at)
        SELECT chat_id, full_name, username, join_date
        FROM users
        WHERE is_approved = 0
        AND is_blocked = 0
        AND chat_id != ?
        AND chat_id NOT IN (SELECT chat_id FROM admins WHERE is_active = 1)
    """, (bot_id,))

    rows = fetchall("SELECT * FROM pending_requests ORDER BY requested_at DESC LIMIT 20")

    if not rows:
        safe_edit(chat_id, panel_message_id, "⏳ <b>Pending Requests</b>\n\nNo pending users.", users_menu_kb())
        return

    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(btn("✅ Approve All Pending", "approve_all_pending", "success"))

    for row in rows:
        uid = int(row["chat_id"])
        name = row["full_name"] or "Unknown"
        uname = f"@{row['username']}" if row["username"] else "@none"
        kb.add(btn(f"{name} | {uname} | {uid}", f"pending_user:{uid}", "primary"))

    kb.add(btn("⬅️ Back", "menu_users", "primary"))

    safe_edit(chat_id, panel_message_id, "⏳ <b>Pending Requests</b>\n\nSelect a user below:", kb)

def show_user_details(chat_id, panel_message_id, target_user_id):
    user = get_user(target_user_id)

    if not user:
        safe_edit(chat_id, panel_message_id, "❌ User not found.", users_menu_kb())
        return

    text = (
        "👤 <b>User Details</b>\n\n"
        f"<b>Name:</b> {user['full_name']}\n"
        f"<b>Username:</b> @{user['username'] or 'none'}\n"
        f"<b>ID:</b> <code>{user['chat_id']}</code>\n"
        f"<b>Approved:</b> {'Yes' if user['is_approved'] else 'No'}\n"
        f"<b>Blocked:</b> {'Yes' if user['is_blocked'] else 'No'}\n"
        f"<b>Current Limit:</b> {user['current_limit']}\n"
        f"<b>Total Lookups:</b> {user['total_lookup']}\n"
        f"<b>Ref Points:</b> {user['ref_points']}\n"
    )

    safe_edit(chat_id, panel_message_id, text, admin_manage_user_kb(target_user_id))

def show_api_list(chat_id, panel_message_id, action=None):
    rows = fetchall("SELECT * FROM api_configs ORDER BY priority ASC, id ASC")

    if not rows:
        safe_edit(chat_id, panel_message_id, "🌐 <b>API List</b>\n\nNo API configured.", api_menu_kb())
        return

    lines = ["🌐 <b>API List</b>", ""]
    kb = InlineKeyboardMarkup(row_width=1)

    for row in rows:
        status = "✅ Active" if int(row["is_active"]) == 1 else "❌ Disabled"
        fallback = " | 🔁 Fallback" if int(row["is_fallback"]) == 1 else ""
        lines.append(f"<b>{row['id']}.</b> {row['name']} — {status}{fallback}\n<code>{row['url_template'][:90]}</code>")

        if action == "delete":
            kb.add(btn(f"🗑 Delete {row['name']}", f"api_delete:{row['id']}", "danger"))
        elif action == "fallback":
            kb.add(btn(f"🔁 Set Fallback: {row['name']}", f"api_fallback:{row['id']}", "success"))
        elif action == "test":
            kb.add(btn(f"🧪 Test: {row['name']}", f"api_test:{row['id']}", "primary"))
        else:
            toggle_text = "🔴 Disable" if int(row["is_active"]) == 1 else "🟢 Enable"
            toggle_style = "danger" if int(row["is_active"]) == 1 else "success"
            kb.add(btn(f"{toggle_text} {row['name']}", f"api_toggle:{row['id']}", toggle_style))

    kb.add(btn("⬅️ Back", "menu_apis", "primary"))

    safe_edit(chat_id, panel_message_id, "\n".join(lines), kb)

def show_api_performance(chat_id, panel_message_id):
    rows = fetchall("SELECT * FROM api_configs ORDER BY priority ASC, id ASC")

    if not rows:
        safe_edit(chat_id, panel_message_id, "📊 <b>API Performance</b>\n\nNo API configured.", api_menu_kb())
        return

    lines = ["📊 <b>API Performance</b>", ""]

    for row in rows:
        lines.append(
            f"■ <b>{row['name']}</b>\n"
            f"Success: {row['success_count']} | Fail: {row['fail_count']}\n"
            f"Last Success: {row['last_success_at'] or '-'}\n"
            f"Last Fail: {row['last_fail_at'] or '-'}\n"
            f"Last Error: <code>{(row['last_error'] or '-')[:80]}</code>\n"
        )

    safe_edit(chat_id, panel_message_id, "\n".join(lines), api_menu_kb())

def show_logs(chat_id, panel_message_id, table, page):
    limit = 20
    offset = page * limit

    maps = {
        "lookup": ("lookup_logs", "📞 <b>Lookup Logs</b>", "view_lookup_logs"),
        "admin": ("admin_logs", "👑 <b>Admin Logs</b>", "view_admin_logs"),
        "broadcast": ("broadcast_logs", "📢 <b>Broadcast Logs</b>", "view_broadcast_logs"),
    }

    tname, title, prefix = maps[table]

    rows = fetchall(f"SELECT * FROM {tname} ORDER BY id DESC LIMIT ? OFFSET ?", (limit + 1, offset))

    has_next = len(rows) > limit
    rows = rows[:limit]

    if not rows:
        safe_edit(chat_id, panel_message_id, f"{title}\n\nNo logs found.", logs_menu_kb())
        return

    lines = [title, ""]

    for row in rows:
        if table == "lookup":
            lines.append(
                f"■ <code>{row['target_id']}</code> | {row['status']} | {row['api_used'] or '-'}\n"
                f"Phone: <code>{row['phone_masked'] or '-'}</code> | Country: {row['country'] or '-'}\n"
                f"User: <code>{row['user_chat_id']}</code>\n"
                f"{row['created_at']}"
            )
        elif table == "admin":
            lines.append(
                f"■ {row['action']} | Admin: <code>{row['admin_id']}</code>\n"
                f"Target: <code>{row['target_user'] or '-'}</code>\n"
                f"{row['created_at']}"
            )
        else:
            lines.append(
                f"■ Admin: <code>{row['admin_id']}</code> | Sent To: {row['total_users']}\n"
                f"<code>{row['message_text'][:70]}</code>"
            )

    safe_edit(chat_id, panel_message_id, "\n\n".join(lines), pagination_kb(prefix, page, has_next, "menu_logs"))

# =========================================================
# ACCESS CONTROL
# =========================================================
def check_user_access(message):
    create_user_if_missing(message)

    user = get_user(message.from_user.id)

    if is_admin(message.from_user.id):
        approve_user(message.from_user.id)
        return True, None, None

    if not is_setting_on("bot_enabled", True):
        return False, maintenance_text(), denied_kb()

    ok, missing = check_force_join(message.from_user.id)

    if not ok:
        return False, "⚠️ To use the bot, join the channels first.", denied_kb(missing)

    if user and int(user["is_blocked"]) == 1:
        return False, blocked_text(), denied_kb()

    if user and int(user["is_approved"]) == 1:
        return True, None, None

    if not is_setting_on("admin_approval_enabled", True):
        approve_user(message.from_user.id)
        return True, None, None

    ensure_pending(message)
    return False, unapproved_text(), denied_kb()

# =========================================================
# LOOKUP PROCESS
# =========================================================
def process_lookup(message, target_id, target_name="Selected User"):
    allowed, deny_text, deny_markup = check_user_access(message)

    if not allowed:
        bot.send_message(message.chat.id, deny_text, reply_markup=deny_markup)
        return

    user = get_user(message.from_user.id)

    if int(user["current_limit"] or 0) < 1:
        bot.send_message(message.chat.id, lookup_fail_text("Not enough lookup limit."), reply_markup=user_reply_kb())
        clear_state(message.chat.id)
        return

    load_msg = bot.send_message(message.chat.id, "⏳ <b>Looking up...</b>")

    progress = [
        "▱▱▱▱▱▱▱▱▱▱ 10%",
        "▰▰▱▱▱▱▱▱▱▱ 20%",
        "▰▰▰▰▱▱▱▱▱▱ 40%",
        "▰▰▰▰▰▱▱▱▱▱ 55%",
        "▰▰▰▰▰▰▰▱▱▱ 75%",
    ]

    for step in progress:
        try:
            bot.edit_message_text(f"⏳ <b>Looking up...</b>\n\n{step}", message.chat.id, load_msg.message_id)
            time.sleep(0.35)
        except Exception:
            pass

    success, api_name, phone_masked, country, extra = call_lookup_api(target_id)

    if success:
        execute(
            "UPDATE users SET current_limit = current_limit - 1, total_lookup = total_lookup + 1 WHERE chat_id = ?",
            (message.from_user.id,)
        )

        updated = get_user(message.from_user.id)

        log_lookup(
            message.from_user.id,
            target_id,
            target_name,
            phone_masked,
            country,
            api_name or "-",
            "success"
        )

        bot.edit_message_text(
            lookup_success_text(
                target_id,
                target_name,
                phone_masked,
                country,
                api_name or "-",
                extra or "",
                int(updated["current_limit"] or 0)
            ),
            message.chat.id,
            load_msg.message_id
        )
    else:
        log_lookup(
            message.from_user.id,
            target_id,
            target_name,
            None,
            None,
            api_name or "-",
            "failed"
        )

        bot.edit_message_text(
            lookup_fail_text(extra or "API failed / data not found."),
            message.chat.id,
            load_msg.message_id
        )

    clear_state(message.chat.id)

# =========================================================
# COMMANDS
# =========================================================
def set_commands():
    bot.set_my_commands([
        BotCommand("start", "Start bot"),
        BotCommand("admin", "Admin panel"),
    ])

@bot.message_handler(commands=["start"])
def start_cmd(message):
    create_user_if_missing(message)

    parts = message.text.split()

    if len(parts) > 1 and parts[1].isdigit():
        referrer_id = int(parts[1])

        if referrer_id != message.from_user.id:
            user = get_user(message.from_user.id)

            if user and not user["referred_by"]:
                execute(
                    "UPDATE users SET referred_by = ? WHERE chat_id = ?",
                    (referrer_id, message.from_user.id)
                )

    allowed, deny_text, deny_markup = check_user_access(message)

    if not allowed:
        bot.send_message(message.chat.id, deny_text, reply_markup=deny_markup)
        return

    user = get_user(message.from_user.id)

    bot.send_message(
        message.chat.id,
        approved_welcome_text(int(user["current_limit"] or 0)),
        reply_markup=user_reply_kb()
    )

@bot.message_handler(commands=["admin"])
def admin_cmd(message):
    if not is_admin(message.from_user.id):
        return

    clear_state(message.chat.id)
    show_admin_panel(message.chat.id)

@bot.message_handler(commands=["pending"])
def pending_cmd(message):
    if not has_permission(message.from_user.id, "can_approve_users"):
        return

    msg = bot.send_message(message.chat.id, "⏳ <b>Pending Requests</b>")
    set_state(message.chat.id, panel_message_id=msg.message_id)
    show_pending(message.chat.id, msg.message_id)

@bot.message_handler(commands=["backupdb"])
def backup_cmd(message):
    if not has_permission(message.from_user.id, "can_backup_restore"):
        return

    ok = backup_db_to_telegram()
    bot.reply_to(message, "✅ Backup sent" if ok else "❌ Backup failed")

@bot.message_handler(commands=["restoredb"])
def restore_cmd(message):
    if not has_permission(message.from_user.id, "can_backup_restore"):
        return

    set_state(message.chat.id, state="restore_db_file")
    bot.reply_to(message, "📥 Send your backup .db file now.")
    
# =========================================================
# USER BUTTONS
# =========================================================
@bot.message_handler(func=lambda m: m.text in [
    "🔍 Lookup by ID",
    "👤 Select User",
    "🟢 Daily Bonus",
    "🔵 Redeem",
    "🔵 Profile",
    "🔴 Help",
    "🔴 Developer",
    "🟣 Refer & Earn",
])
def user_buttons(message):
    allowed, deny_text, deny_markup = check_user_access(message)

    if not allowed:
        bot.send_message(message.chat.id, deny_text, reply_markup=deny_markup)
        return

    user = get_user(message.from_user.id)

    if message.text == "👤 Select User":
        bot.send_message(
            message.chat.id,
            "👤 <b>Use the Select User button from your keyboard.</b>\n\n"
            "If it does not open, update Telegram app.",
            reply_markup=user_reply_kb()
        )
        return

    if message.text == "🔍 Lookup by ID":
        set_state(message.chat.id, state="waiting_target_id")
        bot.send_message(
            message.chat.id,
            "🔍 <b>Send Telegram User ID</b>\n\nExample: <code>8955959693</code>",
            reply_markup=user_reply_kb()
        )
        return

    if message.text == "🟢 Daily Bonus":
        if not is_setting_on("daily_bonus_enabled", True):
            bot.send_message(message.chat.id, "❌ Daily bonus is currently off.", reply_markup=user_reply_kb())
            return

        if can_claim_bonus(user):
            bonus = get_int_setting("daily_bonus", 3)

            execute(
                "UPDATE users SET current_limit = current_limit + ?, last_bonus_at = ? WHERE chat_id = ?",
                (bonus, now_str(), message.chat.id)
            )

            updated = get_user(message.chat.id)

            bot.send_message(
                message.chat.id,
                f"✅ Daily bonus claimed!\n\n+{bonus} limit added.\n💰 Current Limit: <b>{updated['current_limit']}</b>",
                reply_markup=user_reply_kb()
            )
        else:
            next_time = parse_dt(user["last_bonus_at"]) + timedelta(hours=24)
            remaining = next_time - datetime.now(timezone.utc)
            hours = max(0, int(remaining.total_seconds() // 3600))
            minutes = max(0, int((remaining.total_seconds() % 3600) // 60))

            bot.send_message(
                message.chat.id,
                f"⏳ Daily bonus not ready yet.\nTry again in {hours}h {minutes}m.",
                reply_markup=user_reply_kb()
            )

        return

    if message.text == "🔵 Redeem":
        set_state(message.chat.id, state="waiting_redeem_code")
        bot.send_message(message.chat.id, "🎁 <b>Enter redeem code</b>", reply_markup=user_reply_kb())
        return

    if message.text == "🔵 Profile":
        total_refs = fetchone(
            "SELECT COUNT(*) c FROM referrals WHERE referrer_user = ?",
            (message.from_user.id,)
        )["c"]

        text = (
            "👤 <b>Your Profile</b>\n\n"
            f"<b>Name:</b> {user['full_name']}\n"
            f"<b>Chat ID:</b> <code>{user['chat_id']}</code>\n"
            f"<b>Username:</b> @{user['username'] or 'none'}\n"
            f"<b>Current Limit:</b> {user['current_limit']}\n"
            f"<b>Total Lookups:</b> {user['total_lookup']}\n"
            f"<b>Referrals:</b> {total_refs}\n"
            f"<b>Ref Points:</b> {user['ref_points']}\n"
            f"<b>Blocked:</b> {'Yes' if user['is_blocked'] else 'No'}"
        )

        bot.send_message(message.chat.id, text, reply_markup=user_reply_kb())
        return

    if message.text == "🔴 Help":
        bot.send_message(message.chat.id, help_text(), reply_markup=user_reply_kb())
        return

    if message.text == "🔴 Developer":
        bot.send_message(message.chat.id, developer_text(), reply_markup=user_reply_kb())
        return

    if message.text == "🟣 Refer & Earn":
        me = bot.get_me()

        total_refs = fetchone(
            "SELECT COUNT(*) c FROM referrals WHERE referrer_user = ?",
            (message.from_user.id,)
        )["c"]

        ref_link = f"https://t.me/{me.username}?start={message.from_user.id}"

        text = (
            "🟣 <b>Refer & Earn</b>\n\n"
            f"🔗 <b>Your Referral Link:</b>\n<code>{ref_link}</code>\n\n"
            "🎁 <b>Reward:</b> 2 limit per successful referral\n\n"
            f"✅ <b>Successful Referrals:</b> {total_refs}\n"
            f"⭐ <b>Total Referral Points:</b> {int(user['ref_points'] or 0)}\n\n"
            "📌 <b>Rules:</b>\n"
            "• User must join using your referral link\n"
            "• Same user counts only once"
        )

        bot.send_message(message.chat.id, text, reply_markup=user_reply_kb())
        return

# =========================================================
# SELECT USER HANDLERS
# =========================================================
@bot.message_handler(content_types=["users_shared"])
def users_shared_handler(message):
    try:
        users = getattr(message.users_shared, "users", []) or []

        if not users:
            bot.send_message(message.chat.id, lookup_fail_text("No user selected."), reply_markup=user_reply_kb())
            return

        selected = users[0]
        target_id = str(selected.user_id)
        target_name = getattr(selected, "first_name", None) or getattr(selected, "username", None) or "Selected User"

        threading.Thread(
            target=process_lookup,
            args=(message, target_id, target_name),
            daemon=True
        ).start()

    except Exception as e:
        bot.send_message(message.chat.id, lookup_fail_text(str(e)), reply_markup=user_reply_kb())

@bot.message_handler(content_types=["user_shared"])
def user_shared_handler(message):
    try:
        target_id = str(message.user_shared.user_id)

        threading.Thread(
            target=process_lookup,
            args=(message, target_id, "Selected User"),
            daemon=True
        ).start()

    except Exception as e:
        bot.send_message(message.chat.id, lookup_fail_text(str(e)), reply_markup=user_reply_kb())
        
@bot.message_handler(content_types=["document"])
def restore_document_handler(message):
    state_row = get_state(message.chat.id)
    state = state_row["state"] if state_row and state_row["state"] else None

    if state != "restore_db_file":
        return

    if not has_permission(message.from_user.id, "can_backup_restore"):
        clear_state(message.chat.id)
        return

    try:
        file_name = message.document.file_name or ""

        if not file_name.endswith(".db"):
            bot.reply_to(message, "❌ Please send a .db backup file.")
            return

        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)

        backup_before_restore = DB_PATH + ".before_restore"

        if os.path.exists(DB_PATH):
            with open(DB_PATH, "rb") as old_db:
                old_data = old_db.read()

            with open(backup_before_restore, "wb") as old_backup:
                old_backup.write(old_data)

        global CONN

        try:
            CONN.close()
        except Exception:
            pass

        with open(DB_PATH, "wb") as new_db:
            new_db.write(downloaded)

        CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
        CONN.row_factory = sqlite3.Row

        clear_state(message.chat.id)

        bot.reply_to(
            message,
            "✅ Database restored successfully.\n\n♻️ Restart bot recommended."
        )

    except Exception as e:
        bot.reply_to(message, f"❌ Restore failed:\n<code>{str(e)}</code>")

# =========================================================
# GENERAL TEXT / ADMIN STATES
# =========================================================
@bot.message_handler(func=lambda m: True, content_types=["text", "photo", "video", "document", "audio", "sticker"])
def general_text_handler(message):
    state_row = get_state(message.chat.id)
    state = state_row["state"] if state_row and state_row["state"] else None

    if state == "waiting_target_id":
        target_id = (message.text or "").strip()

        if not target_id.isdigit():
            bot.send_message(
                message.chat.id,
                lookup_fail_text("Invalid Telegram ID. Send numeric ID only."),
                reply_markup=user_reply_kb()
            )
            clear_state(message.chat.id)
            return

        user_row = fetchone(
            "SELECT full_name, username FROM users WHERE chat_id = ?",
            (int(target_id),)
        )

        if user_row:
            if user_row["full_name"]:
                target_name = user_row["full_name"]
            elif user_row["username"]:
                target_name = f"@{user_row['username']}"
            else:
                target_name = "Unknown"
        else:
            target_name = "Unknown"

        threading.Thread(
            target=process_lookup,
            args=(message, target_id, target_name),
            daemon=True
        ).start()
        return

    if state == "waiting_redeem_code":
        code = (message.text or "").strip().upper()
        row = fetchone("SELECT * FROM redeem_codes WHERE code = ? AND is_active = 1", (code,))

        if not row:
            bot.send_message(message.chat.id, "❌ Invalid redeem code.", reply_markup=user_reply_kb())
            clear_state(message.chat.id)
            return

        if int(row["used_count"]) >= int(row["max_uses"]):
            bot.send_message(message.chat.id, "❌ This redeem code has reached usage limit.", reply_markup=user_reply_kb())
            clear_state(message.chat.id)
            return

        expires_at = parse_dt(row["expires_at"])
        if expires_at and datetime.now(timezone.utc) > expires_at:
            bot.send_message(message.chat.id, "❌ This redeem code has expired.", reply_markup=user_reply_kb())
            clear_state(message.chat.id)
            return

        used = fetchone(
            "SELECT 1 FROM redeem_uses WHERE code = ? AND user_chat_id = ?",
            (code, message.chat.id)
        )

        if used:
            bot.send_message(message.chat.id, "❌ You already used this redeem code.", reply_markup=user_reply_kb())
            clear_state(message.chat.id)
            return

        execute(
            "UPDATE users SET current_limit = current_limit + ? WHERE chat_id = ?",
            (row["limit_value"], message.chat.id)
        )
        execute("UPDATE redeem_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
        execute(
            "INSERT INTO redeem_uses (code, user_chat_id, used_at) VALUES (?, ?, ?)",
            (code, message.chat.id, now_str())
        )

        updated = get_user(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Redeem successful!\n\n+{row['limit_value']} limit added.\n💰 Current Limit: <b>{updated['current_limit']}</b>",
            reply_markup=user_reply_kb()
        )
        clear_state(message.chat.id)
        return

    if not state:
        return

    if not is_admin(message.from_user.id):
        clear_state(message.chat.id)
        return
    if state == "set_daily_bonus_value":
        value = (message.text or "").strip()

        if not value.isdigit():
            bot.send_message(message.chat.id, "❌ Invalid number. Send only digits.")
            return

        set_setting("daily_bonus", value)
        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Daily bonus updated to <b>{value}</b>",
            reply_markup=back_only_kb("menu_dev")
        )
        return


    if state == "set_initial_limit_value":
        value = (message.text or "").strip()

        if not value.isdigit():
            bot.send_message(message.chat.id, "❌ Invalid number. Send only digits.")
            return

        set_setting("initial_limit", value)
        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Initial limit updated to <b>{value}</b>",
            reply_markup=back_only_kb("menu_dev")
        )
        return


    if state == "set_log_channel_id":
        value = (message.text or "").strip()

        if not value.lstrip("-").isdigit():
            bot.send_message(message.chat.id, "❌ Invalid chat ID.")
            return

        set_setting("log_chat_id", value)
        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Log channel updated:\n<code>{value}</code>",
            reply_markup=back_only_kb("menu_dev")
        )
        return
    panel_message_id = state_row["panel_message_id"] if state_row else None

    if state == "admin_find_user_input":
        q = (message.text or "").strip()
        row = None

        if q.lstrip("-").isdigit():
            row = fetchone("SELECT * FROM users WHERE chat_id = ?", (int(q),))

        if not row:
            row = fetchone("SELECT * FROM users WHERE lower(username) = lower(?)", (q.lstrip("@"),))

        if not row:
            row = fetchone(
                "SELECT * FROM users WHERE lower(full_name) LIKE lower(?) ORDER BY join_date DESC",
                (f"%{q}%",)
            )

        if not row:
            bot.send_message(message.chat.id, "❌ User not found.", reply_markup=back_only_kb("menu_users"))
            return

        clear_state(message.chat.id)
        show_user_details(message.chat.id, panel_message_id or message.message_id, int(row["chat_id"]))
        return

    if state in ["admin_add_limit_userid", "admin_remove_limit_userid"]:
        if not (message.text or "").strip().lstrip("-").isdigit():
            bot.send_message(message.chat.id, "❌ Invalid user ID.", reply_markup=back_only_kb("menu_limits"))
            return

        next_state = "admin_add_limit_amount" if state == "admin_add_limit_userid" else "admin_remove_limit_amount"

        set_state(
            message.chat.id,
            state=next_state,
            temp_user_id=int(message.text.strip()),
            panel_message_id=panel_message_id
        )

        bot.send_message(message.chat.id, "Enter amount:", reply_markup=back_only_kb("menu_limits"))
        return

    if state in ["admin_add_limit_amount", "admin_remove_limit_amount"]:
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid amount.", reply_markup=back_only_kb("menu_limits"))
            return

        target_id = int(get_state(message.chat.id)["temp_user_id"])
        amount = int(message.text.strip())

        if state == "admin_add_limit_amount":
            add_limit(target_id, amount)
            log_admin(message.from_user.id, "add_limit", target_id, str(amount))
            msg = f"✅ Added {amount} limit to <code>{target_id}</code>"
        else:
            remove_limit(target_id, amount)
            log_admin(message.from_user.id, "remove_limit", target_id, str(amount))
            msg = f"✅ Removed {amount} limit from <code>{target_id}</code>"

        clear_state(message.chat.id)
        bot.send_message(message.chat.id, msg, reply_markup=back_only_kb("menu_limits"))
        return

    if state == "admin_create_redeem_code":
        set_state(
            message.chat.id,
            state="admin_create_redeem_limit",
            temp_code=(message.text or "").strip().upper()
        )
        bot.send_message(message.chat.id, "Enter limit value:", reply_markup=back_only_kb("menu_limits"))
        return

    if state == "admin_create_redeem_limit":
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid limit value.", reply_markup=back_only_kb("menu_limits"))
            return

        set_state(
            message.chat.id,
            state="admin_create_redeem_uses",
            temp_limit=int(message.text.strip())
        )
        bot.send_message(message.chat.id, "Enter max uses:", reply_markup=back_only_kb("menu_limits"))
        return

    if state == "admin_create_redeem_uses":
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid uses.", reply_markup=back_only_kb("menu_limits"))
            return

        set_state(
            message.chat.id,
            state="admin_create_redeem_expiry",
            temp_uses=int(message.text.strip())
        )
        bot.send_message(message.chat.id, "Enter expiry hours from now (0 for no expiry):", reply_markup=back_only_kb("menu_limits"))
        return

    if state == "admin_create_redeem_expiry":
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid expiry.", reply_markup=back_only_kb("menu_limits"))
            return

        s = get_state(message.chat.id)
        hours = int(message.text.strip())
        expires_at = None if hours == 0 else (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")

        execute(
            """
            INSERT OR REPLACE INTO redeem_codes
            (code, limit_value, max_uses, used_count, expires_at, is_active, created_by, created_at)
            VALUES (?, ?, ?, 0, ?, 1, ?, ?)
            """,
            (
                s["temp_code"],
                int(s["temp_limit"]),
                int(s["temp_uses"]),
                expires_at,
                message.from_user.id,
                now_str()
            )
        )

        log_admin(
            message.from_user.id,
            "create_redeem",
            None,
            f"{s['temp_code']}|{s['temp_limit']}|{s['temp_uses']}"
        )

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Redeem code created: <code>{s['temp_code']}</code>",
            reply_markup=back_only_kb("menu_limits")
        )
        return

    if state == "admin_delete_redeem_code":
        code = (message.text or "").strip().upper()

        execute("DELETE FROM redeem_codes WHERE code = ?", (code,))
        log_admin(message.from_user.id, "delete_redeem", None, code)

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Redeem deleted: <code>{code}</code>",
            reply_markup=back_only_kb("menu_limits")
        )
        return

    if state == "admin_broadcast_message":
        text = message.text or message.caption or "[MEDIA]"
        users = fetchall("SELECT chat_id FROM users WHERE is_approved = 1 AND is_blocked = 0")

        count = 0

        for u in users:
            try:
                bot.copy_message(u["chat_id"], message.chat.id, message.message_id)
                count += 1
            except Exception:
                pass

        execute(
            "INSERT INTO broadcast_logs (admin_id, message_text, total_users, created_at) VALUES (?, ?, ?, ?)",
            (message.from_user.id, text, count, now_str())
        )

        log_admin(message.from_user.id, "broadcast", None, f"sent_to={count}")

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Broadcast sent to {count} users.",
            reply_markup=back_only_kb("admin_home")
        )
        return

    if state == "api_add_name":
        set_state(
            message.chat.id,
            state="api_add_url",
            temp_text=(message.text or "").strip()
        )
        bot.send_message(
            message.chat.id,
            "Send API URL template.\n\nUse <code>{user_id}</code> placeholder.",
            reply_markup=back_only_kb("menu_apis")
        )
        return

    if state == "api_add_url":
        name = get_state(message.chat.id)["temp_text"]
        url = (message.text or "").strip()

        if "{user_id}" not in url:
            bot.send_message(
                message.chat.id,
                "❌ URL must contain <code>{user_id}</code> placeholder.",
                reply_markup=back_only_kb("menu_apis")
            )
            return

        execute(
            """
            INSERT INTO api_configs
            (name, url_template, api_key, is_active, is_fallback, priority, created_at)
            VALUES (?, ?, '', 1, 0, 100, ?)
            """,
            (name, url, now_str())
        )

        log_admin(message.from_user.id, "add_api", None, name)

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ API added: <b>{name}</b>",
            reply_markup=back_only_kb("menu_apis")
        )
        return

    if state == "api_test_id":
        uid = (message.text or "").strip()

        if not uid.lstrip("-").isdigit():
            bot.send_message(message.chat.id, "❌ Send numeric ID.", reply_markup=back_only_kb("menu_apis"))
            return

        success, api_name, phone_masked, country, extra = call_lookup_api(uid)

        text = (
            f"{'✅' if success else '❌'} <b>API Test</b>\n\n"
            f"<b>API:</b> {api_name or '-'}\n"
            f"<b>Masked Phone:</b> <code>{phone_masked or '-'}</code>\n"
            f"<b>Country:</b> {country or '-'}\n"
        )

        if extra:
            text += f"\n<code>{extra[:800]}</code>"

        bot.send_message(message.chat.id, text, reply_markup=back_only_kb("menu_apis"))
        clear_state(message.chat.id)
        return

    if state == "force_add_channel_username":
        username = (message.text or "").strip()

        if not username.startswith("@"):
            bot.send_message(
                message.chat.id,
                "❌ Channel username must start with @",
                reply_markup=back_only_kb("dev_force_join")
            )
            return

        set_state(message.chat.id, state="force_add_channel_link", temp_text=username)

        bot.send_message(
            message.chat.id,
            "Send channel invite/public link:",
            reply_markup=back_only_kb("dev_force_join")
        )
        return

    if state == "force_add_channel_link":
        username = get_state(message.chat.id)["temp_text"]
        link = (message.text or "").strip()

        execute(
            "INSERT INTO force_channels (channel_username, channel_link, is_active, created_at) VALUES (?, ?, 1, ?)",
            (username, link, now_str())
        )

        log_admin(message.from_user.id, "add_force_channel", None, username)

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Channel added: {username}",
            reply_markup=back_only_kb("dev_force_join")
        )
        return

    if state == "force_remove_channel_id":
        if not (message.text or "").strip().isdigit():
            bot.send_message(
                message.chat.id,
                "❌ Send numeric channel ID from list.",
                reply_markup=back_only_kb("dev_force_join")
            )
            return

        cid = int(message.text.strip())
        execute("DELETE FROM force_channels WHERE id = ?", (cid,))
        log_admin(message.from_user.id, "remove_force_channel", None, str(cid))

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Removed channel ID {cid}",
            reply_markup=back_only_kb("dev_force_join")
        )
        return

    if state in ["set_initial_limit", "set_daily_bonus"]:
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid number.", reply_markup=back_only_kb("menu_dev"))
            return

        key = "initial_limit" if state == "set_initial_limit" else "daily_bonus"
        set_setting(key, message.text.strip())

        log_admin(message.from_user.id, key, None, message.text.strip())

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            "✅ Setting updated.",
            reply_markup=back_only_kb("menu_dev")
        )
        return

    if state == "set_log_channel":
        val = (message.text or "").strip()

        if not val.lstrip("-").isdigit():
            bot.send_message(message.chat.id, "❌ Invalid chat ID.", reply_markup=back_only_kb("menu_dev"))
            return

        set_setting("log_chat_id", val)
        log_admin(message.from_user.id, "set_log_channel", None, val)

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            "✅ Log channel updated.",
            reply_markup=back_only_kb("menu_dev")
        )
        return

    if state == "admin_add_admin_id":
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid admin ID.", reply_markup=back_only_kb("dev_admins"))
            return

        target_id = int(message.text.strip())

        execute(
            """
            INSERT OR IGNORE INTO admins
            (chat_id, full_name, username, is_active, is_full_access, created_at)
            VALUES (?, ?, ?, 1, 0, ?)
            """,
            (target_id, "Admin", "", now_str())
        )

        execute("INSERT OR IGNORE INTO admin_permissions (admin_chat_id) VALUES (?)", (target_id,))

        log_admin(message.from_user.id, "add_admin", target_id)

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Admin added: <code>{target_id}</code>",
            reply_markup=back_only_kb("dev_admins")
        )
        return

    if state == "admin_remove_admin_id":
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid admin ID.", reply_markup=back_only_kb("dev_admins"))
            return

        target_id = int(message.text.strip())

        if target_id == DEVELOPER_ID:
            bot.send_message(message.chat.id, "❌ Developer cannot be removed.", reply_markup=back_only_kb("dev_admins"))
            return

        execute("DELETE FROM admins WHERE chat_id = ?", (target_id,))
        execute("DELETE FROM admin_permissions WHERE admin_chat_id = ?", (target_id,))

        log_admin(message.from_user.id, "remove_admin", target_id)

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Admin removed: <code>{target_id}</code>",
            reply_markup=back_only_kb("dev_admins")
        )
        return

    if state == "admin_set_full_id":
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid admin ID.", reply_markup=back_only_kb("dev_admins"))
            return

        target_id = int(message.text.strip())

        execute("UPDATE admins SET is_full_access = 1 WHERE chat_id = ?", (target_id,))

        execute("""
            INSERT OR REPLACE INTO admin_permissions
            (
                admin_chat_id,
                can_approve_users,
                can_manage_users,
                can_manage_limits,
                can_manage_redeem,
                can_broadcast,
                can_view_logs,
                can_manage_apis,
                can_manage_settings,
                can_manage_admins,
                can_backup_restore
            )
            VALUES (?,1,1,1,1,1,1,1,1,1,1)
        """, (target_id,))

        log_admin(message.from_user.id, "grant_full_access", target_id)

        clear_state(message.chat.id)

        bot.send_message(
            message.chat.id,
            f"✅ Full access granted: <code>{target_id}</code>",
            reply_markup=back_only_kb("dev_admins")
        )
        return

    if state == "adminmgr_add_id":
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid admin ID.", reply_markup=back_only_kb("dev_admins"))
            return

        new_admin = int(message.text.strip())

        execute("""
            INSERT OR REPLACE INTO admins
            (chat_id, full_name, username, is_active, is_full_access, created_at)
            VALUES (?, 'Admin', '', 1, 1, ?)
            """, (new_admin, now_str()))

        execute("""
            INSERT OR REPLACE INTO admin_permissions
            VALUES (?,1,1,1,1,1,1,1,1,1,1)
        """, (new_admin,))

        log_admin(message.from_user.id, "add_admin", new_admin)
        clear_state(message.chat.id)

        bot.send_message(message.chat.id, f"✅ Admin added: <code>{new_admin}</code>", reply_markup=back_only_kb("dev_admins"))
        return


    if state == "adminmgr_remove_id":
        if not (message.text or "").strip().isdigit():
            bot.send_message(message.chat.id, "❌ Invalid admin ID.", reply_markup=back_only_kb("dev_admins"))
            return

        admin_id = int(message.text.strip())

        if admin_id == DEVELOPER_ID:
            bot.send_message(message.chat.id, "❌ You Can't Remove Bot Owner 🤬", reply_markup=back_only_kb("dev_admins"))
            return

        execute("UPDATE admins SET is_active = 0 WHERE chat_id = ?", (admin_id,))
        log_admin(message.from_user.id, "remove_admin", admin_id)
        clear_state(message.chat.id)

        bot.send_message(message.chat.id, f"✅ Admin removed: <code>{admin_id}</code>", reply_markup=back_only_kb("dev_admins"))
        return
# =========================================================
# CALLBACKS
# =========================================================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    chat_id = call.message.chat.id
    panel_message_id = call.message.message_id

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    set_state(chat_id, panel_message_id=panel_message_id)

    if data == "force_join_recheck":
        ok, missing = check_force_join(call.from_user.id)
        if not ok:
            safe_edit(chat_id, panel_message_id, "⚠️ Join all channels first.", denied_kb(missing))
            return

        try:
            bot.delete_message(chat_id, panel_message_id)
        except Exception:
            pass

        if not is_setting_on("admin_approval_enabled", True):
            approve_user(call.from_user.id)
            user = get_user(call.from_user.id)
            bot.send_message(chat_id, approved_welcome_text(int(user["current_limit"] or 0)), reply_markup=user_reply_kb())
            return

        ensure_pending_user(call.from_user.id, call.from_user.full_name or "Unknown", call.from_user.username or "")
        bot.send_message(chat_id, unapproved_text(), reply_markup=denied_kb())
        return

    if not is_admin(call.from_user.id):
        return

    # MAIN MENU
    if data == "admin_home":
        show_admin_panel(chat_id, panel_message_id)
        return

    if data == "menu_users":
        safe_edit(chat_id, panel_message_id, "👥 <b>Users Menu</b>", users_menu_kb())
        return

    if data == "menu_limits":
        safe_edit(chat_id, panel_message_id, "🎁 <b>Limits & Redeem</b>", limits_menu_kb())
        return

    if data == "menu_apis":
        safe_edit(chat_id, panel_message_id, "🌐 <b>API Manager</b>", api_menu_kb())
        return

    if data == "menu_logs":
        safe_edit(chat_id, panel_message_id, "📜 <b>Logs Menu</b>", logs_menu_kb())
        return

    if data == "menu_stats":
        safe_edit(chat_id, panel_message_id, render_stats(), admin_home_kb())
        return

    if data == "menu_dev":
        text = (
            "⚙️ <b>Developer Settings</b>\n\n"
            f"<b>Bot Enabled:</b> {'Yes' if is_setting_on('bot_enabled', True) else 'No'}\n"
            f"<b>Approval:</b> {'On' if is_setting_on('admin_approval_enabled', True) else 'Off'}\n"
            f"<b>Daily Bonus:</b> {get_int_setting('daily_bonus', 3)}\n"
            f"<b>Initial Limit:</b> {get_int_setting('initial_limit', 5)}\n"
            f"<b>Force Join:</b> {'On' if is_setting_on('force_join_enabled', False) else 'Off'}"
        )
        safe_edit(chat_id, panel_message_id, text, dev_menu_kb())
        return

    # USERS
    if data == "approve_all_pending":
        rows = fetchall("SELECT chat_id FROM pending_requests")
        count = 0
        for r in rows:
            if approve_user(int(r["chat_id"])):
                count += 1
        log_admin(call.from_user.id, "approve_all_pending", None, f"count={count}")
        show_pending(chat_id, panel_message_id)
        return

    if data.startswith("pending_user:"):
        show_user_details(chat_id, panel_message_id, int(data.split(":")[1]))
        return

    if data.startswith("users_page:"):
        show_user_list(chat_id, panel_message_id, int(data.split(":")[1]), False)
        return

    if data.startswith("blocked_page:"):
        show_user_list(chat_id, panel_message_id, int(data.split(":")[1]), True)
        return

    if data == "admin_pending":
        show_pending(chat_id, panel_message_id)
        return

    if data == "admin_find_user":
        set_state(chat_id, state="admin_find_user_input", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "🔎 Send user ID / username / name:", back_only_kb("menu_users"))
        return

    if data.startswith("manual_approve:"):
        target = int(data.split(":")[1])
        approve_user(target)
        log_admin(call.from_user.id, "approve_user", target)
        show_user_details(chat_id, panel_message_id, target)
        return

    if data.startswith("manual_reject:"):
        target = int(data.split(":")[1])
        reject_user(target)
        log_admin(call.from_user.id, "reject_user", target)
        safe_edit(chat_id, panel_message_id, "✅ User rejected.", users_menu_kb())
        return

    if data.startswith("manual_ban:"):
        target = int(data.split(":")[1])
        block_user(target)
        log_admin(call.from_user.id, "ban_user", target)
        show_user_details(chat_id, panel_message_id, target)
        return

    if data.startswith("manual_unban:"):
        target = int(data.split(":")[1])
        unblock_user(target)
        log_admin(call.from_user.id, "unban_user", target)
        show_user_details(chat_id, panel_message_id, target)
        return

    if data.startswith("manual_user_details:"):
        show_user_details(chat_id, panel_message_id, int(data.split(":")[1]))
        return
    
    if data == "dev_bonus":
        text = (
            "🎁 <b>Bonus Settings</b>\n\n"
            f"Current Daily Bonus: {get_int_setting('daily_bonus', 3)}\n"
            f"Initial Limit: {get_int_setting('initial_limit', 5)}\n\n"
            "Choose what to edit:"
        )

        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(btn("✏️ Set Daily Bonus", "set_daily_bonus", "primary"))
        kb.add(btn("✏️ Set Initial Limit", "set_initial_limit", "primary"))
        kb.add(btn("⬅️ Back", "menu_dev", "primary"))

        safe_edit(chat_id, panel_message_id, text, kb)
        return


    if data == "set_daily_bonus":
        set_state(chat_id, state="set_daily_bonus_value", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "Enter new daily bonus:", back_only_kb("dev_bonus"))
        return


    if data == "set_initial_limit":
        set_state(chat_id, state="set_initial_limit_value", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "Enter new initial limit:", back_only_kb("dev_bonus"))
        return


    if data == "dev_log_settings":
        current = get_int_setting("log_chat_id", DEFAULT_LOG_CHAT_ID)

        text = (
            "📢 <b>Log Channel Settings</b>\n\n"
            f"Current Log Chat ID:\n<code>{current}</code>\n\n"
            "Send new chat ID:"
        )

        set_state(chat_id, state="set_log_channel_id", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, text, back_only_kb("menu_dev"))
        return
        
    if data.startswith("manual_add_limit:"):
        target = int(data.split(":")[1])
        set_state(chat_id, state="admin_add_limit_amount", temp_user_id=target, panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "Enter amount to add:", back_only_kb("menu_users"))
        return

    if data.startswith("manual_remove_limit:"):
        target = int(data.split(":")[1])
        set_state(chat_id, state="admin_remove_limit_amount", temp_user_id=target, panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "Enter amount to remove:", back_only_kb("menu_users"))
        return

    # LIMITS / REDEEM
    if data == "admin_add_limit":
        set_state(chat_id, state="admin_add_limit_userid", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "➕ Send user ID:", back_only_kb("menu_limits"))
        return

    if data == "admin_remove_limit":
        set_state(chat_id, state="admin_remove_limit_userid", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "➖ Send user ID:", back_only_kb("menu_limits"))
        return

    if data == "admin_create_redeem":
        set_state(chat_id, state="admin_create_redeem_code", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "🎟 Enter redeem code:", back_only_kb("menu_limits"))
        return

    if data == "admin_delete_redeem":
        set_state(chat_id, state="admin_delete_redeem_code", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "🗑 Enter redeem code to delete:", back_only_kb("menu_limits"))
        return

    if data == "admin_redeem_list":
        rows = fetchall("SELECT * FROM redeem_codes ORDER BY created_at DESC LIMIT 20")
        text = "🎁 <b>Redeem Codes</b>\n\n"

        if not rows:
            text += "No redeem code found."
        else:
            for r in rows:
                text += f"■ <code>{r['code']}</code> | Limit: {r['limit_value']} | Used: {r['used_count']}/{r['max_uses']}\n"

        safe_edit(chat_id, panel_message_id, text, limits_menu_kb())
        return

    # API
    if data == "api_add":
        set_state(chat_id, state="api_add_name", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "➕ Send API name:", back_only_kb("menu_apis"))
        return

    if data == "api_list":
        show_api_list(chat_id, panel_message_id)
        return

    if data == "api_set_fallback":
        show_api_list(chat_id, panel_message_id, "fallback")
        return

    if data == "api_test_select":
        set_state(chat_id, state="api_test_id", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "🧪 Send test user ID:", back_only_kb("menu_apis"))
        return

    if data == "api_performance":
        show_api_performance(chat_id, panel_message_id)
        return

    if data == "api_delete_select":
        show_api_list(chat_id, panel_message_id, "delete")
        return

    if data.startswith("api_toggle:"):
        api_id = int(data.split(":")[1])
        row = fetchone("SELECT is_active FROM api_configs WHERE id = ?", (api_id,))
        if row:
            new_status = 0 if int(row["is_active"]) == 1 else 1
            execute("UPDATE api_configs SET is_active = ? WHERE id = ?", (new_status, api_id))
        show_api_list(chat_id, panel_message_id)
        return

    if data.startswith("api_delete:"):
        api_id = int(data.split(":")[1])
        execute("DELETE FROM api_configs WHERE id = ?", (api_id,))
        log_admin(call.from_user.id, "delete_api", None, str(api_id))
        show_api_list(chat_id, panel_message_id, "delete")
        return

    if data.startswith("api_fallback:"):
        api_id = int(data.split(":")[1])
        execute("UPDATE api_configs SET is_fallback = 0")
        execute("UPDATE api_configs SET is_fallback = 1 WHERE id = ?", (api_id,))
        log_admin(call.from_user.id, "set_api_fallback", None, str(api_id))
        show_api_list(chat_id, panel_message_id, "fallback")
        return

    if data.startswith("api_test:"):
        set_state(chat_id, state="api_test_id", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "🧪 Send test user ID:", back_only_kb("menu_apis"))
        return

    # LOGS
    if data.startswith("view_lookup_logs:"):
        show_logs(chat_id, panel_message_id, "lookup", int(data.split(":")[1]))
        return

    if data.startswith("view_admin_logs:"):
        show_logs(chat_id, panel_message_id, "admin", int(data.split(":")[1]))
        return

    if data.startswith("view_broadcast_logs:"):
        show_logs(chat_id, panel_message_id, "broadcast", int(data.split(":")[1]))
        return

    if data == "clean_old_logs":
        execute("DELETE FROM lookup_logs WHERE id NOT IN (SELECT id FROM lookup_logs ORDER BY id DESC LIMIT 200)")
        execute("DELETE FROM admin_logs WHERE id NOT IN (SELECT id FROM admin_logs ORDER BY id DESC LIMIT 200)")
        execute("DELETE FROM broadcast_logs WHERE id NOT IN (SELECT id FROM broadcast_logs ORDER BY id DESC LIMIT 100)")
        log_admin(call.from_user.id, "clean_old_logs")
        safe_edit(chat_id, panel_message_id, "✅ Old logs cleaned.", logs_menu_kb())
        return

    # DEV SETTINGS
    if data == "dev_bot_toggle":
        new_value = "0" if is_setting_on("bot_enabled", True) else "1"
        set_setting("bot_enabled", new_value)
        safe_edit(chat_id, panel_message_id, "✅ Bot setting updated.", dev_menu_kb())
        return

    if data == "toggle_admin_approval":
        new_value = "0" if is_setting_on("admin_approval_enabled", True) else "1"
        set_setting("admin_approval_enabled", new_value)
        safe_edit(chat_id, panel_message_id, "✅ Approval setting updated.", dev_menu_kb())
        return

    if data == "dev_backup_settings":
        current = get_int_setting("backup_interval_hours", 1)

        text = (
            "💾 <b>Backup Settings</b>\n\n"
            f"Current: <b>{current} hour(s)</b>\n\n"
            "Choose option:"
        )

        safe_edit(chat_id, panel_message_id, text, backup_settings_kb())
        return


    if data == "backup_interval_menu":
        current = get_int_setting("backup_interval_hours", 1)

        text = (
            "⏱ <b>Select Backup Interval</b>\n\n"
            f"Current: <b>{current} hour(s)</b>"
        )

        safe_edit(chat_id, panel_message_id, text, backup_interval_kb())
        return


    if data.startswith("backup_interval:"):
        hours = int(data.split(":")[1])

        set_setting("backup_interval_hours", hours)

        safe_edit(
            chat_id,
            panel_message_id,
            f"✅ Interval set to <b>{hours} hour(s)</b>",
            backup_settings_kb()
        )
        return


    if data == "backup_now":
        ok = backup_db_to_telegram()

        safe_edit(
            chat_id,
            panel_message_id,
            "✅ Backup sent." if ok else "❌ Backup failed.",
            backup_settings_kb()
        )
        return

    if data == "dev_force_join":
        text = "📢 <b>Force Join Settings</b>\n\n"
        text += f"Status: {'ON' if is_setting_on('force_join_enabled', False) else 'OFF'}\n\n"
        rows = get_active_channels()
        if rows:
            for r in rows:
                text += f"{r['id']}. {r['channel_username']}\n"
        else:
            text += "No channel added."

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(btn("ON/OFF", "force_toggle", "success"))
        kb.add(btn("➕ Add Channel", "force_add_channel", "primary"))
        kb.add(btn("🗑 Remove Channel", "force_remove_channel", "danger"))
        kb.add(btn("⬅️ Back", "menu_dev", "primary"))
        safe_edit(chat_id, panel_message_id, text, kb)
        return

    if data == "force_toggle":
        new_value = "0" if is_setting_on("force_join_enabled", False) else "1"
        set_setting("force_join_enabled", new_value)
        safe_edit(chat_id, panel_message_id, "✅ Force join updated.", dev_menu_kb())
        return

    if data == "force_add_channel":
        set_state(chat_id, state="force_add_channel_username", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "Send channel username like @channel:", back_only_kb("dev_force_join"))
        return

    if data == "force_remove_channel":
        set_state(chat_id, state="force_remove_channel_id", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "Send channel ID from list:", back_only_kb("dev_force_join"))
        return

    if data == "dev_log_settings":
        safe_edit(chat_id, panel_message_id, "📢 Log settings button not added yet.", dev_menu_kb())
        return

    if data == "backup_now":
        ok = backup_db_to_telegram()
        safe_edit(chat_id, panel_message_id, "✅ Backup sent." if ok else "❌ Backup failed.", dev_menu_kb())
        return

    if data == "dev_admins":
        rows = fetchall("SELECT * FROM admins WHERE is_active = 1 ORDER BY created_at DESC")

        text = "👑 <b>Admin Manager</b>\n\n"

        if not rows:
            text += "No admin found."
        else:
            for r in rows:
                access = "Full" if int(r["is_full_access"]) == 1 else "Limited"
                text += (
                    f"■ <b>{r['full_name']}</b>\n"
                    f"Username: @{r['username'] or 'none'}\n"
                    f"ID: <code>{r['chat_id']}</code>\n"
                    f"Access: {access}\n\n"
                )

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(btn("➕ Add Admin", "adminmgr_add", "success"))
        kb.add(btn("🗑 Remove Admin", "adminmgr_remove", "danger"))
        kb.add(btn("⬅️ Back", "menu_dev", "primary"))

        safe_edit(chat_id, panel_message_id, text, kb)
        return
    if data == "adminmgr_add":
        set_state(chat_id, state="adminmgr_add_id", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "➕ Send new admin Telegram ID:", back_only_kb("dev_admins"))
        return

    if data == "adminmgr_remove":
        set_state(chat_id, state="adminmgr_remove_id", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "🗑 Send admin Telegram ID to remove:", back_only_kb("dev_admins"))
        return
    
    if data == "menu_broadcast":
        set_state(chat_id, state="admin_broadcast_message", panel_message_id=panel_message_id)
        safe_edit(chat_id, panel_message_id, "📢 Send message to broadcast:", back_only_kb("admin_home"))
        return

    if data.startswith("dev_") or data.startswith("toggle_") or data in [
        "set_initial_limit",
        "set_daily_bonus",
        "set_log_channel",
        "toggle_success_log",
        "toggle_fail_log",
        "force_add",
        "force_remove",
        "force_toggle",
        "admin_add_admin",
        "admin_remove_admin",
        "admin_set_full",
        "backup_now",
    ]:
        dev_callbacks(call)
        return
# =========================================================
# MORE CALLBACKS (API / LOGS / DEV SETTINGS)
# =========================================================

def api_callbacks(call):
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if data == "api_add":
        set_state(chat_id, state="api_add_name", panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Enter API name:", back_only_kb("menu_apis"))
        return

    if data == "api_list":
        show_api_list(chat_id, msg_id)
        return
    if data.startswith("api_"):
        api_callbacks(call)
        return

    if data.startswith("view_") or data == "clean_old_logs":
        log_callbacks(call)
        return

    if data.startswith("api_toggle:"):
        api_id = int(data.split(":")[1])
        row = fetchone("SELECT is_active FROM api_configs WHERE id = ?", (api_id,))
        if row:
            new_val = 0 if int(row["is_active"]) == 1 else 1
            execute("UPDATE api_configs SET is_active = ? WHERE id = ?", (new_val, api_id))
        show_api_list(chat_id, msg_id)
        return

    if data == "api_delete_select":
        show_api_list(chat_id, msg_id, action="delete")
        return

    if data.startswith("api_delete:"):
        api_id = int(data.split(":")[1])
        execute("DELETE FROM api_configs WHERE id = ?", (api_id,))
        show_api_list(chat_id, msg_id)
        return

    if data == "api_set_fallback":
        show_api_list(chat_id, msg_id, action="fallback")
        return

    if data.startswith("api_fallback:"):
        api_id = int(data.split(":")[1])
        execute("UPDATE api_configs SET is_fallback = 0")
        execute("UPDATE api_configs SET is_fallback = 1 WHERE id = ?", (api_id,))
        show_api_list(chat_id, msg_id)
        return

    if data == "api_test_select":
        show_api_list(chat_id, msg_id, action="test")
        return

    if data.startswith("api_test:"):
        set_state(chat_id, state="api_test_id", panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Send user ID to test API:", back_only_kb("menu_apis"))
        return

    if data == "api_performance":
        show_api_performance(chat_id, msg_id)
        return


# =========================================================
# LOG CALLBACKS
# =========================================================

def log_callbacks(call):
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if data.startswith("view_lookup_logs:"):
        page = int(data.split(":")[1])
        show_logs(chat_id, msg_id, "lookup", page)
        return

    if data.startswith("view_admin_logs:"):
        page = int(data.split(":")[1])
        show_logs(chat_id, msg_id, "admin", page)
        return

    if data.startswith("view_broadcast_logs:"):
        page = int(data.split(":")[1])
        show_logs(chat_id, msg_id, "broadcast", page)
        return

    if data == "clean_old_logs":
        threshold = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(timespec="seconds")

        execute("DELETE FROM lookup_logs WHERE created_at < ?", (threshold,))
        execute("DELETE FROM admin_logs WHERE created_at < ?", (threshold,))
        execute("DELETE FROM broadcast_logs WHERE created_at < ?", (threshold,))

        bot.answer_callback_query(call.id, "Old logs cleaned")
        safe_edit(chat_id, msg_id, "🧹 Old logs deleted.", logs_menu_kb())
        return


# =========================================================
# DEV SETTINGS CALLBACKS
# =========================================================

def dev_callbacks(call):
    data = call.data
    chat_id = call.message.chat.id
    msg_id = call.message.message_id

    if data == "dev_bot_toggle":
        new = "0" if is_setting_on("bot_enabled", True) else "1"
        set_setting("bot_enabled", new)
        safe_edit(chat_id, msg_id, "🤖 Bot status updated.", dev_menu_kb())
        return

    if data == "toggle_admin_approval":
        new = "0" if is_setting_on("admin_approval_enabled", True) else "1"
        set_setting("admin_approval_enabled", new)
        safe_edit(chat_id, msg_id, "🔄 Approval setting updated.", dev_menu_kb())
        return

    if data == "dev_bonus":
        kb = InlineKeyboardMarkup()
        kb.add(btn("Set Initial Limit", "set_initial_limit", "primary"))
        kb.add(btn("Set Daily Bonus", "set_daily_bonus", "primary"))
        kb.add(btn("⬅️ Back", "menu_dev", "primary"))

        safe_edit(chat_id, msg_id, "🎁 Bonus Settings", kb)
        return

    if data in ["set_initial_limit", "set_daily_bonus"]:
        set_state(chat_id, state=data, panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Send value:", back_only_kb("menu_dev"))
        return

    if data == "dev_force_join":
        rows = fetchall("SELECT * FROM force_channels ORDER BY id DESC")
        text = "📢 <b>Force Join Channels</b>\n\n"

        for r in rows:
            text += f"{r['id']} - {r['channel_username']}\n"

        kb = InlineKeyboardMarkup()
        kb.add(btn("➕ Add Channel", "force_add", "success"))
        kb.add(btn("➖ Remove Channel", "force_remove", "danger"))
        kb.add(btn("Toggle ON/OFF", "force_toggle", "primary"))
        kb.add(btn("⬅️ Back", "menu_dev", "primary"))

        safe_edit(chat_id, msg_id, text, kb)
        return

    if data == "force_add":
        set_state(chat_id, state="force_add_channel_username", panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Send channel username (@xxx):", back_only_kb("dev_force_join"))
        return

    if data == "force_remove":
        set_state(chat_id, state="force_remove_channel_id", panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Send channel ID from list:", back_only_kb("dev_force_join"))
        return

    if data == "force_toggle":
        new = "0" if is_setting_on("force_join_enabled", False) else "1"
        set_setting("force_join_enabled", new)
        safe_edit(chat_id, msg_id, "🔄 Force join toggled.", dev_menu_kb())
        return

    if data == "dev_log_settings":
        kb = InlineKeyboardMarkup()
        kb.add(btn("Set Log Channel", "set_log_channel", "primary"))
        kb.add(btn("Toggle Success Logs", "toggle_success_log", "primary"))
        kb.add(btn("Toggle Fail Logs", "toggle_fail_log", "primary"))
        kb.add(btn("⬅️ Back", "menu_dev", "primary"))

        safe_edit(chat_id, msg_id, "📢 Log Settings", kb)
        return

    if data == "set_log_channel":
        set_state(chat_id, state="set_log_channel", panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Send chat ID:", back_only_kb("menu_dev"))
        return

    if data == "toggle_success_log":
        new = "0" if is_setting_on("log_success_enabled", True) else "1"
        set_setting("log_success_enabled", new)
        safe_edit(chat_id, msg_id, "🔄 Success log toggled.", dev_menu_kb())
        return

    if data == "toggle_fail_log":
        new = "0" if is_setting_on("log_fail_enabled", True) else "1"
        set_setting("log_fail_enabled", new)
        safe_edit(chat_id, msg_id, "🔄 Fail log toggled.", dev_menu_kb())
        return

    if data == "dev_admins":
        kb = InlineKeyboardMarkup()
        kb.add(btn("➕ Add Admin", "admin_add_admin", "success"))
        kb.add(btn("➖ Remove Admin", "admin_remove_admin", "danger"))
        kb.add(btn("👑 Grant Full Access", "admin_set_full", "primary"))
        kb.add(btn("⬅️ Back", "menu_dev", "primary"))

        safe_edit(chat_id, msg_id, "👑 Admin Manager", kb)
        return

    if data == "admin_add_admin":
        set_state(chat_id, state="admin_add_admin_id", panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Send user ID:", back_only_kb("dev_admins"))
        return

    if data == "admin_remove_admin":
        set_state(chat_id, state="admin_remove_admin_id", panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Send admin ID:", back_only_kb("dev_admins"))
        return

    if data == "admin_set_full":
        set_state(chat_id, state="admin_set_full_id", panel_message_id=msg_id)
        safe_edit(chat_id, msg_id, "Send admin ID:", back_only_kb("dev_admins"))
        return

    if data == "backup_now":
        ok = backup_db_to_telegram()
        bot.answer_callback_query(call.id, "Backup sent" if ok else "Backup failed")
        return


# =========================================================
# BACKUP / CLEANUP LOOPS
# =========================================================

def backup_db_to_telegram():
    try:
        with open(DB_PATH, "rb") as f:
            bot.send_document(BACKUP_CHAT_ID, f, caption="💾 Database Backup")
        return True
    except Exception:
        return False

def backup_loop():
    while True:
        hours = get_int_setting("backup_interval_hours", 1)
        time.sleep(hours * 3600)

        try:
            backup_db_to_telegram()
        except:
            pass

def cleanup_loop():
    while True:
        try:
            time.sleep(6 * 3600)
            threshold = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat(timespec="seconds")

            execute("DELETE FROM lookup_logs WHERE created_at < ?", (threshold,))
            execute("DELETE FROM admin_logs WHERE created_at < ?", (threshold,))
            execute("DELETE FROM broadcast_logs WHERE created_at < ?", (threshold,))
        except Exception:
            pass


# =========================================================
# MAIN
# =========================================================

def main():
    init_db()
    set_commands()
    keep_alive()

    threading.Thread(target=self_ping, daemon=True).start()
    threading.Thread(target=backup_loop, daemon=True).start()
    threading.Thread(target=cleanup_loop, daemon=True).start()

    print("🚀 Bot Started...")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    main()