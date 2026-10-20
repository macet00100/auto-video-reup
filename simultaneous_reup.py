import os
import sys
import time
import random
import re
import feedparser
import yt_dlp
from datetime import datetime

from core.config import ConfigManager
from core.task_queue import LogManager
from core.downloader import VideoDownloader
from core.processor import VideoProcessor
from core.ai_rewriter import AIRewriter
from core.thumbnail import ThumbnailGenerator
from core.uploader_yt import YouTubeUploader
from core.uploader_fb import FacebookUploader

def run_simultaneous_reup():
    sys.stdout.reconfigure(encoding='utf-8')
    LogManager.log("==================================================================", "INFO", "WORKER")
    LogManager.log("BẮT ĐẦU QUY TRÌNH REUP ĐỒNG THỜI LÊN CẢ YOUTUBE VÀ FACEBOOK", "INFO", "WORKER")
    LogManager.log("==================================================================", "INFO", "WORKER")

    cfg = ConfigManager.load()
    yt_cfg = cfg.get("youtube", {})
    fb_cfg = cfg.get("facebook", {})
    general_cfg = cfg.get("general", {})

    channels = yt_cfg.get("sources", [])
    if not channels:
        LogManager.log("Không tìm thấy kênh nguồn nào trong cấu hình!", "ERROR", "WORKER")
        return

    LogManager.log(f"Đang quét danh sách video gần nhất từ {len(channels)} kênh nguồn...", "INFO", "MONITOR")
    eligible_candidates = []

    # Danh sách các kênh nguồn
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for ch in channels:
            ch_id = ch.get("id")
            ch_name = ch.get("name", ch_id)
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={ch_id}"

            try:
                feed = feedparser.parse(rss_url)
                if not feed.entries:
                    continue

                # Lấy 3 video gần nhất của mỗi kênh để kiểm tra
                for entry in feed.entries[:3]:
                    v_id = getattr(entry, "yt_videoid", None)
                    if not v_id:
                        m = re.search(r"v=([a-zA-Z0-9_-]+)", entry.link)
                        if m: v_id = m.group(1)

                    if not v_id:
                        continue

                    v_url = f"https://www.youtube.com/watch?v={v_id}"
                    v_title = entry.title

                    # Kiểm tra thời lượng bằng yt-dlp
                    try:
                        info = ydl.extract_info(v_url, download=False)
                        duration = info.get("duration") or 0
                        mins = duration / 60.0

                        # Điều kiện: 30 phút <= duration <= 180 phút
                        if 1800 <= duration <= 10800:
                            eligible_candidates.append({
                                "id": v_id,
                                "url": v_url,
                                "title": v_title,
                                "channel_name": ch_name,
                                "duration_mins": round(mins, 1),
                                "duration_secs": duration
                            })
                            LogManager.log(f"-> Thỏa mãn điều kiện: [{ch_name}] '{v_title}' ({round(mins, 1)} phút)", "INFO", "FILTER")
                        else:
                            LogManager.log(f"-> Bỏ qua (Thời lượng {round(mins, 1)}m không thuộc 30m-180m): '{v_title}'", "WARNING", "FILTER")
                    except Exception as err:
                        LogManager.log(f"Không thể lấy info video {v_id}: {err}", "WARNING", "MONITOR")

            except Exception as e:
                LogManager.log(f"Lỗi đọc RSS kênh {ch_name}: {e}", "WARNING", "MONITOR")

    if not eligible_candidates:
        LogManager.log("Không tìm thấy video nào thỏa mãn điều kiện 30 phút - 3 tiếng!", "ERROR", "WORKER")
        return

    # Random chọn 1 video từ các ứng viên đạt chuẩn
    selected = random.choice(eligible_candidates)
    LogManager.log(f">>> RANDOM ĐÃ CHỌN: [{selected['channel_name']}] '{selected['title']}' ({selected['duration_mins']} phút)", "SUCCESS", "WORKER")

    task_id = f"simul_{int(time.time())}"
    source_url = selected["url"]
    orig_title = selected["title"]

    # BƯỚC 1: TẢI VIDEO GỐC
    LogManager.log(f"[{task_id}] Bước 1/5: Bắt đầu tải video gốc từ YouTube...", "INFO", "DOWNLOAD")
    dl_res = VideoDownloader.download(
        url=source_url,
        task_id=task_id,
        proxy=general_cfg.get("proxy"),
        min_duration_seconds=1800,
        max_duration_seconds=10800
    )

    if not dl_res.get("success"):
        LogManager.log(f"Tải video thất bại: {dl_res.get('error')}", "ERROR", "DOWNLOAD")
        return

    raw_video = dl_res["video_path"]
    raw_thumb = dl_res.get("thumbnail_path")
    actual_title = dl_res.get("title", orig_title)

    try:
        # BƯỚC 2: AI VIẾT LẠI TIÊU ĐỀ
        LogManager.log(f"[{task_id}] Bước 2/5: AI Gemini viết lại tiêu đề thu hút & chuẩn SEO...", "INFO", "AI")
        ai_title = AIRewriter.rewrite_title(
            actual_title,
            gemini_key=general_cfg.get("gemini_api_key"),
            openai_key=general_cfg.get("openai_api_key")
        )
        # Tạo 2 tiêu đề phù hợp từng nền tảng
        yt_suffix = yt_cfg.get("metadata_rules", {}).get("title_suffix", " #reviewphim #phimhay #review #viral")
        fb_suffix = fb_cfg.get("metadata_rules", {}).get("title_suffix", " #reviewphim #phimhay #xuhuong #phimmoi")

        title_yt = f"{ai_title}{yt_suffix}".strip()
        title_fb = f"{ai_title}{fb_suffix}".strip()

        LogManager.log(f"Tiêu đề YouTube: {title_yt}", "INFO", "YOUTUBE")
        LogManager.log(f"Tiêu đề Facebook: {title_fb}", "INFO", "FACEBOOK")

        # BƯỚC 3: TẠO THUMBNAIL TỰ ĐỘNG
        LogManager.log(f"[{task_id}] Bước 3/5: Tạo thumbnail từ frame phim thực tế...", "INFO", "THUMBNAIL")
        thumb_path = ThumbnailGenerator.create_thumbnail(
            video_path=raw_video,
            fallback_image_path=raw_thumb,
            title_text=ai_title,
            task_id=task_id,
            style=yt_cfg.get("metadata_rules", {}).get("thumbnail_style", "modern_yellow")
        )

        # BƯỚC 4: RENDER FFMPEG BIẾN ĐỔI VIDEO (CHỐNG BẢN QUYỀN)
        LogManager.log(f"[{task_id}] Bước 4/5: FFmpeg transcode (Xóa logo, Tốc độ 1.03x, Đổi cao độ âm, KHÔNG lật sub)...", "INFO", "FFMPEG")
        bypass_rules = yt_cfg.get("bypass_rules", {
            "hflip": False,
            "remove_logo": True,
            "logo_position": "top-left",
            "speed": 1.03,
            "pitch_shift": True,
            "crop_percent": 3,
            "color_boost": True,
            "change_fps": True,
            "target_resolution": "720p"
        })
        processed_video = VideoProcessor.process(
            input_path=raw_video,
            task_id=task_id,
            rules=bypass_rules
        )

        # BƯỚC 5: ĐĂNG TẢI LÊN CẢ YOUTUBE VÀ FACEBOOK
        LogManager.log(f"[{task_id}] Bước 5/5: Bắt đầu đăng tải đồng thời lên cả 2 nền tảng...", "INFO", "UPLOAD")

        # 5.1 ĐĂNG YOUTUBE
        LogManager.log(f"-> Đang đăng tải lên YouTube (Kênh: Cool Meo Phim)...", "INFO", "YOUTUBE")
        desc_yt = (
            f"{title_yt}\n\n"
            f"Chào mừng các bạn đã đến với kênh! Hãy bấm Like, Đăng Ký Kênh và Nhấn Chuông thông báo để không bỏ lỡ những video mới và hay nhất mỗi ngày nhé!\n\n"
            f"Cảm ơn mọi người đã luôn đồng hành và ủng hộ kênh!\n\n"
            f"#review #phimhay #reviewphim #viral #trending #phimmoi"
        )
        yt_res = YouTubeUploader.upload(
            video_path=processed_video,
            title=title_yt,
            description=desc_yt,
            thumbnail_path=thumb_path,
            config=yt_cfg.get("destination", {})
        )

        # 5.2 ĐĂNG FACEBOOK
        LogManager.log(f"-> Đang đăng tải lên Facebook Fanpage (Film Trung Quốc)...", "INFO", "FACEBOOK")
        desc_fb = (
            f"{title_fb}\n\n"
            f"Mọi người xem video thấy hay nhớ bấm Like và Follow Fanpage để đón xem những tập tiếp theo nhé!\n\n"
            f"#film #reviewphim #phimhay #reels #xuhuong #trending"
        )
        fb_res = FacebookUploader.upload(
            video_path=processed_video,
            title=title_fb,
            description=desc_fb,
            config=fb_cfg.get("destination", {})
        )

        LogManager.log("==================================================================", "SUCCESS", "WORKER")
        LogManager.log("KẾT QUẢ ĐĂNG TẢI ĐỒNG THỜI:", "SUCCESS", "WORKER")
        if yt_res.get("success"):
            yt_link = f"https://www.youtube.com/watch?v={yt_res.get('video_id')}"
            LogManager.log(f"✅ YOUTUBE THÀNH CÔNG: {yt_link}", "SUCCESS", "YOUTUBE")
        else:
            LogManager.log(f"❌ YOUTUBE THẤT BẠI: {yt_res.get('error')}", "ERROR", "YOUTUBE")

        if fb_res.get("success"):
            fb_id = fb_res.get('video_id')
            LogManager.log(f"✅ FACEBOOK THÀNH CÔNG: Post ID = {fb_id}", "SUCCESS", "FACEBOOK")
        else:
            LogManager.log(f"❌ FACEBOOK THẤT BẠI: {fb_res.get('error')}", "ERROR", "FACEBOOK")
        LogManager.log("==================================================================", "SUCCESS", "WORKER")

    finally:
        # Dọn dẹp video tạm
        for p in [raw_video, raw_thumb]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except Exception: pass
        processed_video_expected = os.path.abspath(os.path.join(os.path.dirname(__file__), "storage", "temp", f"processed_{task_id}.mp4"))
        if os.path.exists(processed_video_expected):
            try: os.remove(processed_video_expected)
            except Exception: pass

if __name__ == "__main__":
    run_simultaneous_reup()
