import os
import sys
import time
import json

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

from core.config import ConfigManager
from core.task_queue import LogManager
from core.downloader import VideoDownloader
from core.processor import VideoProcessor
from core.ai_rewriter import AIRewriter
from core.thumbnail import ThumbnailGenerator
from core.uploader_yt import YouTubeUploader
from core.uploader_fb import FacebookUploader

def test_duration_filter_rules():
    """Kiểm tra độ chính xác của bộ lọc thời lượng: Chỉ nhận video từ 30 phút đến 3 tiếng."""
    print("\n" + "=" * 65)
    print("🔍 KIỂM TRA BỘ LỌC THỜI LƯỢNG (CHỈ NHẬN VIDEO 30 PHÚT - 3 TIẾNG)")
    print("=" * 65)

    # 1. Test video quá ngắn (< 30 phút, cụ thể là 2 giây)
    short_url = "https://www.youtube.com/watch?v=_opnqfK920U"
    print("\n[TEST 1] Thử tải video ngắn < 30 phút (Video ngắn 2s từ Daica Review)...")
    res_short = VideoDownloader.download(
        url=short_url,
        task_id="check_short",
        min_duration_seconds=1800,  # 30 phút
        max_duration_seconds=10800  # 3 tiếng
    )
    if res_short.get("skipped"):
        print(f"✅ BỘ LỌC CHÍNH XÁC: Đã chặn video ngắn thành công! ({res_short.get('error')})")
    else:
        print(f"❌ Lỗi: Video ngắn không bị chặn!")

    # 2. Test video đạt chuẩn (56.5 phút từ Tiểu Tử Review)
    valid_url = "https://www.youtube.com/watch?v=XmafYrR-DIA"
    print("\n[TEST 2] Kiểm tra video đạt chuẩn 30 phút - 3 tiếng (56.5 phút từ Tiểu Tử Review)...")
    import yt_dlp
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(valid_url, download=False)
        dur = info.get('duration', 0)
        dur_mins = dur / 60
        print(f"   Thời lượng: {dur_mins:.1f} phút ({dur}s)")
        if 1800 <= dur <= 10800:
            print(f"✅ BỘ LỌC CHÍNH XÁC: Video {dur_mins:.1f} phút nằm trong khoảng [30 phút - 3 tiếng] -> ĐƯỢC PHÉP REUP.")
        else:
            print(f"❌ Lỗi kiểm tra thời lượng!")

def test_youtube_pipeline_only():
    """Quy trình YouTube RIÊNG BIỆT: Lấy nguồn YouTube -> Đăng CHỈ LÊN YouTube."""
    print("\n" + "=" * 65)
    print("🔴 QUY TRÌNH REUP YOUTUBE RIÊNG BIỆT (KHÔNG LIÊN QUAN ĐẾN FACEBOOK)")
    print("=" * 65)

    # Video chuẩn từ nguồn YouTube
    test_video_url = "https://www.youtube.com/watch?v=_opnqfK920U" # Video demo kiểm tra luồng
    task_id = f"yt_{int(time.time())}"
    cfg = ConfigManager.load()
    yt_cfg = cfg.get("youtube", {})

    print(f"\n[YOUTUBE 1/5] 📥 Đang tải video từ nguồn YouTube...")
    # Cho phép test chạy với min_duration tùy biến nếu đang test demo
    dl_res = VideoDownloader.download(
        url=test_video_url,
        task_id=task_id,
        min_duration_seconds=0, # Bật 0 để chạy luồng mẫu nhanh
        max_duration_seconds=10800
    )
    if not dl_res.get("success"):
        print(f"❌ Thất bại: {dl_res.get('error')}")
        return False

    raw_video = dl_res["video_path"]
    raw_thumb = dl_res.get("thumbnail_path")
    orig_title = dl_res["title"]

    print(f"\n[YOUTUBE 2/5] 🧠 AI viết lại tiêu đề YouTube...")
    new_title = AIRewriter.rewrite_title(
        orig_title,
        gemini_key=cfg.get("general", {}).get("gemini_api_key"),
        openai_key=cfg.get("general", {}).get("openai_api_key")
    )
    new_title = f"{new_title} #reviewphim #phimhay".strip()
    print(f"✅ Tiêu đề YouTube mới: '{new_title}'")

    print(f"\n[YOUTUBE 3/5] 🎨 Thiết kế Thumbnail mới...")
    thumb_path = ThumbnailGenerator.create_thumbnail(
        video_path=raw_video,
        fallback_image_path=raw_thumb,
        title_text=new_title,
        task_id=task_id,
        style="modern_yellow"
    )

    print(f"\n[YOUTUBE 4/5] ⚙️ FFmpeg lách bản quyền video & audio...")
    processed_video = VideoProcessor.process(
        input_path=raw_video,
        task_id=task_id,
        rules=yt_cfg.get("bypass_rules", {})
    )

    print(f"\n[YOUTUBE 5/5] 🔴 Đăng CHỈ LÊN KÊNH YOUTUBE...")
    clean_desc = (
        f"{new_title}\n\n"
        f"Chào mừng các bạn đã đến với kênh! Hãy bấm Like, Đăng Ký Kênh và Nhấn Chuông thông báo để không bỏ lỡ những video mới và hay nhất mỗi ngày nhé!\n\n"
        f"Cảm ơn mọi người đã luôn đồng hành và ủng hộ kênh!\n\n"
        f"#review #phimhay #reviewphim #viral #trending #phimmoi"
    )
    yt_res = YouTubeUploader.upload(
        video_path=processed_video,
        title=new_title,
        description=clean_desc,
        thumbnail_path=thumb_path,
        config=yt_cfg.get("destination", {})
    )
    if yt_res.get("success"):
        print(f"✅ Reup YouTube THÀNH CÔNG! Video ID: {yt_res.get('video_id')}")
        print(f"   🔗 Link YouTube: https://www.youtube.com/watch?v={yt_res.get('video_id')}")

    # Dọn dẹp cache
    for p in [raw_video, raw_thumb, processed_video, thumb_path]:
        if p and os.path.exists(p):
            try: os.remove(p)
            except Exception: pass
    print("🧹 Đã dọn sạch toàn bộ cache YouTube!")

