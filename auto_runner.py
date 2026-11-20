import os
import sys
import time
import json
import feedparser
import re
import urllib.request
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple

from core.config import ConfigManager
from core.task_queue import LogManager
from core.monitor import ChannelMonitor
from core.downloader import VideoDownloader
from core.processor import VideoProcessor
from core.ai_rewriter import AIRewriter
from core.thumbnail import ThumbnailGenerator
from core.uploader_yt import YouTubeUploader
from core.uploader_fb import FacebookUploader
from core.history import HistoryManager
from core.auto_reply import AutoReplyBot
from core.china_crawler import ChinaCrawler
from core.ai_reviewer import AIReviewer

# Danh sách câu bình luận tự động tăng tương tác (Call-to-Action) sau khi đăng video
YOUTUBE_COMMENTS = [
    "Chúc cả nhà xem phim vui vẻ! Mọi người thấy phim hôm nay thế nào? Để lại bình luận cho mình biết nhé! ❤️",
    "Mọi người xem phim thấy hay nhớ ủng hộ mình 1 Like và 1 Đăng ký kênh để đón xem tập mới sớm nhất nhé! 🥰",
    "Cả nhà muốn xem thêm phim gì hay phần tiếp theo cứ để lại bình luận giúp em, em sẽ lên phim sớm nhất nhé! 🍿",
    "Cảm ơn mọi người đã luôn đồng hành và ủng hộ kênh! Chúc cả nhà có những phút giây thư giãn thật tuyệt vời! ✨",
    "Mọi người thích nhất đoạn nào trong phim? Hãy để lại cảm nghĩ bên dưới để cùng bàn luận nhé! 💬"
]

FACEBOOK_COMMENTS = [
    "Chúc cả nhà xem phim vui vẻ! Mọi người thấy phim hôm nay thế nào ạ? Để lại cmt cho mình biết nhé! ❤️",
    "Mọi người xem video thấy hay nhớ ủng hộ mình 1 Like và 1 Follow Fanpage để không bỏ lỡ những tập tiếp theo nhé! 🥰",
    "Cả nhà muốn xem phim gì cứ cmt giúp em để em lên phim sớm nhất phục vụ mọi người nhé! 🍿",
    "Cảm ơn cả nhà đã luôn theo dõi và ủng hộ trang! Chúc mọi người có những phút giây xem phim thư giãn thật tuyệt vời! ✨",
    "Thả tim ❤️ và Follow page để cập nhật những bộ phim hay nhất mỗi ngày nhé cả nhà ơi! 💬"
]

def clean_all_temp_cache():
    """Xóa sạch toàn bộ video tạm, frame và cache phim sau khi hoàn thành để bảo toàn 100% dung lượng ổ cứng."""
    temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "temp"))
    thumb_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "thumbnails"))
    cleaned_count = 0

    for folder in [temp_dir, thumb_dir]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f != ".gitkeep":
                    file_path = os.path.join(folder, f)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                            cleaned_count += 1
                    except Exception:
                        pass
    LogManager.log(f"Đã dọn sạch {cleaned_count} file cache tạm để tối ưu ổ đĩa.", "INFO", "CLEANUP")

def get_destination_channel_uploaded_info(cfg: Dict[str, Any], max_results: int = 50) -> Dict[str, Any]:
    """Lấy danh sách tiêu đề và RefID của các video mới nhất đã tải lên kênh YouTube đích để chống trùng lặp vĩnh viễn."""
    info = {
        "titles": [],
        "ref_ids": set()
    }
    try:
        yt_dest = cfg.get("youtube", {}).get("destination", {})
        token = YouTubeUploader.get_valid_access_token(yt_dest)
        if not token:
            return info

        # Lấy uploads playlist ID của kênh đích
        ch_req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=contentDetails&mine=true",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(ch_req, timeout=10) as resp:
            ch_data = json.loads(resp.read().decode())
            items = ch_data.get("items", [])
            if not items:
                return info
            uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

        # Lấy danh sách video đã tải lên
        pl_req = urllib.request.Request(
            f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet&playlistId={uploads_id}&maxResults={max_results}",
            headers={"Authorization": f"Bearer {token}"}
        )
        with urllib.request.urlopen(pl_req, timeout=10) as resp2:
            pl_data = json.loads(resp2.read().decode())
            for it in pl_data.get("items", []):
                snippet = it.get("snippet", {})
                t = snippet.get("title", "")
                d = snippet.get("description", "")
                if t:
                    info["titles"].append(t)
                if d:
                    for r_id in re.findall(r'\[(?:RefID|SourceID|Ref):\s*([a-zA-Z0-9_-]+)\]', d):
                        info["ref_ids"].add(r_id)
    except Exception as e:
        LogManager.log(f"Không thể lấy danh sách video kênh đích: {e}", "WARNING", "DUPLICATE_CHECK")
    return info

def is_title_duplicate(title1: str, title2: str, threshold: float = 0.45) -> bool:
    """So sánh 2 tiêu đề video dựa trên từ khóa nội dung đặc trưng (loại bỏ từ nối, đại từ và từ ngữ thể loại đại trà)."""
    stop_words = {
        "cực", "sốc", "cận", "cảnh", "khám", "phá", "ngay", "full", "hd", "reviewphim", "phimhay",
        "reels", "viral", "shorts", "phần", "tập", "p", "cô", "chàng", "nàng", "ai", "ngờ", "lại",
        "thành", "về", "để", "mà", "còn", "bị", "cho", "của", "những", "các", "và", "với", "trong",
        "được", "làm", "dùng", "ra", "vào", "có", "thì", "ở", "từ", "qua", "sau", "khi", "lên",
        "xuyên", "không", "truyện", "sách", "kiếp", "trước", "sống", "lại", "trọng", "sinh",
        "hệ", "thống", "kích", "hoạt", "người", "nhà", "cả", "nữ", "nam", "phim", "năm"
    }
    words1 = {w for w in re.findall(r'[\w\d]+', title1.lower()) if w not in stop_words and len(w) > 1}
    words2 = {w for w in re.findall(r'[\w\d]+', title2.lower()) if w not in stop_words and len(w) > 1}
    if not words1 or not words2:
        return False
    inter = words1.intersection(words2)
    min_len = min(len(words1), len(words2))
    similarity = len(inter) / min_len if min_len > 0 else 0
    # Phải có độ tương đồng từ 45% trở lên VÀ trùng ít nhất 4 từ khóa cốt truyện mới là cùng 1 bộ phim
    return similarity >= threshold and len(inter) >= 4

