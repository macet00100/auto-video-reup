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

def run_youtube_test():
    print("=" * 65)
    print("🔴 BẮT ĐẦU TEST REUP YOUTUBE TỪ KÊNH NGUỒN TIỂU TỬ REVIEW")
    print("=" * 65)

    yt_source_url = "https://www.youtube.com/watch?v=XmafYrR-DIA"
    task_id = f"yt_real_{int(time.time())}"
    cfg = ConfigManager.load()
    yt_cfg = cfg.get("youtube", {})

    print(f"\n[BƯỚC 1/5] 📥 Kiểm tra bộ lọc & Tải video gần nhất...")
    print(f"   Kênh nguồn: Tiểu Tử Review (@tieutureview94)")
    print(f"   URL: {yt_source_url}")

    # Tận dụng file đã tải nếu có sẵn để tiết kiệm thời gian
    cached_raw = os.path.join(os.path.dirname(__file__), "storage", "temp", "raw_speed_test.mp4")
    cached_thumb = os.path.join(os.path.dirname(__file__), "storage", "temp", "raw_speed_test.jpg")
    
    if os.path.exists(cached_raw):
        print("   ✅ Sử dụng file video 56.5 phút đã tải sẵn trong storage/temp để tối ưu tốc độ.")
        raw_video = cached_raw
        raw_thumb = cached_thumb if os.path.exists(cached_thumb) else None
        orig_title = "Xuyên Không Thành Hoàng Đế Lười: Lừa Vương Gia Cướp Ngôi Để Mình Đi Nghỉ Hưu !!!"
        duration = 3391
    else:
        dl_res = VideoDownloader.download(
            url=yt_source_url,
            task_id=task_id,
            min_duration_seconds=1800,
            max_duration_seconds=10800
        )
        if not dl_res.get("success"):
            print(f"❌ Tải thất bại: {dl_res.get('error')}")
            return False
        raw_video = dl_res["video_path"]
        raw_thumb = dl_res.get("thumbnail_path")
        orig_title = dl_res["title"]
        duration = dl_res["duration"]

    print(f"   Thời lượng: {duration/60:.1f} phút -> Thỏa mãn điều kiện [30 phút - 3 tiếng]!")

    # BƯỚC 2: AI viết lại tiêu đề mới
    print(f"\n[BƯỚC 2/5] 🧠 AI đang viết lại tiêu đề YouTube chuẩn SEO...")
    new_title = AIRewriter.rewrite_title(
        orig_title,
        gemini_key=cfg.get("general", {}).get("gemini_api_key"),
        openai_key=cfg.get("general", {}).get("openai_api_key")
    )
    new_title = f"{new_title} #reviewphim #phimhay".strip()
    print(f"   Tiêu đề mới: '{new_title}'")

    # BƯỚC 3: Tạo Thumbnail mới
    print(f"\n[BƯỚC 3/5] 🎨 Đang tạo ảnh bìa Thumbnail mới...")
    thumb_path = ThumbnailGenerator.create_thumbnail(
        video_path=raw_video,
        fallback_image_path=raw_thumb,
        title_text=new_title,
        task_id=task_id,
        style="modern_yellow"
    )
    print(f"   Thumbnail: {thumb_path}")

    # BƯỚC 4: FFmpeg lách bản quyền video 56.5 phút
    print(f"\n[BƯỚC 4/5] ⚙️ FFmpeg đang render lách bản quyền video 56.5 phút (Ultrafast Mode)...")
    t0 = time.time()
    rules = yt_cfg.get("bypass_rules", {})
    rules["preset"] = "ultrafast"
    rules["threads"] = 4
    processed_video = VideoProcessor.process(
        input_path=raw_video,
        task_id=task_id,
        rules=rules
    )
    elapsed = time.time() - t0
    size_mb = os.path.getsize(processed_video) / (1024 * 1024)
    print(f"   Render thành công ({elapsed:.1f}s = {elapsed/60:.1f} phút)! Kích thước: {size_mb:.2f} MB")

    # BƯỚC 5: Đăng CHỈ LÊN KÊNH YOUTUBE ĐÍCH
    print(f"\n[BƯỚC 5/5] 🔴 Đang tải lên kênh YouTube đích qua Refresh Token...")
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
        print(f"   ✅ UPLOAD YOUTUBE THÀNH CÔNG! {yt_res.get('message')}")
        if yt_res.get("video_id"):
            print(f"   🔗 Link YouTube: https://www.youtube.com/watch?v={yt_res.get('video_id')}")
    else:
        print(f"   ⚠️ YouTube phản hồi: {yt_res.get('message')}")

    # Dọn dẹp cache
    print("\n🧹 Đang xóa sạch cache video và thumbnail đã tải...")
    for p in [processed_video, thumb_path]:
        if p and os.path.exists(p):
            try: os.remove(p)
            except Exception: pass
    print("✅ Đã dọn dẹp sạch ổ cứng!")
    return yt_res

if __name__ == "__main__":
    run_youtube_test()
