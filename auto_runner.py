import os
import sys
import time
import json
import feedparser
import re
import urllib.request
import random
from typing import Dict, Any, List

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

def is_title_duplicate(title1: str, title2: str, threshold: float = 0.40) -> bool:
    """So sánh 2 tiêu đề video dựa trên từ khóa nội dung đặc trưng (loại bỏ từ nối, đại từ và stop words)."""
    stop_words = {
        "cực", "sốc", "cận", "cảnh", "khám", "phá", "ngay", "full", "hd", "reviewphim", "phimhay",
        "reels", "viral", "shorts", "phần", "tập", "p", "cô", "chàng", "nàng", "ai", "ngờ", "lại",
        "thành", "về", "để", "mà", "còn", "bị", "cho", "của", "những", "các", "và", "với", "trong",
        "được", "làm", "dùng", "ra", "vào", "có", "thì", "ở", "từ", "qua", "sau", "khi", "lên"
    }
    words1 = {w for w in re.findall(r'[\w\d]+', title1.lower()) if w not in stop_words and len(w) > 1}
    words2 = {w for w in re.findall(r'[\w\d]+', title2.lower()) if w not in stop_words and len(w) > 1}
    if not words1 or not words2:
        return False
    inter = words1.intersection(words2)
    min_len = min(len(words1), len(words2))
    similarity = len(inter) / min_len if min_len > 0 else 0
    # Nếu trùng từ 4 từ khóa đặc trưng trở lên HOẶC độ tương đồng >= 40% -> Đều là trùng lặp phim
    return len(inter) >= 4 or similarity >= threshold

def get_channel_latest_videos(channel_id: str, cfg: Dict[str, Any], max_results: int = 5) -> List[Dict[str, str]]:
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

    # Lấy thông tin các video đã có trên kênh đích YouTube để bảo vệ đa lớp chống trùng lặp tuyệt đối
    destination_info = get_destination_channel_uploaded_info(cfg, max_results=50)
    destination_titles = destination_info.get("titles", [])
    destination_ref_ids = destination_info.get("ref_ids", set())
    LogManager.log(f"Đã nạp {len(destination_titles)} video và {len(destination_ref_ids)} RefID đã có trên kênh YouTube đích để kiểm tra trùng lặp.", "INFO", "WORKER")

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
            videos = get_channel_latest_videos(channel_id, cfg, max_results=5)
            if not videos:
                LogManager.log(f"Không quét được video nào từ kênh [{channel_name}].", "WARNING", "WORKER")
                continue

            for vid_info in videos:
                video_id = vid_info["id"]
                video_title = vid_info["title"]
                video_url = vid_info["url"]

                # LỚP 1: Kiểm tra lịch sử persistent JSON
                if HistoryManager.is_processed(video_id):
                    LogManager.log(f"Video [{video_title}] (ID: {video_id}) đã có trong lịch sử đã xử lý -> BỎ QUA.", "INFO", "WORKER")
                    continue

                # LỚP 2: Kiểm tra RefID trực tiếp trên kênh đích YouTube (Chống trùng ngay cả khi mất file lịch sử)
                if video_id in destination_ref_ids:
                    LogManager.log(f"Video [{video_title}] (ID: {video_id}) đã có RefID trên kênh đích YouTube -> Đánh dấu lịch sử và BỎ QUA.", "WARNING", "WORKER")
                    HistoryManager.record_processed(video_id, video_title, yt_uploaded=True, fb_uploaded=True)
                    continue

                # LỚP 3: Kiểm tra đối chiếu tiêu đề thông minh với danh sách video đã tồn tại trên kênh đích YouTube
                clean_test_title = AIRewriter.clean_and_format_title(video_title)
                is_duplicate = False
                for dt in destination_titles:
                    if is_title_duplicate(clean_test_title, dt) or is_title_duplicate(video_title, dt):
                        LogManager.log(f"Video [{video_title}] khớp tiêu đề với video đã có ('{dt}') -> Đánh dấu lịch sử và BỎ QUA.", "WARNING", "WORKER")
                        HistoryManager.record_processed(video_id, video_title, yt_uploaded=True, fb_uploaded=True)
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

    # BƯỚC 7: TỰ ĐỘNG QUÉT & TRẢ LỜI BÌNH LUẬN (AUTO REPLY BOT DÙNG AI GEMINI)
    try:
        LogManager.log("Đang kiểm tra và tự động trả lời bình luận của khán giả qua AI (YouTube & Facebook)...", "INFO", "AUTO_REPLY")
        AutoReplyBot.scan_and_reply_all(cfg)
    except Exception as ex_rep:
        LogManager.log(f"Lỗi khi chạy Auto Reply Bot: {ex_rep}", "WARNING", "AUTO_REPLY")

    LogManager.log("=== HOÀN TẤT CHU KỲ QUÉT & REUP ĐỒNG THỜI ===", "SUCCESS", "WORKER")