def get_channel_latest_videos(channel_id: str, cfg: Dict[str, Any], max_results: int = 15) -> List[Dict[str, str]]:
    """
    Quét video mới từ kênh YouTube bằng 3 tầng bảo vệ:
    1. YouTube Data API v3 (PlaylistItems từ uploads playlist): 100% chuẩn xác, không bao giờ 404.
    2. yt-dlp flat-playlist: Trích xuất trực tiếp từ web nếu API gặp sự cố.
    3. RSS feed: Tầng dự phòng cuối cùng.
    """
    # TẦNG 1: YouTube Data API v3 (Chuẩn xác nhất, không bao giờ bị 404)
    try:
        yt_dest = cfg.get("youtube", {}).get("destination", {})
        token = YouTubeUploader.get_valid_access_token(yt_dest)
        uploads_id = "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id
        url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,contentDetails&playlistId={uploads_id}&maxResults={max_results}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])
            if items:
                vids = []
                for it in items:
                    v_id = it.get("contentDetails", {}).get("videoId")
                    if v_id:
                        vids.append({
                            "id": v_id,
                            "title": it.get("snippet", {}).get("title", ""),
                            "url": f"https://www.youtube.com/watch?v={v_id}"
                        })
                if vids:
                    return vids
    except Exception as e:
        LogManager.log(f"YouTube Data API không lấy được video kênh {channel_id}: {e}. Đang chuyển sang tầng dự phòng yt-dlp.", "WARNING", "WORKER")

    # TẦNG 2: yt-dlp flat-playlist
    try:
        import yt_dlp
        ydl_opts = {"extract_flat": True, "quiet": True, "playlistend": max_results}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(f"https://www.youtube.com/channel/{channel_id}/videos", download=False)
            entries = res.get("entries", [])
            if entries:
                vids = []
                for e in entries:
                    v_id = e.get("id")
                    if v_id:
                        vids.append({
                            "id": v_id,
                            "title": e.get("title", ""),
                            "url": f"https://www.youtube.com/watch?v={v_id}"
                        })
                if vids:
                    return vids
    except Exception as e:
        LogManager.log(f"yt-dlp flat-playlist lỗi: {e}. Đang chuyển sang RSS dự phòng.", "WARNING", "WORKER")

    # TẦNG 3: RSS Feed
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        feed = feedparser.parse(rss_url)
        vids = []
        for entry in feed.entries[:max_results]:
            v_id = getattr(entry, "yt_videoid", None)
            if not v_id:
                m = re.search(r"v=([a-zA-Z0-9_-]+)", getattr(entry, "link", ""))
                if m: v_id = m.group(1)
            if v_id:
                vids.append({
                    "id": v_id,
                    "title": getattr(entry, "title", ""),
                    "url": getattr(entry, "link", f"https://www.youtube.com/watch?v={v_id}")
                })
        return vids
    except Exception:
        pass

    return []

def run_china_raw_pipeline(cfg: Dict[str, Any], destination_titles: List[str], destination_ref_ids: set) -> bool:
    """
    Quy trình Phong cách B (AI Film Review / Recap):
    1. Quét kho phim ngắn nội địa Trung Quốc trực tiếp qua API (độ trễ = 0, chưa có trên YouTube).
    2. Lọc các bộ phim có chủ đề kịch tính/vả mặt/hào môn mới ra mắt hôm nay.
    3. Tải poster gốc, dùng Gemini Flash tạo gói kịch bản review triệu view + mô tả Fair Use.
    4. Tạo giọng đọc thuyết minh tiếng Việt AI bằng Edge-TTS / gTTS.
    5. Thiết kế thumbnail điện ảnh giật gân (chữ vàng viền đen, poster sắc nét).
    6. Tải M3U8 siêu tốc và render lách bản quyền kết hợp lồng tiếng thuyết minh.
    7. Đăng lên YouTube và Facebook (HOÀN TOÀN KHÔNG TẠO SHORTS để bảo vệ kênh).
    """
    general_cfg = cfg.get("general", {})
    yt_cfg = cfg.get("youtube", {})
    fb_cfg = cfg.get("facebook", {})

    LogManager.log(">>> BẮT ĐẦU CHẾ ĐỘ PHONG CÁCH B: QUÉT PHIM GỐC NỘI ĐỊA TRUNG QUỐC (ĐỘC QUYỀN 100%) <<<", "INFO", "CHINA_RAW")
    candidates = ChinaCrawler.get_candidate_dramas(limit=25)
    if not candidates:
        LogManager.log("Không quét được bộ phim ngắn nào từ các trạm API Trung Quốc.", "WARNING", "CHINA_RAW")
        return False

    selected_drama = None
    for cand in candidates:
        unique_id = cand["id"]
        raw_title = cand["raw_title"]

        # Kiểm tra lịch sử
        if HistoryManager.is_processed(unique_id):
            continue

        # Kiểm tra trùng lặp tiêu đề với các video đã có trên kênh đích
        clean_cand = AIRewriter.clean_and_format_title(raw_title)
        is_dup = False
        for dt in destination_titles:
            if is_title_duplicate(clean_cand, dt) or is_title_duplicate(raw_title, dt):
                LogManager.log(f"Phim Trung Quốc [{raw_title}] khớp tiêu đề đã có ('{dt}') -> Bỏ qua.", "WARNING", "CHINA_RAW")
                HistoryManager.record_processed(unique_id, raw_title, yt_uploaded=False, fb_uploaded=False, extra={"skipped": True, "reason": f"Trùng tiêu đề với '{dt}'"})
                is_dup = True
                break

        if is_dup:
            continue

        LogManager.log(f"Đang xử lý phim ứng viên kịch tính: '{raw_title}' (Điểm kịch tính: {cand['score']})", "INFO", "CHINA_RAW")
        success = process_and_upload_china_drama(
            drama_info=cand,
            upload_to_yt=yt_cfg.get("enabled", True),
            upload_to_fb=fb_cfg.get("enabled", True),
            cfg=cfg
        )
        if success:
            LogManager.log(f"Đã xử lý và xuất bản thành công phim: '{raw_title}'", "SUCCESS", "CHINA_RAW")
            return True
        else:
            LogManager.log(f"Phim '{raw_title}' không tải được từ CDN hoặc xử lý thất bại -> Tự động thử tiếp phim tiếp theo trong danh sách...", "WARNING", "CHINA_RAW")

    LogManager.log("Toàn bộ phim mới quét được hôm nay đều đã được xử lý, trùng lặp hoặc CDN không phản hồi.", "INFO", "CHINA_RAW")
    return False

