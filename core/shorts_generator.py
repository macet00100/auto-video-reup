import os
import subprocess
from typing import List, Dict, Any, Optional
from core.task_queue import LogManager

class ShortsGenerator:
    @staticmethod
    def get_video_duration(video_path: str) -> float:
        """Lấy chính xác thời lượng video tính bằng giây."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return float(res.stdout.strip())
        except Exception as e:
            LogManager.log(f"Lỗi lấy thời lượng video: {e}", "WARNING", "SHORTS")
            return 3600.0

    @staticmethod
    def is_video_vertical(video_path: str) -> bool:
        """Kiểm tra video là dạng dọc 9:16 hay dạng ngang 16:9."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                video_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            dims = res.stdout.strip().split('x')
            w, h = int(dims[0]), int(dims[1])
            return h > w
        except Exception:
            return False

    @staticmethod
    def extract_shorts(
        processed_video_path: str,
        base_title: str,
        task_id: str,
        count: int = 2,
        clip_duration: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Tự động cắt đúng 2 đoạn cao trào nhất (50s/clip) từ video dài đã render:
        - Đoạn 1: Mở màn kịch tính / xung đột ban đầu (~18% thời lượng phim)
        - Đoạn 2: Cao trào đỉnh điểm / vả mặt trả thù (~72% thời lượng phim)
        Định dạng dọc chuẩn 9:16 (1080x1920) tối ưu cho YouTube Shorts & Facebook Reels.
        """
        if not os.path.exists(processed_video_path):
            return []

        total_duration = ShortsGenerator.get_video_duration(processed_video_path)
        if total_duration < 120:
            LogManager.log("Video quá ngắn để cắt Shorts.", "WARNING", "SHORTS")
            return []

        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "temp"))
        os.makedirs(temp_dir, exist_ok=True)

        is_vertical = ShortsGenerator.is_video_vertical(processed_video_path)

        # 2 mốc thời gian vàng để bắt trọn cao trào kịch tính
        # Điểm 1: 18% thời lượng (xung đột ban đầu)
        # Điểm 2: 72% thời lượng (vả mặt cao trào)
        cut_points = [
            (int(total_duration * 0.18), "Tập 1", "Mở màn kịch tính"),
            (int(total_duration * 0.72), "Cao Trào", "Đỉnh điểm vả mặt")
        ]

        shorts_results = []

        for idx, (start_sec, label_prefix, label_desc) in enumerate(cut_points[:count]):
            short_task_id = f"short_{task_id}_{idx+1}"
            out_short_path = os.path.join(temp_dir, f"{short_task_id}.mp4")

            # Đảm bảo điểm bắt đầu không vượt quá thời lượng
            safe_start = max(0, min(start_sec, int(total_duration - clip_duration - 5)))

            LogManager.log(
                f"Đang trích xuất Short #{idx+1} ({label_prefix} - {label_desc}) tại mốc {safe_start//60}m{safe_start%60}s...",
                "INFO", "SHORTS"
            )

            # Xây dựng bộ lọc 9:16 dọc điện ảnh
            if is_vertical:
                # Video đã là dọc 9:16 -> scale chuẩn 1080x1920
                vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
            else:
                # Video ngang 16:9 -> Tạo hiệu ứng Blur-Background phong cách điện ảnh
                vf = (
                    "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                    "[0:v]scale=1080:-1[fg];"
                    "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
                )

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(safe_start),
                "-t", str(clip_duration),
                "-i", processed_video_path
            ]

            if is_vertical:
                cmd.extend(["-vf", vf])
            else:
                cmd.extend(["-filter_complex", vf, "-map", "[v]", "-map", "0:a:0?"])

            cmd.extend([
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-r", "30",
                "-c:a", "aac",
                "-b:a", "128k",
                "-ar", "48000",
                out_short_path
            ])

            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0 and os.path.exists(out_short_path) and os.path.getsize(out_short_path) > 10000:
                short_title = f"[{label_prefix}] {base_title}"
                if len(short_title) > 90:
                    short_title = short_title[:90].rsplit(' ', 1)[0]

                shorts_results.append({
                    "path": out_short_path,
                    "title": short_title,
                    "label": label_prefix,
                    "description": label_desc,
                    "duration": clip_duration
                })
                LogManager.log(f"Đã tạo thành công Short #{idx+1} ({os.path.getsize(out_short_path)//1024} KB): {out_short_path}", "SUCCESS", "SHORTS")
            else:
                LogManager.log(f"Lỗi khi cắt Short #{idx+1}: {res.stderr[-200:]}", "WARNING", "SHORTS")

        return shorts_results
