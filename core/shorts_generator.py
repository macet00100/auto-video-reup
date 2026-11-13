import os
import re
import subprocess
import numpy as np
from typing import List, Dict, Any, Tuple
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
    def find_audio_peak_moments(video_path: str, clip_duration: int = 50) -> List[Tuple[int, str, str]]:
        """
        THUẬT TOÁN KHOA HỌC PHÂN TÍCH SÓNG ÂM (AUDIO RMS ENERGY ANALYSIS):
        Không đoán mò. Đo lường chính xác mức độ kịch tính dựa trên:
        - Âm lượng cao nhất (tiếng quát tháo, cãi vã, tát, nhạc dồn dập).
        - Biến thiên năng lượng âm thanh mạnh nhất (Dynamic Range).
        Tìm ra:
        - Đoạn 1: Khoảnh khắc cao trào nhất ở nửa đầu phim (Xung đột bùng nổ).
        - Đoạn 2: Khoảnh khắc cao trào nhất ở nửa sau phim (Đỉnh điểm vả mặt).
        """
        total_duration = ShortsGenerator.get_video_duration(video_path)
        if total_duration < 120:
            return []

        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "temp"))
        os.makedirs(temp_dir, exist_ok=True)
        temp_wav = os.path.join(temp_dir, f"audio_probe_{os.getpid()}.wav")

        try:
            # 1. Trích xuất âm thanh downsampled 8kHz mono siêu tốc (1 tiếng chỉ mất ~2s)
            cmd_extract = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-c:a", "pcm_s16le", "-ar", "8000", "-ac", "1",
                temp_wav
            ]
            subprocess.run(cmd_extract, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            # 2. Đọc mẫu âm thanh PCM
            with open(temp_wav, "rb") as f:
                f.seek(44)  # Bỏ qua WAV header 44 bytes
                raw_bytes = f.read()
            samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)

            sr = 8000
            window_size = sr * clip_duration
            hop_size = sr * 5  # Quét bước nhảy 5 giây một lần

            # Chia timeline thành 2 nửa (bỏ 3 phút đầu và 2 phút cuối video để tránh đoạn intro/outro kênh nguồn)
            min_start = min(180, int(total_duration * 0.05))
            max_end = max(min_start + clip_duration, int(total_duration - 120))
            mid_point = int((min_start + max_end) / 2)

            half1_peaks = []
            half2_peaks = []

            for s_idx in range(min_start * sr, (max_end - clip_duration) * sr, hop_size):
                chunk = samples[s_idx:s_idx + window_size]
                if len(chunk) < window_size:
                    break
                # Tính toán Root Mean Square (RMS) Energy
                rms = np.sqrt(np.mean(chunk ** 2))
                time_sec = int(s_idx / sr)

                if time_sec < mid_point:
                    half1_peaks.append((time_sec, rms))
                else:
                    half2_peaks.append((time_sec, rms))

            # Chọn điểm có năng lượng âm thanh cao nhất mỗi nửa
            half1_peaks.sort(key=lambda x: x[1], reverse=True)
            half2_peaks.sort(key=lambda x: x[1], reverse=True)

            best_p1 = half1_peaks[0][0] if half1_peaks else int(total_duration * 0.25)
            best_p2 = half2_peaks[0][0] if half2_peaks else int(total_duration * 0.75)

            LogManager.log(
                f"Phân tích phổ âm thanh khoa học: Phát hiện Cao trào #1 tại {best_p1//60}m{best_p1%60}s, Cao trào #2 tại {best_p2//60}m{best_p2%60}s",
                "SUCCESS", "SHORTS"
            )

            return [
                (best_p1, "Cao Trào 1", "Xung đột kịch tính nhất"),
                (best_p2, "Cao Trào 2", "Vả mặt đỉnh điểm nhất")
            ]

        except Exception as e:
            LogManager.log(f"Lỗi khi phân tích phổ âm thanh (dùng mốc tiêu chuẩn): {e}", "WARNING", "SHORTS")
            return [
                (int(total_duration * 0.20), "Cao Trào 1", "Xung đột ban đầu"),
                (int(total_duration * 0.75), "Cao Trào 2", "Đỉnh điểm vả mặt")
            ]
        finally:
            if os.path.exists(temp_wav):
                try:
                    os.remove(temp_wav)
                except Exception:
                    pass

    @staticmethod
    def extract_shorts(
        processed_video_path: str,
        base_title: str,
        task_id: str,
        count: int = 2,
        clip_duration: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Tự động cắt đúng 2 đoạn cao trào nhất (50s/clip) từ video dài dựa trên phân tích phổ âm thanh thực tế.
        Định dạng dọc chuẩn 9:16 (1080x1920) tối ưu cho YouTube Shorts & Facebook Reels.
        """
        if not os.path.exists(processed_video_path):
            return []

        total_duration = ShortsGenerator.get_video_duration(processed_video_path)
        if total_duration < 120:
            return []

        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "temp"))
        os.makedirs(temp_dir, exist_ok=True)

        is_vertical = ShortsGenerator.is_video_vertical(processed_video_path)

        # Sử dụng thuật toán đo năng lượng âm thanh thực tế để tìm điểm cao trào
        cut_points = ShortsGenerator.find_audio_peak_moments(processed_video_path, clip_duration)

        shorts_results = []

        for idx, (start_sec, label_prefix, label_desc) in enumerate(cut_points[:count]):
            short_task_id = f"short_{task_id}_{idx+1}"
            out_short_path = os.path.join(temp_dir, f"{short_task_id}.mp4")

            safe_start = max(0, min(start_sec, int(total_duration - clip_duration - 5)))

            LogManager.log(
                f"Đang cắt Short #{idx+1} ({label_prefix} - {label_desc}) tại điểm đỉnh âm thanh {safe_start//60}m{safe_start%60}s...",
                "INFO", "SHORTS"
            )

            # Xây dựng bộ lọc 9:16 dọc điện ảnh
            if is_vertical:
                vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
            else:
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
                # Gọt sạch toàn bộ 'Full Trọn Bộ | ', 'Trọn Bộ | ', '[Tập X]' để video Short không bao giờ có chữ 'Full trọn bộ'
                clean_short_base = re.sub(r'^(?:\[.*?\]\s*)?(?:full\s+trọn\s+bộ|trọn\s+bộ|bản\s+full|full)\s*[\:\|\-]?\s*', '', base_title, flags=re.IGNORECASE).strip()
                clean_short_base = re.sub(r'^(?:\[\s*(?:tập|phần|p)\.?\s*\d+\s*\]|(?:tập|phần|p)\.?\s*\d+[\s:\-\|])\s*', '', clean_short_base, flags=re.IGNORECASE).strip()
                short_title = f"[{label_prefix}] {clean_short_base}"
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