def get_next_scheduled_slot() -> Tuple[datetime, str, int]:
    """
    Tính toán khung giờ vàng tiếp theo chuẩn giờ Việt Nam (UTC+7) để hẹn giờ đăng:
    - Khung 1: 11:30 (Trưa)
    - Khung 2: 17:30 (Chiều tan tầm)
    - Khung 3: 21:00 (Tối muộn)
    Tự động tránh các khung giờ đã được xếp lịch trước đó, xếp xoay vòng sang các slot tiếp theo.
    """
    tz_vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(tz_vn)
    slots = [(11, 30), (17, 30), (21, 0)]

    scheduled_isostrings = set()
    try:
        hist_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "processed_history.json"))
        if os.path.exists(hist_path):
            with open(hist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                hist_dict = data.get("history", {}) if isinstance(data, dict) else {}
                for v in hist_dict.values():
                    extra = v.get("extra", {})
                    s_utc = extra.get("scheduled_utc")
                    if s_utc:
                        scheduled_isostrings.add(s_utc)
    except Exception:
        pass

    for day_offset in range(4):
        check_date = (now_vn + timedelta(days=day_offset)).date()
        for hour, minute in slots:
            slot_dt = datetime(check_date.year, check_date.month, check_date.day, hour, minute, tzinfo=tz_vn)
            if slot_dt < now_vn + timedelta(minutes=25):
                continue
            iso_utc = slot_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if iso_utc not in scheduled_isostrings:
                return slot_dt, iso_utc, int(slot_dt.timestamp())

    fallback_dt = datetime(now_vn.year, now_vn.month, now_vn.day, 11, 30, tzinfo=tz_vn) + timedelta(days=1)
    return fallback_dt, fallback_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"), int(fallback_dt.timestamp())

def process_and_upload_china_drama(
    drama_info: Dict[str, Any],
    upload_to_yt: bool,
    upload_to_fb: bool,
    cfg: Dict[str, Any]
) -> bool:
    task_id = f"cn_{int(time.time())}"
    vod_id = drama_info["vod_id"]
    raw_title = drama_info["raw_title"]
    m3u8_url = drama_info["m3u8_url"]
    poster_url = drama_info.get("poster_url", "")
    unique_id = drama_info["id"]

    general_cfg = cfg.get("general", {})
    yt_cfg = cfg.get("youtube", {})
    fb_cfg = cfg.get("facebook", {})
    gemini_key = general_cfg.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")

    temp_files = []

    try:
        # BƯỚC 1: TẢI POSTER GỐC TỪ XƯỞNG PHIM
        poster_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "temp", f"poster_{task_id}.jpg"))
        has_poster = ChinaCrawler.download_poster(poster_url, poster_path)
        if has_poster:
            temp_files.append(poster_path)

        # BƯỚC 2: AI REVIEW PACKAGE (Gemini Flash)
        LogManager.log(f"[{task_id}] Đang phân tích kịch bản và sáng tạo nội dung review cho: '{raw_title}'...", "INFO", "AI_REVIEW")
        review_pkg = AIReviewer.generate_review_package(raw_title, gemini_key)
        new_title = review_pkg["vietnamese_title"]
        hook_text = review_pkg["thumbnail_hook"]
        sub_text = review_pkg["thumbnail_sub"]
        voice_text = review_pkg.get("voice_intro", "")
        yt_description = review_pkg["description"]

        # BƯỚC 3: THIẾT KẾ THUMBNAIL ĐIỆN ẢNH GIẬT GÂN (Chuẩn 16:9 1280x720)
        thumb_path = ThumbnailGenerator.create_review_thumbnail(
            poster_path=poster_path if has_poster else None,
            hook_text=hook_text,
            sub_text=sub_text,
            task_id=task_id
        )

        # BƯỚC 4: TẢI VIDEO M3U8 TRỰC TIẾP TỪ NGUỒN NỘI ĐỊA TRUNG QUỐC
        raw_video = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "temp", f"raw_{task_id}.mp4"))
        temp_files.append(raw_video)
        max_mins = general_cfg.get("max_duration_minutes", 180)
        dl_ok = ChinaCrawler.download_m3u8_video(m3u8_url, raw_video, max_duration_seconds=int(max_mins * 60))
        if not dl_ok:
            LogManager.log(f"[{task_id}] Không thể tải video từ link M3U8.", "ERROR", "CHINA_RAW")
            return False

        # BƯỚC 5: TẠO BẢN REVIEW CÔ ĐỌNG DỒN DẬP (15 - 25 PHÚT CHUẨN FILM RECAP)
        review_mode = general_cfg.get("review_mode", "condensed_recap")
        target_recap_mins = general_cfg.get("target_recap_minutes", 20)
        video_to_process = raw_video

        if review_mode == "condensed_recap":
            montage_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "temp", f"montage_{task_id}.mp4"))
            condensed_video = VideoProcessor.create_condensed_recap_montage(
                input_video_path=raw_video,
                output_montage_path=montage_path,
                target_minutes=target_recap_mins,
                clip_duration=45,
                task_id=task_id
            )
            if condensed_video != raw_video:
                temp_files.append(condensed_video)
                video_to_process = condensed_video

        # BƯỚC 5.5: TẠO TRỌN GÓI GIỌNG ĐỌC THUYẾT MINH & ĐỒ HỌA KÊU GỌI ĐĂNG KÝ (CTA) CUỐI PHIM
        vid_dur = VideoProcessor.get_video_duration(video_to_process)
        voice_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "temp", f"voice_{task_id}.mp3"))
        voice_info = AIReviewer.synthesize_full_review_voiceover(
            intro_text=voice_text,
            outro_text=review_pkg.get("voice_outro", ""),
            total_duration_sec=vid_dur,
            output_path=voice_path,
            task_id=task_id
        )
        if voice_info.get("voice_path"):
            temp_files.append(voice_path)

        outro_banner = ThumbnailGenerator.create_outro_banner(task_id=task_id, channel_name="@CoolMeoPhim")
        if outro_banner:
            temp_files.append(outro_banner)

        # BƯỚC 6: RENDER FFMPEG LÁCH BẢN QUYỀN + DYNAMIC DUCKING + OVERLAY OUTRO BANNER
        user_bypass = yt_cfg.get("bypass_rules", {})
        combined_rules = {
            "hflip": user_bypass.get("hflip", True),
            "remove_logo": user_bypass.get("remove_logo", True),
            "speed": float(user_bypass.get("speed", 1.05)),
            "pitch_shift": user_bypass.get("pitch_shift", True),
            "add_bgm": user_bypass.get("add_bgm", True),
            "bgm_volume": float(user_bypass.get("bgm_volume", 0.12)),
            "crop_percent": float(user_bypass.get("crop_percent", 4.5)),
            "color_boost": user_bypass.get("color_boost", True),
            "change_fps": user_bypass.get("change_fps", True),
            "target_resolution": user_bypass.get("target_resolution", "720p"),
            "cut_intro_seconds": float(user_bypass.get("cut_intro_seconds", 2.0)),
            "preset": "veryfast",
            "voiceover_path": voice_info.get("voice_path"),
            "d_intro": voice_info.get("d_intro", 25.0),
            "outro_start": voice_info.get("outro_start", max(0.0, vid_dur - 20.0)),
            "outro_banner_path": outro_banner
        }

        processed_video = VideoProcessor.process(
            input_path=video_to_process,
            task_id=task_id,
            rules=combined_rules
        )
        temp_files.append(processed_video)

        # BƯỚC 7: XUẤT BẢN HOẶC HẸN GIỜ ĐĂNG LÊN YOUTUBE & FACEBOOK
        yt_success = False
        fb_success = False
        uploaded_yt_id = None
        uploaded_fb_id = None

        is_scheduled = general_cfg.get("schedule_mode", "scheduled") == "scheduled"
        yt_publish_at = None
        fb_schedule_ts = None
        slot_vn_str = ""

        if is_scheduled:
            slot_dt, yt_publish_at, fb_schedule_ts = get_next_scheduled_slot()
            slot_vn_str = slot_dt.strftime("%H:%M ngày %d/%m/%Y")
            LogManager.log(f"[{task_id}] ⏰ Đã lên lịch hẹn giờ đăng video: {slot_vn_str} (Giờ VN)", "SUCCESS", "SCHEDULER")

        if upload_to_yt:
            seo_tags = AIRewriter.get_recommended_tags(new_title)
            action_desc = f"Hẹn giờ đăng ({slot_vn_str})" if is_scheduled else "Đăng ngay công khai"
            LogManager.log(f"[{task_id}] Đang tải phim review độc quyền lên YouTube [{action_desc}]...", "INFO", "YOUTUBE")
            try:
                yt_res = YouTubeUploader.upload(
                    video_path=processed_video,
                    title=new_title,
                    description=yt_description,
                    thumbnail_path=thumb_path,
                    config=yt_cfg.get("destination", {}),
                    tags=seo_tags,
                    publish_at=yt_publish_at
                )
                yt_success = yt_res.get("success", False) if isinstance(yt_res, dict) else False
                if yt_success:
                    uploaded_yt_id = yt_res.get("video_id")
                    LogManager.log(f"[{task_id}] Upload YouTube thành công! Video ID: {uploaded_yt_id}", "SUCCESS", "YOUTUBE")
                    pin_comment = random.choice(YOUTUBE_COMMENTS)
                    YouTubeUploader.add_comment(uploaded_yt_id, pin_comment, yt_cfg.get("destination", {}))
            except Exception as e:
                LogManager.log(f"[{task_id}] Lỗi khi upload YouTube: {e}", "ERROR", "YOUTUBE")

        if upload_to_fb:
            fb_desc = (
                f"🎬 {new_title}\n\n"
                f"🔥 Đón xem trọn bộ review phim ngắn Trung Quốc cực cuốn độc quyền tại fanpage!\n\n"
                f"👉 Bấm Like và Theo Dõi Fanpage để cập nhật ngay những tập phim mới nhất mỗi ngày!\n\n"
                f"#reviewphim #phimhay #phimngantrungquoc #tomtatphim #haomon #xuhuong"
            )
            action_desc = f"Hẹn giờ đăng ({slot_vn_str})" if is_scheduled else "Đăng ngay công khai"
            LogManager.log(f"[{task_id}] Đang tải phim review lên Facebook [{action_desc}]...", "INFO", "FACEBOOK")
            try:
                fb_res = FacebookUploader.upload(
                    video_path=processed_video,
                    title=new_title,
                    description=fb_desc,
                    thumbnail_path=thumb_path,
                    config=fb_cfg.get("destination", {}),
                    scheduled_publish_time=fb_schedule_ts
                )
                fb_success = fb_res.get("success", False) if isinstance(fb_res, dict) else False
                if fb_success:
                    uploaded_fb_id = fb_res.get("video_id")
                    LogManager.log(f"[{task_id}] Upload Facebook thành công! Video ID: {uploaded_fb_id}", "SUCCESS", "FACEBOOK")
                    pin_comment = random.choice(FACEBOOK_COMMENTS)
                    FacebookUploader.add_comment(uploaded_fb_id, pin_comment, fb_cfg.get("destination", {}))
            except Exception as e:
                LogManager.log(f"[{task_id}] Lỗi khi upload Facebook: {e}", "ERROR", "FACEBOOK")

        # KHÔNG TẠO SHORTS (Shorts disabled)
        # BƯỚC 8: LƯU LỊCH SỬ & ĐỒNG BỘ GIT
        if yt_success or fb_success:
            extra_meta = {
                "raw_title": raw_title,
                "scheduled_utc": yt_publish_at,
                "scheduled_vn": slot_vn_str
            }
            HistoryManager.record_processed(unique_id, new_title, yt_uploaded=yt_success, fb_uploaded=fb_success, extra=extra_meta)
            HistoryManager.sync_to_git(f"chore: save china review video {unique_id} [skip ci]")
            LogManager.log(f"[{task_id}] Đã hoàn tất đăng video độc quyền ({slot_vn_str if is_scheduled else 'ngay lập tức'}) và lưu lịch sử!", "SUCCESS", "CHINA_RAW")
            return True
        else:
            LogManager.log(f"[{task_id}] Cả hai nền tảng upload đều thất bại.", "ERROR", "CHINA_RAW")
            return False

    finally:
        for p in temp_files:
            if p and os.path.exists(p):
                try: os.remove(p)
                except Exception: pass

