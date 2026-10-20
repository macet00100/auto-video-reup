import os
import glob
import subprocess
from typing import Dict, Any, Optional
import yt_dlp
from core.task_queue import LogManager

class VideoDownloader:
    @staticmethod
    def download(
        url: str,
        task_id: str,
        proxy: Optional[str] = None,
        min_duration_seconds: int = 1800,  # Tối thiểu 30 phút
        max_duration_seconds: int = 10800  # Tối đa 3 tiếng
    ) -> Dict[str, Any]:
        """
        Tải video với bộ lọc thời lượng:
        - Chỉ nhận video từ 30 phút (1.800 giây) đến 3 tiếng (10.800 giây).
        - Bỏ qua các video ngắn < 30 phút và video dài > 3 tiếng.
        """
        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "temp"))
        os.makedirs(temp_dir, exist_ok=True)
        
        output_template = os.path.join(temp_dir, f"raw_{task_id}.%(ext)s")
        thumb_template = os.path.join(temp_dir, f"raw_thumb_{task_id}")

        cookie_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cookies.txt"))
        check_opts = {
            'quiet': True,
            'noplaylist': True,
            'extractor_args': {'youtube': {'player_client': ['visionos', 'android', 'android_vr']}}
        }
        if os.path.exists(cookie_path):
            check_opts['cookiefile'] = cookie_path
        if proxy and proxy.strip():
            check_opts['proxy'] = proxy.strip()
        elif os.environ.get("PROXY"):
            check_opts['proxy'] = os.environ.get("PROXY").strip()
        elif os.environ.get("HTTP_PROXY"):
            check_opts['proxy'] = os.environ.get("HTTP_PROXY").strip()

        try:
            # 1. Trích xuất thông tin trước để kiểm tra thời lượng video (tránh tải file không đạt chuẩn thời lượng)
            with yt_dlp.YoutubeDL(check_opts) as ydl_check:
                info_check = ydl_check.extract_info(url, download=False)
                duration = info_check.get('duration', 0)
                title = info_check.get('title', 'Video Không Tiêu Đề')

                # Bộ lọc 1: Bỏ qua video ngắn dưới 30 phút (1.800 giây)
                if duration and duration < min_duration_seconds:
                    mins = duration // 60
                    secs = duration % 60
                    min_req = min_duration_seconds // 60
                    LogManager.log(
                        f"Bỏ qua video '{title}' vì chỉ dài {mins}m{secs}s (Ngắn hơn mức yêu cầu tối thiểu {min_req} phút).",
                        "WARNING", "DOWNLOADER"
                    )
                    return {
                        "success": False,
                        "skipped": True,
                        "title": title,
                        "duration": duration,
                        "error": f"Video chỉ dài {mins}m{secs}s (ngắn hơn mức tối thiểu {min_req} phút)"
                    }

                # Bộ lọc 2: Bỏ qua video dài trên 3 tiếng (10.800 giây)
                if duration and duration > max_duration_seconds:
                    hours = duration // 3600
                    minutes = (duration % 3600) // 60
                    max_req = max_duration_seconds // 3600
                    LogManager.log(
                        f"Bỏ qua video '{title}' vì dài {hours} giờ {minutes} phút (Vượt quá giới hạn tối đa {max_req} tiếng).",
                        "WARNING", "DOWNLOADER"
                    )
                    return {
                        "success": False,
                        "skipped": True,
                        "title": title,
                        "duration": duration,
                        "error": f"Video dài {hours}h{minutes}m (quá giới hạn tối đa {max_req} tiếng)"
                    }

            # 2. Tiến hành tải video nếu dưới 3 tiếng
            ydl_opts = {
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                'outtmpl': output_template,
                'writethumbnail': True,
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
                'retries': 5,
                'fragment_retries': 5,
                'extractor_args': {'youtube': {'player_client': ['visionos', 'android', 'android_vr']}},
                'postprocessors': [{
                    'key': 'FFmpegThumbnailsConvertor',
                    'format': 'jpg',
                    'when': 'before_dl'
                }],
            }

            if os.path.exists(cookie_path):
                ydl_opts['cookiefile'] = cookie_path
            if proxy and proxy.strip():
                ydl_opts['proxy'] = proxy.strip()
            elif os.environ.get("PROXY"):
                ydl_opts['proxy'] = os.environ.get("PROXY").strip()
            elif os.environ.get("HTTP_PROXY"):
                ydl_opts['proxy'] = os.environ.get("HTTP_PROXY").strip()

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', title)
                duration = info.get('duration', duration)
                
                # Tìm file video thực tế được tải về
                expected_video = os.path.join(temp_dir, f"raw_{task_id}.mp4")
                if not os.path.exists(expected_video):
                    matches = glob.glob(os.path.join(temp_dir, f"raw_{task_id}.*"))
                    for m in matches:
                        if not m.endswith(('.jpg', '.webp', '.png', '.part')):
                            expected_video = m
                            break

                if not os.path.exists(expected_video):
                    raise FileNotFoundError("Không tìm thấy file video sau khi tải về.")
                # Kiểm tra âm thanh của file tải về
                try:
                    probe_chk = subprocess.run(
                        ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', expected_video],
                        stdout=subprocess.PIPE, text=True
                    )
                    if 'audio' not in probe_chk.stdout:
                        LogManager.log(f'Cảnh báo: File video tải về từ "{url}" không có luồng audio!', 'WARNING', 'DOWNLOADER')
                except Exception:
                    pass


                # Tìm file thumbnail
                thumb_path = None
                thumb_matches = glob.glob(os.path.join(temp_dir, f"raw_{task_id}.*.jpg")) + \
                                glob.glob(os.path.join(temp_dir, f"raw_{task_id}.jpg")) + \
                                glob.glob(os.path.join(temp_dir, f"raw_thumb_{task_id}*.jpg"))
                if thumb_matches:
                    thumb_path = thumb_matches[0]

                LogManager.log(f"Tải video thành công: '{title}' ({duration} giây)", "INFO", "DOWNLOADER")
                return {
                    "success": True,
                    "title": title,
                    "duration": duration,
                    "video_path": expected_video,
                    "thumbnail_path": thumb_path
                }
        except Exception as e:
            LogManager.log(f"Lỗi tải video {url}: {str(e)}", "ERROR", "DOWNLOADER")
            return {
                "success": False,
                "error": str(e)
            }
