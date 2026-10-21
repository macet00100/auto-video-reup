import os
import json
import random
import requests
import urllib.request
from typing import Dict, Any, List, Optional
from core.task_queue import LogManager
from core.uploader_yt import YouTubeUploader

REPLIED_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "replied_comments.json"))

FALLBACK_REPLIES = [
    "Dạ cảm ơn bạn nhiều nha! Chúc bạn xem phim thật vui vẻ và có một ngày tuyệt vời ạ! 🥰🍿",
    "Cảm ơn bạn đã luôn theo dõi và ủng hộ kênh! Bạn nhớ đón xem các tập tiếp theo nha! ❤️✨",
    "Dạ ad ghi nhận góp ý của bạn nha! Chúc bạn có những phút giây thư giãn thật tuyệt vời cùng kênh ạ! 🍿✨",
    "Cảm ơn bạn đã đồng hành cùng kênh! Nếu thấy phim hay nhớ bấm Like và chia sẻ ủng hộ ad nhé! 🥰❤️",
    "Dạ chuẩn luôn bạn ơi! Cảm ơn bạn đã tương tác, chúc bạn và gia đình xem phim vui vẻ nha! ✨🍿"
]

class AutoReplyBot:
    @staticmethod
    def _load_replied_ids() -> Dict[str, List[str]]:
        os.makedirs(os.path.dirname(REPLIED_FILE), exist_ok=True)
        if not os.path.exists(REPLIED_FILE):
            return {"youtube": [], "facebook": []}
        try:
            with open(REPLIED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                data.setdefault("youtube", [])
                data.setdefault("facebook", [])
                return data
        except Exception:
            return {"youtube": [], "facebook": []}

    @staticmethod
    def _save_replied_id(platform: str, comment_id: str):
        if not comment_id:
            return
        data = AutoReplyBot._load_replied_ids()
        data.setdefault(platform, [])
        if comment_id not in data[platform]:
            data[platform].append(comment_id)
            # Giữ tối đa 2000 ID gần nhất để tránh file phình to
            if len(data[platform]) > 2000:
                data[platform] = data[platform][-2000:]
        try:
            temp_file = REPLIED_FILE + ".tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, REPLIED_FILE)
        except Exception:
            pass

    @staticmethod
    def generate_ai_reply(comment_text: str, gemini_key: str = "") -> str:
        """Sử dụng Gemini AI (Free) để viết câu trả lời thông minh, thân thiện cho khán giả."""
        cleaned_text = (comment_text or "").strip()
        if not cleaned_text:
            return random.choice(FALLBACK_REPLIES)

        if gemini_key and gemini_key.strip():
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là admin kênh review phim (Fanpage Facebook & YouTube Channel).\n"
                    f"Khán giả vừa để lại bình luận dưới video: \"{cleaned_text}\"\n"
                    f"Nhiệm vụ: Hãy viết 1 câu trả lời (reply) thật thân thiện, lễ phép, gần gũi và dí dỏm.\n"
                    f"- Nếu khán giả hỏi về phim (tên phim, phần tiếp, diễn viên): Giải đáp ngắn gọn hoặc hẹn tập sớm nhất.\n"
                    f"- Nếu khán giả khen phim: Cảm ơn chân thành và chúc xem phim vui vẻ.\n"
                    f"- Độ dài: Đúng 1 đến 2 câu ngắn gọn, súc tích.\n"
                    f"- Xưng hô: 'mình' hoặc 'ad', gọi người xem là 'bạn' hoặc 'cả nhà'.\n"
                    f"- Có kèm emoji dễ thương: ❤️, 🥰, ✨, 🍿.\n"
                    f"Chỉ trả về đúng nội dung câu trả lời, không để trong ngoặc kép, không giải thích."
                )
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = requests.post(url, json=payload, timeout=10)
                if res.status_code == 200:
                    candidates = res.json().get("candidates", [])
                    if candidates:
                        raw_reply = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        raw_reply = raw_reply.replace('"', '').replace("'", "")
                        if raw_reply and len(raw_reply) >= 5:
                            return raw_reply
            except Exception as e:
                LogManager.log(f"Lỗi gọi Gemini AI tạo câu trả lời (dùng câu mẫu): {e}", "WARNING", "AI_REPLY")

        return random.choice(FALLBACK_REPLIES)

    @staticmethod
    def scan_and_reply_youtube(yt_cfg: Dict[str, Any], gemini_key: str = "", max_videos: int = 5) -> int:
        """Tự động quét và trả lời bình luận của khán giả trên YouTube."""
        dest = yt_cfg.get("destination", {})
        token = YouTubeUploader.get_valid_access_token(dest)
        if not token:
            return 0

        replied_data = AutoReplyBot._load_replied_ids()
        replied_ids = set(replied_data.get("youtube", []))
        reply_count = 0

        try:
            # 1. Lấy Channel ID của chính mình
            ch_req = urllib.request.Request(
                "https://www.googleapis.com/youtube/v3/channels?part=contentDetails,id&mine=true",
                headers={"Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(ch_req, timeout=10) as resp:
                ch_data = json.loads(resp.read().decode())
                items = ch_data.get("items", [])
                if not items:
                    return 0
                my_channel_id = items[0]["id"]
                uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

            # 2. Lấy danh sách video mới nhất
            pl_req = urllib.request.Request(
                f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_id}&maxResults={max_videos}",
                headers={"Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(pl_req, timeout=10) as resp2:
                pl_data = json.loads(resp2.read().decode())
                video_items = pl_data.get("items", [])

            # 3. Duyệt từng video để tìm bình luận cần rep
            for v_item in video_items:
                v_id = v_item.get("snippet", {}).get("resourceId", {}).get("videoId")
                if not v_id:
                    continue

                cmt_url = f"https://www.googleapis.com/youtube/v3/commentThreads?part=snippet,replies&videoId={v_id}&maxResults=15"
                cmt_req = urllib.request.Request(cmt_url, headers={"Authorization": f"Bearer {token}"})
                try:
                    with urllib.request.urlopen(cmt_req, timeout=10) as cmt_resp:
                        thread_data = json.loads(cmt_resp.read().decode())
                except Exception:
                    continue

                for thread in thread_data.get("items", []):
                    top_cmt = thread.get("snippet", {}).get("topLevelComment", {})
                    cmt_id = top_cmt.get("id")
                    snippet = top_cmt.get("snippet", {})
                    author_ch_id = snippet.get("authorChannelId", {}).get("value")
                    author_name = snippet.get("authorDisplayName", "Khán giả")
                    cmt_text = snippet.get("textDisplay", "")

                    # Bỏ qua nếu đã trả lời rồi
                    if cmt_id in replied_ids:
                        continue
                    # Bỏ qua bình luận của chính kênh mình
                    if author_ch_id == my_channel_id:
                        continue

                    # Kiểm tra xem kênh mình đã từng rep trong thread này chưa
                    has_replied = False
                    sub_replies = thread.get("replies", {}).get("comments", [])
                    for sub in sub_replies:
                        if sub.get("snippet", {}).get("authorChannelId", {}).get("value") == my_channel_id:
                            has_replied = True
                            break

                    if has_replied:
                        AutoReplyBot._save_replied_id("youtube", cmt_id)
                        replied_ids.add(cmt_id)
                        continue

                    # Tạo câu trả lời bằng AI
                    ai_reply = AutoReplyBot.generate_ai_reply(cmt_text, gemini_key)
                    reply_payload = {
                        "snippet": {
                            "parentId": cmt_id,
                            "textOriginal": ai_reply
                        }
                    }
                    rep_res = requests.post(
                        "https://www.googleapis.com/youtube/v3/comments?part=snippet",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                        json=reply_payload,
                        timeout=15
                    )

                    if rep_res.status_code in [200, 201]:
                        AutoReplyBot._save_replied_id("youtube", cmt_id)
                        replied_ids.add(cmt_id)
                        reply_count += 1
                        LogManager.log(f"[YOUTUBE] Đã tự động trả lời cmt của {author_name}: '{ai_reply}'", "SUCCESS", "AUTO_REPLY")
                    else:
                        LogManager.log(f"[YOUTUBE] Không thể gửi reply cmt: {rep_res.text[:120]}", "WARNING", "AUTO_REPLY")

        except Exception as e:
            LogManager.log(f"Lỗi trong quá trình quét comment YouTube: {e}", "WARNING", "AUTO_REPLY")

        return reply_count

    @staticmethod
    def scan_and_reply_facebook(fb_cfg: Dict[str, Any], gemini_key: str = "", max_videos: int = 5) -> int:
        """Tự động quét và trả lời bình luận của khán giả trên Facebook Fanpage."""
        dest = fb_cfg.get("destination", {})
        page_id = dest.get("page_id", "").strip()
        access_token = dest.get("access_token", "").strip()
        if not page_id or not access_token:
            return 0

        # Lấy Page Access Token
        page_token = access_token
        try:
            pt_res = requests.get(
                f"https://graph.facebook.com/v19.0/{page_id}?fields=access_token&access_token={access_token}",
                timeout=15
            )
            pt_data = pt_res.json()
            if pt_data.get("access_token"):
                page_token = pt_data["access_token"]
        except Exception:
            pass

        replied_data = AutoReplyBot._load_replied_ids()
        replied_ids = set(replied_data.get("facebook", []))
        reply_count = 0

        try:
            # 1. Lấy danh sách video mới nhất của Fanpage
            v_url = f"https://graph.facebook.com/v19.0/{page_id}/videos?fields=id,title&limit={max_videos}&access_token={page_token}"
            v_res = requests.get(v_url, timeout=15)
            if v_res.status_code != 200:
                return 0

            videos = v_res.json().get("data", [])
            for v in videos:
                v_id = v.get("id")
                if not v_id:
                    continue

                # 2. Lấy danh sách bình luận của video
                c_url = f"https://graph.facebook.com/v19.0/{v_id}/comments?fields=id,from,message,comments{{id,from}}&access_token={page_token}"
                c_res = requests.get(c_url, timeout=15)
                if c_res.status_code != 200:
                    continue

                comments = c_res.json().get("data", [])
                for cmt in comments:
                    cmt_id = cmt.get("id")
                    from_info = cmt.get("from", {})
                    author_id = from_info.get("id")
                    author_name = from_info.get("name", "Khán giả")
                    cmt_text = cmt.get("message", "")

                    # Bỏ qua nếu đã xử lý
                    if cmt_id in replied_ids:
                        continue
                    # Bỏ qua bình luận của chính Fanpage
                    if author_id == page_id:
                        continue

                    # Kiểm tra xem Fanpage đã reply chưa
                    has_replied = False
                    sub_cmts = cmt.get("comments", {}).get("data", [])
                    for sub in sub_cmts:
                        if sub.get("from", {}).get("id") == page_id:
                            has_replied = True
                            break

                    if has_replied:
                        AutoReplyBot._save_replied_id("facebook", cmt_id)
                        replied_ids.add(cmt_id)
                        continue

                    # Tạo câu trả lời bằng AI
                    ai_reply = AutoReplyBot.generate_ai_reply(cmt_text, gemini_key)
                    rep_url = f"https://graph.facebook.com/v19.0/{cmt_id}/comments"
                    rep_res = requests.post(
                        rep_url,
                        data={"message": ai_reply, "access_token": page_token},
                        timeout=15
                    )

                    if rep_res.status_code in [200, 201]:
                        AutoReplyBot._save_replied_id("facebook", cmt_id)
                        replied_ids.add(cmt_id)
                        reply_count += 1
                        LogManager.log(f"[FACEBOOK] Đã tự động trả lời cmt của {author_name}: '{ai_reply}'", "SUCCESS", "AUTO_REPLY")
                    else:
                        LogManager.log(f"[FACEBOOK] Không thể gửi reply cmt: {rep_res.text[:120]}", "WARNING", "AUTO_REPLY")

        except Exception as e:
            LogManager.log(f"Lỗi trong quá trình quét comment Facebook: {e}", "WARNING", "AUTO_REPLY")

        return reply_count

    @staticmethod
    def scan_and_reply_all(cfg: Dict[str, Any]) -> Dict[str, int]:
        """Chạy quét và trả lời bình luận đồng thời trên cả 2 nền tảng."""
        gemini_key = cfg.get("general", {}).get("gemini_api_key", "")
        yt_count = 0
        fb_count = 0

        if cfg.get("youtube", {}).get("enabled", True):
            yt_count = AutoReplyBot.scan_and_reply_youtube(cfg.get("youtube", {}), gemini_key)

        if cfg.get("facebook", {}).get("enabled", True):
            fb_count = AutoReplyBot.scan_and_reply_facebook(cfg.get("facebook", {}), gemini_key)

        if yt_count > 0 or fb_count > 0:
            LogManager.log(f"Tổng kết tự động Rep cmt AI: YouTube ({yt_count}), Facebook ({fb_count})", "SUCCESS", "AUTO_REPLY")

        return {"youtube": yt_count, "facebook": fb_count}