def process_and_upload_simultaneously(
    video_id: str,
    source_url: str,
    orig_title: str,
    upload_to_yt: bool,
    upload_to_fb: bool,
    cfg: Dict[str, Any]
) -> bool:
    task_id = f"auto_{int(time.time())}"
    LogManager.log(f"Bắt đầu chu trình xử lý siêu tốc ID [{task_id}] từ {source_url}", "INFO", "WORKER")

    general_cfg = cfg.get("general", {})
    yt_cfg = cfg.get("youtube", {})
    fb_cfg = cfg.get("facebook", {})

    # BƯỚC 1: TẢI VIDEO 1 LẦN DUY NHẤT (Có bộ lọc 30 phút - 3 tiếng)
    min_mins = general_cfg.get("min_duration_minutes", 30)
    max_mins = general_cfg.get("max_duration_minutes", 180)
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

    try:
        # BƯỚC 2: AI VIẾT LẠI TIÊU ĐỀ 1 LẦN DUY NHẤT (Chuẩn hóa tên phim + Phần X lên đầu)
        new_title = actual_title
        meta_rules = yt_cfg.get("metadata_rules", fb_cfg.get("metadata_rules", {}))
        if meta_rules.get("rewrite_title", True):
            new_title = AIRewriter.rewrite_title(
                actual_title,
                gemini_key=general_cfg.get("gemini_api_key"),
                openai_key=general_cfg.get("openai_api_key")
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
        combined_rules = {
            "hflip": True,
            "remove_logo": True,
            "speed": 1.045,
            "pitch_shift": True,
            "crop_percent": 3.5,
            "color_boost": True,
            "change_fps": True,
            "target_resolution": "720p",
            "preset": "veryfast"
        }

        processed_video = VideoProcessor.process(
            input_path=raw_video,
            task_id=task_id,
            rules=combined_rules
        )

        # BƯỚC 5: ĐĂNG ĐỒNG THỜI LÊN CẢ YOUTUBE VÀ FACEBOOK
        yt_success = False
        fb_success = False

        # 5.1 Đăng YouTube
        if upload_to_yt:
            clean_yt_desc = (
                f"{new_title}\n\n"
                f"Chào mừng các bạn đã đến với kênh! Hãy bấm Like, Đăng Ký Kênh và Nhấn Chuông thông báo để không bỏ lỡ những video mới và hay nhất mỗi ngày nhé!\n\n"
                f"Cảm ơn mọi người đã luôn đồng hành và ủng hộ kênh!\n\n"
                f"#review #phimhay #reviewphim #shorts #viral #trending #phimmoi\n\n"
                f"[RefID: {video_id}]"
            )
            LogManager.log(f"[{task_id}] Đang tải lên YouTube...", "INFO", "YOUTUBE")
            try:
                yt_res = YouTubeUploader.upload(
                    video_path=processed_video,
                    title=new_title,
                    description=clean_yt_desc,
                    thumbnail_path=thumb_path,
                    config=yt_cfg.get("destination", {})
                )
                yt_success = yt_res.get("success", False) if isinstance(yt_res, dict) else False
                if yt_success:
                    uploaded_yt_id = yt_res.get("video_id")
                    LogManager.log(f"[{task_id}] Upload YouTube thành công! Video ID: {uploaded_yt_id}", "SUCCESS", "YOUTUBE")
                    if uploaded_yt_id:
                        # 1. Tự động Like video vừa đăng tải
                        YouTubeUploader.like_video(uploaded_yt_id, yt_cfg.get("destination", {}))
                        # 2. Tự động comment lần đầu tăng tương tác
                        yt_cmt = random.choice(YOUTUBE_COMMENTS)
                        YouTubeUploader.add_comment(uploaded_yt_id, yt_cmt, yt_cfg.get("destination", {}))
                else:
                    LogManager.log(f"[{task_id}] Upload YouTube không thành công: {yt_res}", "WARNING", "YOUTUBE")
            except Exception as e:
                LogManager.log(f"[{task_id}] Lỗi khi upload YouTube: {e}", "ERROR", "YOUTUBE")

        # 5.2 Đăng Facebook
        if upload_to_fb:
            clean_fb_desc = (
                f"{new_title}\n\n"
                f"Mọi người xem video thấy hay nhớ bấm Like và Follow Fanpage để đón xem những tập tiếp theo nhé!\n\n"
                f"#film #reviewphim #phimhay #reels #xuhuong #trending"
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
                    if uploaded_fb_id:
                        fb_cmt = random.choice(FACEBOOK_COMMENTS)
                        FacebookUploader.add_comment(uploaded_fb_id, fb_cmt, fb_cfg.get("destination", {}))
                else:
                    LogManager.log(f"[{task_id}] Upload Facebook không thành công: {fb_res}", "WARNING", "FACEBOOK")
            except Exception as e:
                LogManager.log(f"[{task_id}] Lỗi khi upload Facebook: {e}", "ERROR", "FACEBOOK")

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

if __name__ == "__main__":
    run_headless_pipeline()