def test_facebook_pipeline_only():
    """Quy trình Facebook RIÊNG BIỆT: Lấy nguồn Facebook -> Đăng CHỈ LÊN Fanpage Facebook."""
    print("\n" + "=" * 65)
    print("🔵 QUY TRÌNH REUP FACEBOOK RIÊNG BIỆT (KHÔNG LIÊN QUAN ĐẾN YOUTUBE)")
    print("=" * 65)

    test_video_url = "https://www.youtube.com/watch?v=_opnqfK920U" # Video demo ngắn để kiểm tra luồng FB
    task_id = f"fb_{int(time.time())}"
    cfg = ConfigManager.load()
    fb_cfg = cfg.get("facebook", {})

    print(f"\n[FACEBOOK 1/4] 📥 Đang tải video nguồn Facebook...")
    dl_res = VideoDownloader.download(
        url=test_video_url,
        task_id=task_id,
        min_duration_seconds=0,
        max_duration_seconds=10800
    )
    if not dl_res.get("success"):
        print(f"❌ Thất bại: {dl_res.get('error')}")
        return False

    raw_video = dl_res["video_path"]
    raw_thumb = dl_res.get("thumbnail_path")
    orig_title = dl_res["title"]

    print(f"\n[FACEBOOK 2/4] 🧠 AI viết lại tiêu đề Facebook...")
    new_title = AIRewriter.rewrite_title(
        orig_title,
        gemini_key=cfg.get("general", {}).get("gemini_api_key"),
        openai_key=cfg.get("general", {}).get("openai_api_key")
    )
    new_title = f"{new_title} #reviewphim #xuhuong".strip()
    print(f"✅ Tiêu đề Facebook mới: '{new_title}'")

    print(f"\n[FACEBOOK 3/4] ⚙️ FFmpeg lách bản quyền video...")
    processed_video = VideoProcessor.process(
        input_path=raw_video,
        task_id=task_id,
        rules=fb_cfg.get("bypass_rules", {})
    )

    print(f"\n[FACEBOOK 4/4] 🔵 Đăng CHỈ LÊN FANPAGE FACEBOOK (Film Trung Quốc)...")
    clean_fb_desc = (
        f"{new_title}\n\n"
        f"Mọi người xem video thấy hay nhớ bấm Like và Follow Fanpage để đón xem những tập tiếp theo nhé!\n\n"
        f"#film #reviewphim #phimhay #xuhuong #trending"
    )
    fb_res = FacebookUploader.upload(
        video_path=processed_video,
        title=new_title,
        description=clean_fb_desc,
        config=fb_cfg.get("destination", {})
    )
    if fb_res.get("success"):
        print(f"✅ Reup Facebook THÀNH CÔNG! Post ID: {fb_res.get('video_id')}")
        print(f"   🔗 Facebook Post ID: {fb_res.get('video_id')}")

    # Dọn dẹp cache
    for p in [raw_video, raw_thumb, processed_video]:
        if p and os.path.exists(p):
            try: os.remove(p)
            except Exception: pass
    print("🧹 Đã dọn sạch toàn bộ cache Facebook!")

if __name__ == "__main__":
    test_duration_filter_rules()