def run_headless_pipeline():
    """
    Quy trình siêu tối ưu:
    1. Quét danh sách các kênh nguồn duy nhất (không quét trùng lặp).
    2. Kiểm tra bộ nhớ lịch sử vĩnh viễn (storage/processed_history.json) & kênh đích YouTube -> Chống reup trùng 100%.
    3. TẢI 1 LẦN DUY NHẤT.
    4. RENDER LÁCH BẢN QUYỀN 1 LẦN DUY NHẤT (Khử logo toàn màn hình + tốc độ chuẩn + âm thanh AAC 48k).
    5. ĐĂNG ĐỒNG THỜI LÊN CẢ YOUTUBE VÀ FACEBOOK.
    6. ĐỒNG BỘ GIT NGAY LẬP TỨC & XÓA SẠCH CACHE TẠM.
    """
    LogManager.log("=== BẮT ĐẦU CHU KỲ QUÉT & REUP ĐỒNG THỜI 24/7 (CHỐNG TRÙNG TUYỆT ĐỐI) ===", "INFO", "WORKER")
    cfg = ConfigManager.load()
    general_cfg = cfg.get("general", {})
    yt_cfg = cfg.get("youtube", {})
    fb_cfg = cfg.get("facebook", {})

    # KIỂM SOÁT TẦN SUẤT: Giới hạn tối đa video/ngày để bảo vệ thuật toán kênh tránh bị bóp reach
    max_daily_uploads = general_cfg.get("max_daily_uploads", 2)
    today_uploaded = HistoryManager.get_today_uploaded_count()
    if today_uploaded >= max_daily_uploads:
        LogManager.log(f"Hôm nay đã đăng {today_uploaded}/{max_daily_uploads} video (đạt giới hạn vàng). Tạm dừng đăng thêm để bảo vệ thuật toán kênh.", "INFO", "WORKER")
        return

    # Lấy thông tin các video đã có trên kênh đích YouTube để bảo vệ đa lớp chống trùng lặp tuyệt đối
    destination_info = get_destination_channel_uploaded_info(cfg, max_results=50)
    destination_titles = destination_info.get("titles", [])
    destination_ref_ids = destination_info.get("ref_ids", set())
    LogManager.log(f"Đã nạp {len(destination_titles)} video và {len(destination_ref_ids)} RefID đã có trên kênh YouTube đích để kiểm tra trùng lặp.", "INFO", "WORKER")

    # CHỌN CHẾ ĐỘ NGUỒN PHIM:
    source_mode = general_cfg.get("source_mode", "china_raw")
    if source_mode == "china_raw":
        success = run_china_raw_pipeline(cfg, destination_titles, destination_ref_ids)
        clean_all_temp_cache()
        LogManager.log(f"=== HOÀN TẤT CHU KỲ PHONG CÁCH B (Thành công: {success}) ===", "SUCCESS" if success else "INFO", "WORKER")
        return

    # Tập hợp danh sách các kênh nguồn duy nhất từ cấu hình YouTube và Facebook
    all_sources = []
    seen_channel_ids = set()

    for platform_cfg in [yt_cfg, fb_cfg]:
        for s in platform_cfg.get("sources", []):
            if not s.get("enabled", True):
                continue
            channel_id = ChannelMonitor.extract_youtube_channel_id(s.get("id") or s.get("url", ""))
            if channel_id and channel_id not in seen_channel_ids:
                seen_channel_ids.add(channel_id)
                all_sources.append({
                    "channel_id": channel_id,
                    "name": s.get("name", channel_id),
                    "url": s.get("url", f"https://www.youtube.com/channel/{channel_id}"),
                    "last_video_id": s.get("last_video_id", "")
                })

    if not all_sources:
        LogManager.log("Không có kênh nguồn nào được bật.", "WARNING", "WORKER")
        return

    # Quét từng kênh nguồn
    for source_info in all_sources:
        channel_id = source_info["channel_id"]
        channel_name = source_info["name"]
        last_processed_vid = source_info.get("last_video_id", "")

        try:
            videos = get_channel_latest_videos(channel_id, cfg, max_results=15)
            if not videos:
                LogManager.log(f"Không quét được video nào từ kênh [{channel_name}].", "WARNING", "WORKER")
                continue

            for vid_info in videos:
                video_id = vid_info["id"]
                video_title = vid_info["title"]
                video_url = vid_info["url"]

                # LỚP 0: BỎ QUA VIDEO CHIA PHẦN / NHIỀU TẬP (Chỉ chọn phim trọn bộ để tối ưu view và giữ chân người xem)
                is_part, part_label = AIRewriter.is_multi_part_video(video_title)
                if is_part:
                    LogManager.log(f"Video [{video_title}] là video chia phần ({part_label}) -> BỎ QUA để chỉ chọn phim trọn bộ.", "INFO", "WORKER")
                    HistoryManager.record_processed(video_id, video_title, yt_uploaded=False, fb_uploaded=False, extra={"skipped": True, "reason": f"Multi-part video ({part_label})"})
                    continue

                # LỚP 1: Kiểm tra lịch sử persistent JSON
                if HistoryManager.is_processed(video_id):
                    LogManager.log(f"Video [{video_title}] (ID: {video_id}) đã có trong lịch sử đã xử lý -> BỎ QUA.", "INFO", "WORKER")
                    continue

                # LỚP 2: Kiểm tra RefID trực tiếp trên kênh đích YouTube (Chống trùng ngay cả khi mất file lịch sử)
                if video_id in destination_ref_ids:
                    LogManager.log(f"Video [{video_title}] (ID: {video_id}) đã có RefID trên kênh đích YouTube -> Đánh dấu lịch sử và BỎ QUA.", "WARNING", "WORKER")
                    HistoryManager.record_processed(video_id, video_title, yt_uploaded=False, fb_uploaded=False, extra={"skipped": True, "reason": "Already exists on destination channel"})
                    continue

                # LỚP 3: Kiểm tra đối chiếu tiêu đề thông minh với danh sách video đã tồn tại trên kênh đích YouTube
                clean_test_title = AIRewriter.clean_and_format_title(video_title)
                is_duplicate = False
                for dt in destination_titles:
                    if is_title_duplicate(clean_test_title, dt) or is_title_duplicate(video_title, dt):
                        LogManager.log(f"Video [{video_title}] khớp tiêu đề với video đã có ('{dt}') -> Đánh dấu lịch sử và BỎ QUA.", "WARNING", "WORKER")
                        HistoryManager.record_processed(video_id, video_title, yt_uploaded=False, fb_uploaded=False, extra={"skipped": True, "reason": f"Trùng tiêu đề với '{dt}'"})
                        is_duplicate = True
                        break

                if is_duplicate:
                    continue

                # Nếu là video hoàn toàn mới, bắt đầu quy trình Tải 1 lần -> Render 1 lần -> Đăng đồng thời
                LogManager.log(f"Phát hiện video MỚI từ [{channel_name}]: '{video_title}' (ID: {video_id})", "INFO", "WORKER")

                handled = process_and_upload_simultaneously(
                    video_id=video_id,
                    source_url=video_url,
                    orig_title=video_title,
                    upload_to_yt=yt_cfg.get("enabled", True),
                    upload_to_fb=fb_cfg.get("enabled", True),
                    cfg=cfg
                )

                # Cập nhật last_video_id đồng bộ cho cả YouTube và Facebook
                if handled:
                    destination_titles.append(video_title)
                    destination_titles.append(AIRewriter.clean_and_format_title(video_title))
                    destination_ref_ids.add(video_id)
                    for s in yt_cfg.get("sources", []):
                        if ChannelMonitor.extract_youtube_channel_id(s.get("id") or s.get("url", "")) == channel_id:
                            s["last_video_id"] = video_id
                    for s in fb_cfg.get("sources", []):
                        if ChannelMonitor.extract_youtube_channel_id(s.get("id") or s.get("url", "")) == channel_id:
                            s["last_video_id"] = video_id
                    ConfigManager.save(cfg)
                    LogManager.log(f"Đã hoàn thành và đồng bộ trạng thái video ID [{video_id}] cho kênh [{channel_name}]", "SUCCESS", "WORKER")
                    break  # Mỗi kênh nguồn chỉ xử lý 1 video mới trong 1 chu kỳ quét

        except Exception as e:
            LogManager.log(f"Lỗi khi quét kênh {channel_name}: {e}", "ERROR", "WORKER")

    # Dọn dẹp cache tổng thể sau khi hoàn tất
    clean_all_temp_cache()

    # (Đã tắt chức năng tự động tương tác và bình luận theo yêu cầu)

    LogManager.log("=== HOÀN TẤT CHU KỲ QUÉT & REUP ĐỒNG THỜI ===", "SUCCESS", "WORKER")

