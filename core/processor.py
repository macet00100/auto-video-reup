import os
import re
import subprocess
import statistics
from typing import Dict, Any, Optional
from core.task_queue import LogManager

class VideoProcessor:
    @staticmethod
    def detect_video_format(input_path: str, task_id: str = "") -> Dict[str, Any]:
        """
        Tự động phân loại định dạng video và phát hiện dải viền đen (Pillarbox):
        - Dạng 1: Phim dọc (height > width HOẶC video ngang có 2 dải đen lớn 2 bên pillarbox).
        - Dạng 2: Phim ngang (widescreen 16:9 điện ảnh chuẩn).
        """
        in_w, in_h = 1280, 720
        dur = 60.0
        try:
            probe_cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", input_path
            ]
            probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, text=True, check=True)
            lines = [line.strip() for line in probe_res.stdout.strip().splitlines() if line.strip()]
            if len(lines) >= 2:
                in_w, in_h = int(lines[0]), int(lines[1])
            if len(lines) >= 3:
                try:
                    dur = float(lines[2])
                except ValueError:
                    pass
        except Exception:
            try:
                p1 = subprocess.run(
                    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", input_path],
                    stdout=subprocess.PIPE, text=True
                )
                parts = p1.stdout.strip().split('x')
                if len(parts) == 2:
                    in_w, in_h = int(parts[0]), int(parts[1])
            except Exception:
                pass

        # 1. Trường hợp Video vốn là Dọc tự nhiên (height > width)
        if in_h > in_w:
            LogManager.log(f"[{task_id}] Nhận diện DẠNG 1: Phim Dọc 9:16 nguyên bản ({in_w}x{in_h}).", "INFO", "DETECTOR")
            return {
                "is_vertical": True,
                "has_pillarbox": False,
                "crop_filter": None,
                "crop_x": 0,
                "eff_w": in_w,
                "eff_h": in_h,
                "orig_w": in_w,
                "orig_h": in_h
            }

        # 2. Trường hợp Khung hình Ngang (in_w >= in_h, ví dụ 1920x1080 hoặc 1280x720)
        # Quét cropdetect tại nhiều mốc thời gian để phát hiện 2 viền đen bên hông (Pillarbox)
        sample_times = [30, 60, 120, 180, 240, 360]
        sample_times = [t for t in sample_times if t < max(10, dur - 15)]
        if not sample_times:
            sample_times = [max(1, int(dur * 0.2)), max(2, int(dur * 0.5)), max(3, int(dur * 0.8))]

        detected_w = []
        detected_x = []

        for ts in sample_times:
            try:
                cd_cmd = [
                    "ffmpeg", "-y", "-ss", str(int(ts)), "-i", input_path,
                    "-vframes", "12", "-vf", "cropdetect=24:16:0",
                    "-f", "null", "-"
                ]
                res = subprocess.run(cd_cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, encoding="utf-8", errors="ignore")
                matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", res.stderr)
                for cw, ch, cx, cy in matches:
                    cw, ch, cx, cy = int(cw), int(ch), int(cx), int(cy)
                    # Tiêu chuẩn nhận diện viền đen:
                    # - Bề rộng crop < 70% bề rộng khung ngang (thường chiếm 30%-60% ở giữa)
                    # - Tỷ lệ khung hình crop là tỷ lệ dọc (w / in_h <= 0.85)
                    # - Tọa độ x nằm lùi vào trong (cx >= 8% in_w)
                    if (cw / in_w) < 0.70 and (cw / in_h) <= 0.85 and cx >= (in_w * 0.08):
                        detected_w.append(cw)
                        detected_x.append(cx)
            except Exception:
                continue

        # Nếu phát hiện ít nhất 3 mẫu khẳng định có viền đen
        if len(detected_w) >= 3:
            med_w = int(statistics.median(detected_w))
            med_x = int(statistics.median(detected_x))
            # Làm tròn số chẵn cho bộ mã hóa H.264
            med_w = med_w - (med_w % 2)
            med_x = med_x - (med_x % 2)

            crop_filter = f"crop={med_w}:{in_h}:{med_x}:0"
            LogManager.log(
                f"[{task_id}] Nhận diện DẠNG 1: Phim Dọc bị lồng viền đen ({med_w}x{in_h} tại x={med_x}). Tự động gọt sạch 2 dải đen thừa!",
                "INFO", "DETECTOR"
            )
            return {
                "is_vertical": True,
                "has_pillarbox": True,
                "crop_filter": crop_filter,
                "crop_x": med_x,
                "eff_w": med_w,
                "eff_h": in_h,
                "orig_w": in_w,
                "orig_h": in_h
            }

        # Nếu không có viền đen -> DẠNG 2: Phim Ngang 16:9 chuẩn điện ảnh
        LogManager.log(f"[{task_id}] Nhận diện DẠNG 2: Phim Ngang 16:9 chuẩn điện ảnh ({in_w}x{in_h}).", "INFO", "DETECTOR")
        return {
            "is_vertical": False,
            "has_pillarbox": False,
            "crop_filter": None,
            "crop_x": 0,
            "eff_w": in_w,
            "eff_h": in_h,
            "orig_w": in_w,
            "orig_h": in_h
        }

    @staticmethod
    def process(input_path: str, task_id: str, rules: Dict[str, Any]) -> str:
        temp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "temp"))
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.join(temp_dir, f"processed_{task_id}.mp4")

        # Đọc các cấu hình bypass
        hflip = rules.get("hflip", False) # Tắt mặc định để không bị ngược phụ đề
        remove_logo = rules.get("remove_logo", True) # Bật xóa logo kênh cũ
        speed = float(rules.get("speed", 1.035))
        crop_percent = int(rules.get("crop_percent", 3))
        color_boost = rules.get("color_boost", True)
        blur_border = rules.get("blur_border", False)
        target_res = rules.get("target_resolution", "720p")

        # 0. Tự động nhận diện định dạng (Dạng 1: Phim dọc / Dạng 2: Phim ngang 16:9)
        fmt_info = VideoProcessor.detect_video_format(input_path, task_id)
        in_w = fmt_info["orig_w"]
        in_h = fmt_info["orig_h"]

        # Xây dựng video filter chuỗi (-vf)
        vf_parts = []

        # 1. Quét thông minh toàn màn hình để phát hiện và xóa sạch mọi logo bất kể vị trí
        if remove_logo:
            detected_boxes = []
            try:
                from core.logo_detector import LogoDetector
                detected_boxes = LogoDetector.detect_watermarks(input_path)
            except Exception as e:
                LogManager.log(f"Lỗi khi gọi LogoDetector: {e}", "WARNING", "DELOGO")

            if detected_boxes:
                LogManager.log(f"[{task_id}] Quét toàn màn hình thành công: Phát hiện {len(detected_boxes)} logo cần xóa!", "INFO", "DELOGO")
                for (lx, ly, lw, lh) in detected_boxes:
                    safe_x = max(4, min(int(lx), in_w - 20))
                    safe_y = max(4, min(int(ly), in_h - 20))
                    safe_w = max(16, min(int(lw), in_w - safe_x - 4))
                    safe_h = max(16, min(int(lh), in_h - safe_y - 4))
                    vf_parts.append(f"delogo=x={safe_x}:y={safe_y}:w={safe_w}:h={safe_h}:show=0")
            else:
                # Nếu video không có logo rõ ràng, bảo vệ an toàn bằng cách làm mờ 2 góc trên
                if fmt_info["has_pillarbox"]:
                    # Phim dọc có viền đen: đặt vùng mờ trong phạm vi hiển thị nội dung phim
                    med_x = fmt_info["crop_x"]
                    eff_w = fmt_info["eff_w"]
                    lw = max(16, int(eff_w * 0.18))
                    lh = max(16, int(in_h * 0.12))
                    safe_x1 = med_x + 8
                    safe_y1 = max(4, int(in_h * 0.01))
                    safe_x2 = med_x + eff_w - lw - 8
                    safe_y2 = safe_y1
                    vf_parts.append(f"delogo=x={safe_x1}:y={safe_y1}:w={lw}:h={lh}:show=0")
                    vf_parts.append(f"delogo=x={safe_x2}:y={safe_y2}:w={lw}:h={lh}:show=0")
                else:
                    lw = int(in_w * 0.18)
                    lh = int(in_h * 0.12)
                    safe_x1 = max(4, int(in_w * 0.01))
                    safe_y1 = max(4, int(in_h * 0.01))
                    safe_x2 = max(4, in_w - lw - 4)
                    vf_parts.append(f"delogo=x={safe_x1}:y={safe_y1}:w={lw}:h={lh}:show=0")
                    vf_parts.append(f"delogo=x={safe_x2}:y={safe_y1}:w={lw}:h={lh}:show=0")

        # 2. Gọt sạch viền đen (Pillarbox Crop) nếu phát hiện phim dọc lồng viền đen
        if fmt_info["crop_filter"]:
            vf_parts.append(fmt_info["crop_filter"])

        # 3. Lật ngang (chỉ khi người dùng cố ý bật, mặc định tắt để không ngược sub)
        if hflip:
            vf_parts.append("hflip")

        # 4. Tăng tốc độ video
        if speed != 1.0:
            vf_parts.append(f"setpts=PTS/{speed}")

        # 5. Cắt viền mép (Crop)
        if crop_percent > 0:
            factor = (100 - crop_percent * 2) / 100.0
            offset = crop_percent / 100.0
            vf_parts.append(f"crop=in_w*{factor:.3f}:in_h*{factor:.3f}:in_w*{offset:.3f}:in_h*{offset:.3f}")

        # 6. Tăng tương phản & bão hòa màu để thay đổi mã hash bản quyền
        if color_boost:
            vf_parts.append("eq=contrast=1.06:saturation=1.12:brightness=0.01")

        # 7. Căn chỉnh kích thước độ phân giải chuẩn mực cho từng dạng
        if fmt_info["is_vertical"]:
            # DẠNG 1: PHIM DỌC CHUẨN 9:16 (Tràn viền màn hình điện thoại)
            if target_res == "1080p":
                vf_parts.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2")
            elif target_res == "original":
                pass
            else: # 720p chuẩn dọc (720x1280)
                vf_parts.append("scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2")
        else:
            # DẠNG 2: PHIM NGANG 16:9 CHUẨN ĐIỆN ẢNH
            if target_res == "1080p":
                vf_parts.append("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2")
            elif target_res == "original":
                pass
            else: # 720p chuẩn ngang (1280x720)
                vf_parts.append("scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2")

        vf_str = ",".join(vf_parts)

        # 8. Xây dựng audio filter chuẩn xác 100% không bao giờ mất tiếng
        has_audio = True
        try:
            probe_a = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", input_path],
                stdout=subprocess.PIPE, text=True
            )
            if "audio" not in probe_a.stdout:
                has_audio = False
                LogManager.log(f"[{task_id}] CẢNH BÁO: File nguồn không phát hiện thấy luồng âm thanh!", "WARNING", "FFMPEG")
        except Exception:
            pass

        af_parts = []
        if speed != 1.0:
            # atempo chuẩn thích ứng mọi sample rate (44.1kHz, 48kHz), giữ nguyên giọng nói rõ ràng không bị méo hay nghẹt tiếng
            af_parts.append(f"atempo={speed:.3f}")
        af_parts.append("volume=1.05")
        af_str = ",".join(af_parts)

        preset = rules.get("preset", "veryfast")
        threads = str(rules.get("threads", 4))

        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-vf", vf_str,
            "-map", "0:v:0",
        ]

        if has_audio:
            cmd.extend([
                "-map", "0:a:0",
                "-af", af_str,
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000"
            ])

        cmd.extend([
            "-r", "30",
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", "23",
            "-threads", threads,
            output_path
        ])

        LogManager.log(f"[{task_id}] Thực thi lệnh FFmpeg ({'DỌC 9:16' if fmt_info['is_vertical'] else 'NGANG 16:9'}): {' '.join(cmd[:14])}...", "INFO", "FFMPEG")

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="ignore")
        if result.returncode != 0:
            LogManager.log(f"[{task_id}] Lỗi FFmpeg: {result.stderr[-400:]}", "ERROR", "FFMPEG")
            raise RuntimeError(f"FFmpeg transcode failed: {result.stderr[-200:]}")

        LogManager.log(f"[{task_id}] Render video thành công ({'Dọc 9:16' if fmt_info['is_vertical'] else 'Ngang 16:9'}): {output_path}", "SUCCESS", "FFMPEG")
        return output_path
