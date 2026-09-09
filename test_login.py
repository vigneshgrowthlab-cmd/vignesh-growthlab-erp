"""Quick test: hit the Railway login endpoint and print the result."""
import urllib.request
import json

URL = "https://vignesh-growthlab-erp-production-2955.up.railway.app/api/v1/auth/login"
payload = {"username": "admin", "password": "Admin@1234"}

data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"}, method="POST")

try:
    resp = urllib.request.urlopen(req, timeout=15)
    body = resp.read().decode()
    print("Status:", resp.status)
    parsed = json.loads(body)
    user = parsed.get("user", {})
    print("Username:", user.get("username"))
    print("Role:", user.get("role"))
    print("Name:", user.get("full_name"))
    print("LOGIN WORKS!")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print("FAILED Status:", e.code)
    print("Body:", body)
except Exception as ex:
    print("Error:", ex)