def process_and_upload_simultaneously(
    video_id: str,
    source_url: str,
    orig_title: str,
    upload_to_yt: bool,
    upload_to_fb: bool,
    cfg: Dict[str, Any],
    bypass_duration_check: bool = False
) -> bool:
    task_id = f"auto_{int(time.time())}"
    LogManager.log(f"Bắt đầu chu trình xử lý siêu tốc ID [{task_id}] từ {source_url}", "INFO", "WORKER")

    general_cfg = cfg.get("general", {})
    yt_cfg = cfg.get("youtube", {})
    fb_cfg = cfg.get("facebook", {})

    # BƯỚC 1: TẢI VIDEO 1 LẦN DUY NHẤT (Có bộ lọc 30 phút - 3 tiếng, trừ khi được chỉ định chạy thủ công)
    min_mins = 0 if bypass_duration_check else general_cfg.get("min_duration_minutes", 30)
    max_mins = 600 if bypass_duration_check else general_cfg.get("max_duration_minutes", 180)
    min_secs = int(min_mins * 60)
    max_secs = int(max_mins * 60)

    dl_res = VideoDownloader.download(
        url=source_url,
        task_id=task_id,
        proxy=general_cfg.get("proxy"),
        min_duration_seconds=min_secs,
        max_duration_seconds=max_secs
    )

    # Nếu video bị bỏ qua do thời lượng (< 30m hoặc > 3h)
    if dl_res.get("skipped"):
        reason = dl_res.get("error", "Thời lượng không nằm trong khoảng 30m - 180m")
        LogManager.log(f"Bỏ qua video [{orig_title}]: {reason}. Đánh dấu lịch sử để không quét lại.", "WARNING", "DOWNLOADER")
        HistoryManager.record_processed(video_id, orig_title, yt_uploaded=False, fb_uploaded=False, extra={"skipped": True, "reason": reason})
        HistoryManager.sync_to_git(f"chore: skip duration video {video_id} [skip ci]")
        return True

    if not dl_res.get("success"):
        LogManager.log(f"Tải video thất bại: {dl_res.get('error')}", "ERROR", "DOWNLOADER")
        return False

    raw_video = dl_res["video_path"]
    raw_thumb = dl_res.get("thumbnail_path")
    actual_title = dl_res.get("title", orig_title)

    gemini_key = general_cfg.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
    openai_key = general_cfg.get("openai_api_key") or os.getenv("OPENAI_API_KEY")

    try:
        # BƯỚC 2: AI VIẾT LẠI TIÊU ĐỀ 1 LẦN DUY NHẤT (Chuẩn hóa tên phim + Phần X lên đầu)
        new_title = actual_title
        meta_rules = yt_cfg.get("metadata_rules", fb_cfg.get("metadata_rules", {}))
        if meta_rules.get("rewrite_title", True):
            new_title = AIRewriter.rewrite_title(
                actual_title,
                gemini_key=gemini_key,
                openai_key=openai_key
            )
            prefix = meta_rules.get("title_prefix", "")
            suffix = meta_rules.get("title_suffix", "")
            new_title = f"{prefix}{new_title}{suffix}".strip()

        # BƯỚC 3: THIẾT KẾ THUMBNAIL 1 LẦN DUY NHẤT (Ưu tiên poster gốc điện ảnh 1280x720)
        thumb_path = None
        if meta_rules.get("generate_thumbnail", True):
            thumb_path = ThumbnailGenerator.create_thumbnail(
                video_path=raw_video,
                fallback_image_path=raw_thumb,
                title_text=new_title,
                task_id=task_id,
                style=meta_rules.get("thumbnail_style", "modern_yellow")
            )

        # BƯỚC 4: RENDER FFMPEG LÁCH BẢN QUYỀN NÂNG CAO (LẬT GƯƠNG + TỐC ĐỘ + ĐỔI MÃ HASH TOÀN DIỆN)
        # Bộ luật tối tân chống quét Content ID toàn cầu tuyệt đối:
        # - hflip=True (Lật gương hình ảnh: phá vỡ 100% ma trận khớp ảnh Content ID)
        # - remove_logo=True (Khử logo toàn màn hình)
        # - speed=1.045 (Tăng tốc độ video và âm thanh)
        # - pitch_shift=True (Biến đổi cao độ âm thanh)
        # - crop_percent=3.5 (Cắt viền phá tỷ lệ khung hình gốc)
        # - color_boost=True (Tăng tương phản & màu sắc thay đổi hash điểm ảnh)
        user_bypass = yt_cfg.get("bypass_rules", {})
        combined_rules = {
            "hflip": user_bypass.get("hflip", True),
            "remove_logo": user_bypass.get("remove_logo", True),
            "speed": float(user_bypass.get("speed", 1.05)),
            "pitch_shift": user_bypass.get("pitch_shift", True),
            "add_bgm": user_bypass.get("add_bgm", True),
            "bgm_volume": float(user_bypass.get("bgm_volume", 0.12)),
            "crop_percent": float(user_bypass.get("crop_percent", 4.5)),
            "color_boost": user_bypass.get("color_boost", True),
            "change_fps": user_bypass.get("change_fps", True),
            "target_resolution": user_bypass.get("target_resolution", "720p"),
            "cut_intro_seconds": float(user_bypass.get("cut_intro_seconds", 2.5)),
            "preset": "superfast" if bypass_duration_check else "veryfast"
        }

        processed_video = VideoProcessor.process(
            input_path=raw_video,
            task_id=task_id,
            rules=combined_rules
        )

        # BƯỚC 5: ĐĂNG ĐỒNG THỜI LÊN CẢ YOUTUBE VÀ FACEBOOK
        yt_success = False
        fb_success = False
        uploaded_yt_id = None
        uploaded_fb_id = None

        # 5.1 Đăng YouTube
        if upload_to_yt:
            # Tạo mô tả chuẩn SEO YouTube và bộ 20+ thẻ tags đề xuất
            seo_tags = AIRewriter.get_recommended_tags(new_title)
            clean_yt_desc = AIRewriter.generate_seo_description(
                title=new_title,
                orig_title=actual_title,
                video_id=video_id,
                gemini_key=gemini_key,
                openai_key=openai_key
            )
            LogManager.log(f"[{task_id}] Đang tải lên YouTube kèm {len(seo_tags)} thẻ tags SEO...", "INFO", "YOUTUBE")
            try:
                yt_res = YouTubeUploader.upload(
                    video_path=processed_video,
                    title=new_title,
                    description=clean_yt_desc,
                    thumbnail_path=thumb_path,
                    config=yt_cfg.get("destination", {}),
                    tags=seo_tags
                )
                yt_success = yt_res.get("success", False) if isinstance(yt_res, dict) else False
                if yt_success:
                    uploaded_yt_id = yt_res.get("video_id")
                    LogManager.log(f"[{task_id}] Upload YouTube thành công! Video ID: {uploaded_yt_id}", "SUCCESS", "YOUTUBE")
                else:
                    LogManager.log(f"[{task_id}] Upload YouTube không thành công: {yt_res}", "WARNING", "YOUTUBE")
            except Exception as e:
                LogManager.log(f"[{task_id}] Lỗi khi upload YouTube: {e}", "ERROR", "YOUTUBE")

        # 5.2 Đăng Facebook
        if upload_to_fb:
            clean_fb_desc = (
                f"🎬 {new_title}\n\n"
                f"🔥 Đón xem trọn bộ phim kịch tính cực cuốn! Cùng bình luận cảm nghĩ của bạn về diễn biến tập này nhé.\n\n"
                f"👉 Nhớ bấm Like và Theo Dõi Fanpage để cập nhật ngay những tập phim mới nhất mỗi ngày!\n\n"
                f"#reviewphim #phimhay #phimngantrungquoc #tomtatphim #reels #xuhuong #trending"
            )
            LogManager.log(f"[{task_id}] Đang tải lên Facebook...", "INFO", "FACEBOOK")
            try:
                fb_res = FacebookUploader.upload(
                    video_path=processed_video,
                    title=new_title,
                    description=clean_fb_desc,
                    thumbnail_path=thumb_path,
                    config=fb_cfg.get("destination", {})
                )
                fb_success = fb_res.get("success", False) if isinstance(fb_res, dict) else False
                if fb_success:
                    uploaded_fb_id = fb_res.get("video_id")
                    LogManager.log(f"[{task_id}] Upload Facebook thành công! Video ID: {uploaded_fb_id}", "SUCCESS", "FACEBOOK")
                else:
                    LogManager.log(f"[{task_id}] Upload Facebook không thành công: {fb_res}", "WARNING", "FACEBOOK")
            except Exception as e:
                LogManager.log(f"[{task_id}] Lỗi khi upload Facebook: {e}", "ERROR", "FACEBOOK")

        # 5.3 TỰ ĐỘNG TẠO & ĐĂNG VIDEO SHORTS / REELS (Chỉ khi được bật trong cấu hình)
        shorts_list = []
        if general_cfg.get("enable_shorts", False):
            try:
                from core.shorts_generator import ShortsGenerator
                shorts_list = ShortsGenerator.extract_shorts(
                    processed_video_path=processed_video,
                    base_title=new_title,
                    task_id=task_id,
                    count=2,
                    clip_duration=50,
                    gemini_key=gemini_key,
                    openai_key=openai_key
                )
                for s_idx, short_item in enumerate(shorts_list):
                    s_path = short_item["path"]
                    s_title = short_item["title"]

                    # 1. Đăng lên YouTube Shorts
                    if upload_to_yt and uploaded_yt_id:
                        short_yt_title = f"{s_title} #Shorts #ReviewPhim #PhimHay"
                        if len(short_yt_title) > 100:
                            short_yt_title = short_yt_title[:100].rsplit(' ', 1)[0]
                        short_yt_desc = (
                            f"🎬 {s_title}\n\n"
                            f"#Shorts #ReviewPhim #PhimHay #XuHuong #Trending #PhimNgan"
                        )
                        short_tags = ["shorts", "reviewphim", "phimhay", "xuhuong", "phimngan", "trending"]
                        s_yt_res = YouTubeUploader.upload(
                            video_path=s_path,
                            title=short_yt_title,
                            description=short_yt_desc,
                            thumbnail_path=None,
                            config=yt_cfg.get("destination", {}),
                            tags=short_tags
                        )
                        s_yt_id = s_yt_res.get("video_id") if isinstance(s_yt_res, dict) else None
                        if s_yt_id:
                            LogManager.log(f"[{task_id}] Đã đăng YouTube Short #{s_idx+1}: {s_yt_id}", "SUCCESS", "SHORTS")
                            if s_idx == 0:
                                pin_comment = (
                                    f"🎬 XEM TRỌN BỘ FULL TẬP DÀI:\n"
                                    f"👉 Bấm vào kênh @CoolMeoPhim để xem trọn bộ tập dài mới nhất nhé!\n"
                                    f"🔗 Link: https://www.youtube.com/watch?v={uploaded_yt_id}"
                                )
                            else:
                                pin_comment = (
                                    f"🎬 Xem trọn bộ diễn biến tập dài:\n"
                                    f"👉 Bấm vào kênh @CoolMeoPhim để xem video dài ở đầu trang nhé!\n"
                                    f"🔗 Link: https://www.youtube.com/watch?v={uploaded_yt_id}"
                                )
                            YouTubeUploader.add_comment(s_yt_id, pin_comment, yt_cfg.get("destination", {}))

                    # 2. Đăng lên Facebook Reels
                    if upload_to_fb:
                        fb_dest_reel = dict(fb_cfg.get("destination", {}))
                        fb_dest_reel["post_as_reel"] = True
                        short_fb_desc = (
                            f"🎬 {s_title}\n\n"
                            f"#reels #reviewphim #xuhuong #phimhay #phimngan"
                        )
                        s_fb_res = FacebookUploader.upload(
                            video_path=s_path,
                            title=s_title,
                            description=short_fb_desc,
                            thumbnail_path=None,
                            config=fb_dest_reel
                        )
                        s_fb_id = s_fb_res.get("video_id") if isinstance(s_fb_res, dict) else None
                        if s_fb_id:
                            LogManager.log(f"[{task_id}] Đã đăng Facebook Reel #{s_idx+1}: {s_fb_id}", "SUCCESS", "SHORTS")
                            if uploaded_fb_id:
                                if s_idx == 0:
                                    fb_pin_comment = f"👉 XEM TRỌN BỘ TẬP DÀI TẠI ĐÂY: https://www.facebook.com/watch/?v={uploaded_fb_id}"
                                else:
                                    fb_pin_comment = f"🎬 Xem trọn bộ diễn biến tập dài tại đây: https://www.facebook.com/watch/?v={uploaded_fb_id}"
                                FacebookUploader.add_comment(s_fb_id, fb_pin_comment, fb_cfg.get("destination", {}))
            except Exception as ex_shorts:
                LogManager.log(f"[{task_id}] Lỗi trong tiến trình tạo Shorts: {ex_shorts}", "WARNING", "SHORTS")
            finally:
                for s_item in shorts_list:
                    sp = s_item.get("path")
                    if sp and os.path.exists(sp):
                        try:
                            os.remove(sp)
                        except Exception:
                            pass

        if yt_success or fb_success:
            # Lưu ngay vào lịch sử và push Git ngay lập tức
            HistoryManager.record_processed(video_id, new_title, yt_uploaded=yt_success, fb_uploaded=fb_success)
            HistoryManager.sync_to_git(f"chore: save reup video {video_id} [skip ci]")
            LogManager.log(f"[{task_id}] Đã hoàn tất đăng đồng thời và lưu trữ lịch sử thành công!", "SUCCESS", "WORKER")
            return True
        else:
            LogManager.log(f"[{task_id}] Cả hai nền tảng upload đều thất bại.", "ERROR", "WORKER")
            return False

    finally:
        # BƯỚC 6: XÓA SẠCH VIDEO GỐC VÀ VIDEO TẠM NGAY LẬP TỨC
        for p in [raw_video, raw_thumb]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
        processed_video_expected = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "temp", f"processed_{task_id}.mp4"))
        if os.path.exists(processed_video_expected):
            try: os.remove(processed_video_expected)
            except Exception: pass

