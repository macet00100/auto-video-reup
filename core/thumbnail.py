import os
import subprocess
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageStat, ImageEnhance
from core.task_queue import LogManager

class ThumbnailGenerator:
    @staticmethod
    def create_thumbnail(
        video_path: Optional[str],
        fallback_image_path: Optional[str],
        title_text: str,
        task_id: str,
        style: str = "modern_yellow"
    ) -> Optional[str]:
        """
        Tạo ảnh thu nhỏ (Thumbnail) chuẩn đồ họa điện ảnh:
        - ƯU TIÊN 1: Sử dụng trực tiếp ảnh thumbnail gốc 1280x720 (maxresdefault) từ nhà sản xuất/kênh nguồn.
          Đây là ảnh đồ họa chất lượng cao nhất với đầy đủ nhân vật và phông chữ thư pháp nghệ thuật.
        - ƯU TIÊN 2: Nếu không có thumbnail gốc, trích xuất khung hình sắc nét nhất từ video và căn chỉnh tỷ lệ 16:9 chuẩn.
        """
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "thumbnails"))
        os.makedirs(output_dir, exist_ok=True)
        out_file = os.path.join(output_dir, f"thumb_{task_id}.jpg")

        # 1. Ưu tiên hàng đầu: Dùng thumbnail gốc chất lượng cao từ nguồn + biến tấu lách bản quyền nghệ thuật
        if fallback_image_path and os.path.exists(fallback_image_path) and os.path.getsize(fallback_image_path) > 5000:
            try:
                with Image.open(fallback_image_path) as src_img:
                    # Chuẩn hóa về tỷ lệ vàng 1280x720 (chuẩn HD YouTube/Facebook)
                    thumb_img = src_img.convert("RGB")
                    if thumb_img.size != (1280, 720):
                        thumb_img = thumb_img.resize((1280, 720), Image.Resampling.LANCZOS)

                    # BẢO VỆ CHỮ NGHỆ THUẬT: TUYỆT ĐỐI KHÔNG LẬT GƯƠNG CHIỀU NGANG (Tránh bị ngược chữ thư pháp/tiêu đề)
                    # Biến tấu lách mã băm (anti-hash) thông minh bằng cách cạo viền 1.5% + Tái tạo điểm ảnh:
                    crop_w = int(thumb_img.width * 0.015)
                    crop_h = int(thumb_img.height * 0.015)
                    thumb_img = thumb_img.crop((crop_w, crop_h, thumb_img.width - crop_w, thumb_img.height - crop_h))
                    thumb_img = thumb_img.resize((1280, 720), Image.Resampling.LANCZOS)

                    # TĂNG CƯỜNG ĐỘ RỰC RỠ & TƯƠNG PHẢN ĐIỆN ẢNH:
                    # Tăng độ tươi màu (saturation), độ nét và tương phản nhẹ để tạo mã băm mới và ảnh bắt mắt hơn
                    thumb_img = ImageEnhance.Color(thumb_img).enhance(1.08)
                    thumb_img = ImageEnhance.Contrast(thumb_img).enhance(1.06)
                    thumb_img = ImageEnhance.Brightness(thumb_img).enhance(1.02)
                    thumb_img = ImageEnhance.Sharpness(thumb_img).enhance(1.05)

                    thumb_img.save(out_file, "JPEG", quality=95, optimize=True)
                    LogManager.log(f"Đã tối ưu poster điện ảnh độc quyền (Giữ chữ xuôi + Tinh chỉnh màu sắc): {out_file}", "SUCCESS", "THUMBNAIL")
                    return out_file
            except Exception as e:
                LogManager.log(f"Lỗi khi xử lý thumbnail gốc: {e}. Đang chuyển sang trích xuất khung hình video.", "WARNING", "THUMBNAIL")

        # 2. Dự phòng: Trích xuất frame phim sắc nét từ video
        frame_extracted = os.path.join(output_dir, f"raw_frame_{task_id}.jpg")
        best_frame = None

        if video_path and os.path.exists(video_path):
            sample_timestamps = ["00:05:00", "00:08:30", "00:12:00", "00:03:00", "00:15:00"]
            for ts in sample_timestamps:
                try:
                    cmd = [
                        "ffmpeg", "-y",
                        "-ss", ts,
                        "-i", video_path,
                        "-vframes", "1",
                        "-q:v", "1",
                        frame_extracted
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    if os.path.exists(frame_extracted) and os.path.getsize(frame_extracted) > 15000:
                        with Image.open(frame_extracted) as test_img:
                            stat = ImageStat.Stat(test_img)
                            avg_bright = sum(stat.mean[:3]) / 3
                            if 40 < avg_bright < 220:
                                best_frame = frame_extracted
                                break
                except Exception:
                    continue

        if best_frame and os.path.exists(best_frame):
            try:
                with Image.open(best_frame) as img:
                    img = img.convert("RGB")
                    if img.height > img.width:
                        # Khung hình dọc: tạo canvas 1280x720 và căn giữa với nền mờ thẩm mỹ
                        bg = img.resize((1280, 720), Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(15))
                        scale_factor = 720.0 / img.height
                        new_w = int(img.width * scale_factor)
                        center_fg = img.resize((new_w, 720), Image.Resampling.LANCZOS)
                        paste_x = (1280 - new_w) // 2
                        bg.paste(center_fg, (paste_x, 0))
                        final_img = bg
                    else:
                        final_img = img.resize((1280, 720), Image.Resampling.LANCZOS)
                    final_img.save(out_file, "JPEG", quality=95, optimize=True)
                    LogManager.log(f"Đã tạo thumbnail điện ảnh từ video: {out_file}", "SUCCESS", "THUMBNAIL")
                    return out_file
            finally:
                if os.path.exists(frame_extracted):
                    try: os.remove(frame_extracted)
                    except Exception: pass

        return fallback_image_path
