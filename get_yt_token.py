import os
import sys
import json
import urllib.parse
import webbrowser
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

# Cấu hình UTF-8 cho terminal Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

CONFIG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "config.json"))

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

yt_dest = config.get("youtube", {}).get("destination", {})
client_id = yt_dest.get("client_id", "").strip()
client_secret = yt_dest.get("client_secret", "").strip()

if not client_id or not client_secret:
    print("❌ Lỗi: Không tìm thấy client_id hoặc client_secret trong config.json!")
    sys.exit(1)

PORT = 8080
REDIRECT_URI = f"http://127.0.0.1:{PORT}"

SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

auth_params = {
    "client_id": client_id,
    "redirect_uri": REDIRECT_URI,
    "response_type": "code",
    "scope": " ".join(SCOPES),
    "access_type": "offline",
    "prompt": "consent"
}
auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(auth_params)

auth_code = None

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = """
            <html>
            <head><title>Xác thực thành công!</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                <h1 style="color: #2e7d32;">✅ Cấp quyền YouTube thành công!</h1>
                <p style="font-size: 18px;">Hệ thống đã nhận được đầy đủ quyền (Đăng video + Tự động bình luận).</p>
                <p style="color: #666;">Bạn có thể đóng tab trình duyệt này lại và quay lại chat với AI.</p>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            err = params.get("error", ["Unknown error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = f"<html><body><h1>❌ Lỗi xác thực: {err}</h1></body></html>"
            self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Không in log server ra console

print("=" * 60)
print("🔑 KHỞI TẠO CẤP QUYỀN YOUTUBE 1-CHẠM (UPLOAD + AUTO COMMENT)")
print("=" * 60)
print("🌐 Đang tự động mở trình duyệt để bạn đăng nhập và cấp quyền...")
print(f"👉 Nếu trình duyệt không tự mở, hãy copy link này dán vào Chrome:\n{auth_url}\n")

webbrowser.open(auth_url)

server = HTTPServer(("127.0.0.1", PORT), OAuthCallbackHandler)
while not auth_code:
    server.handle_request()
server.server_close()

print("🔄 Đang trao đổi mã xác thực để lấy Refresh Token vĩnh viễn...")

token_url = "https://oauth2.googleapis.com/token"
token_data = {
    "client_id": client_id,
    "client_secret": client_secret,
    "code": auth_code,
    "grant_type": "authorization_code",
    "redirect_uri": REDIRECT_URI
}

res = requests.post(token_url, data=token_data)
if res.status_code == 200:
    data = res.json()
    new_refresh = data.get("refresh_token")
    new_access = data.get("access_token")

    if new_refresh:
        config["youtube"]["destination"]["refresh_token"] = new_refresh
    if new_access:
        config["youtube"]["destination"]["access_token"] = new_access

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

    print("\n🎉 THÀNH CÔNG RỰC RỠ!")
    print(f"✅ Đã cập nhật Refresh Token mới vào config.json!")
    print(f"✅ Token đã có đầy đủ quyền:")
    print("   - Đăng video YouTube (youtube.upload)")
    print("   - Tự động bình luận dưới video (youtube.force-ssl)")
else:
    print(f"\n❌ Lỗi khi đổi token: {res.text}")