def process_single_video_url(target_url: str) -> bool:
    """
    Quy trình xử lý và đăng ngay một video cụ thể theo URL chỉ định:
    1. Trích xuất video_id và tiêu đề từ URL.
    2. Bỏ qua giới hạn thời lượng 3 tiếng (hỗ trợ phim dài tới 10 tiếng).
    3. Tải 1 lần -> Render lách bản quyền -> Đăng lên YouTube & Facebook -> Lưu lịch sử.
    """
    LogManager.log(f"=== BẮT ĐẦU XỬ LÝ VIDEO CHỈ ĐỊNH: {target_url} ===", "INFO", "WORKER")
    cfg = ConfigManager.load()
    yt_cfg = cfg.get("youtube", {})
    fb_cfg = cfg.get("facebook", {})

    # Trích xuất video_id
    video_id = None
    m = re.search(r'(?:v=|/embed/|/watch\?v=|youtu\.be/|/v/)([a-zA-Z0-9_-]{11})', target_url)
    if m:
        video_id = m.group(1)
    else:
        video_id = target_url.strip()

    orig_title = "Video Chỉ Định"
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({'quiet': True, 'noplaylist': True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            orig_title = info.get("title", orig_title)
            video_id = info.get("id", video_id)
    except Exception as e:
        LogManager.log(f"Không thể lấy metadata video: {e}", "WARNING", "WORKER")

    LogManager.log(f"Video mục tiêu: [{orig_title}] (ID: {video_id})", "INFO", "WORKER")
    success = process_and_upload_simultaneously(
        video_id=video_id,
        source_url=f"https://www.youtube.com/watch?v={video_id}",
        orig_title=orig_title,
        upload_to_yt=yt_cfg.get("enabled", True),
        upload_to_fb=fb_cfg.get("enabled", True),
        cfg=cfg,
        bypass_duration_check=True
    )
    clean_all_temp_cache()
    LogManager.log(f"=== HOÀN TẤT XỬ LÝ VIDEO CHỈ ĐỊNH (Thành công: {success}) ===", "SUCCESS" if success else "ERROR", "WORKER")
    return success

if __name__ == "__main__":
    target_url = os.environ.get("TARGET_VIDEO_URL", "").strip()
    if not target_url and len(sys.argv) > 1:
        for i, arg in enumerate(sys.argv[1:]):
            if arg in ["--url", "--video-url", "-u"] and (i + 1) < len(sys.argv) - 1:
                target_url = sys.argv[i + 2].strip()
                break
            elif "youtube.com" in arg or "youtu.be" in arg:
                target_url = arg.strip()
                break

    if target_url:
        process_single_video_url(target_url)
    else:
        run_headless_pipeline()
