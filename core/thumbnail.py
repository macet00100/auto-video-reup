import os
import subprocess
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageStat, ImageEnhance
from core.task_queue import LogManager

class ThumbnailGenerator:
    @staticmethod
    def create_review_thumbnail(
        poster_path: Optional[str],
        hook_text: str,
        sub_text: str,
        task_id: str,
        video_path: Optional[str] = None
    ) -> Optional[str]:
        """
        Tạo ảnh thu nhỏ (Thumbnail) chuẩn phong cách Review Phim triệu view (tỷ lệ 16:9 1280x720):
        - Nền: Poster mờ tạo chiều sâu điện ảnh.
        - Phải: Poster dọc gốc của phim sắc nét.
        - Trái: Tiêu đề giật gân (hook vàng viền đen, sub trắng viền đen) + Badge [FULL TRỌN BỘ] + Watermark kênh.
        """
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "thumbnails"))
        os.makedirs(output_dir, exist_ok=True)
        out_file = os.path.join(output_dir, f"thumb_review_{task_id}.jpg")

        src_img = None
        if poster_path and os.path.exists(poster_path) and os.path.getsize(poster_path) > 3000:
            try:
                src_img = Image.open(poster_path).convert("RGB")
            except Exception:
                pass

        # Nếu không có poster, trích xuất khung hình từ video
        if src_img is None and video_path and os.path.exists(video_path):
            temp_frame = os.path.join(output_dir, f"temp_frame_{task_id}.jpg")
            try:
                cmd = ["ffmpeg", "-y", "-ss", "00:08:00", "-i", video_path, "-vframes", "1", "-q:v", "1", temp_frame]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(temp_frame):
                    src_img = Image.open(temp_frame).convert("RGB")
                    try: os.remove(temp_frame)
                    except Exception: pass
            except Exception:
                pass

        if src_img is None:
            return None

        try:
            # 1. Tạo Canvas 1280x720
            canvas = Image.new("RGB", (1280, 720), (15, 15, 20))

            # 2. Tạo hình nền mờ điện ảnh từ ảnh gốc
            bg = src_img.copy().resize((1280, 720), Image.Resampling.BILINEAR)
            bg = bg.filter(ImageFilter.GaussianBlur(radius=28))
            bg = ImageEnhance.Brightness(bg).enhance(0.42)
            canvas.paste(bg, (0, 0))

            # 3. Đặt Poster gốc sắc nét ở bên phải
            h = 700
            w = int(src_img.width * (h / src_img.height))
            if w > 600:
                w = 600
            poster_resized = src_img.resize((w, h), Image.Resampling.LANCZOS)
            # Thêm viền nhẹ cho poster
            x_poster = 1280 - w - 20
            y_poster = 10
            canvas.paste(poster_resized, (x_poster, y_poster))

            # 4. Vẽ Chữ giật gân ở bên trái
            draw = ImageDraw.Draw(canvas)
            font_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "font.ttf"))

            try:
                font_tag = ImageFont.truetype(font_path, 26)
                font_hook = ImageFont.truetype(font_path, 52)
                font_sub = ImageFont.truetype(font_path, 34)
                font_wm = ImageFont.truetype(font_path, 22)
            except Exception:
                font_tag = font_hook = font_sub = font_wm = ImageFont.load_default()

            # Tag đỏ [FULL TRỌN BỘ]
            tag_text = "FULL TRỌN BỘ"
            draw.rectangle([(40, 45), (260, 90)], fill=(220, 20, 60))
            draw.text((50, 52), tag_text, fill=(255, 255, 255), font=font_tag)

            # Hook giật gân (Vàng rực rỡ viền đen)
            clean_hook = hook_text.upper().strip()
            # Tự ngắt dòng nếu hook quá dài
            if len(clean_hook) > 16:
                words = clean_hook.split()
                mid = len(words) // 2
                hook_line1 = " ".join(words[:mid])
                hook_line2 = " ".join(words[mid:])
                draw.text((40, 140), hook_line1, fill=(255, 220, 0), font=font_hook, stroke_width=4, stroke_fill=(0, 0, 0))
                draw.text((40, 215), hook_line2, fill=(255, 220, 0), font=font_hook, stroke_width=4, stroke_fill=(0, 0, 0))
                y_sub = 310
            else:
                draw.text((40, 150), clean_hook, fill=(255, 220, 0), font=font_hook, stroke_width=5, stroke_fill=(0, 0, 0))
                y_sub = 240

            # Sub giật gân (Trắng tinh viền đen)
            if sub_text:
                clean_sub = sub_text.upper().strip()
                draw.text((40, y_sub), clean_sub, fill=(255, 255, 255), font=font_sub, stroke_width=3, stroke_fill=(0, 0, 0))

            # Nhận diện kênh @CoolMeoPhim
            draw.text((40, 650), "@CoolMeoPhim • Thuyết Minh Tiếng Việt", fill=(210, 210, 210), font=font_wm)

            # Lưu ảnh
            canvas.save(out_file, "JPEG", quality=95, optimize=True)
            LogManager.log(f"Đã tạo thumbnail Review điện ảnh hoàn hảo: {out_file}", "SUCCESS", "THUMBNAIL")
            return out_file
        except Exception as e:
            LogManager.log(f"Lỗi khi thiết kế thumbnail review: {e}", "WARNING", "THUMBNAIL")
            return None

    @staticmethod
    def create_outro_banner(
        task_id: str,
        channel_name: str = "@CoolMeoPhim"
    ) -> Optional[str]:
        """
        Tạo banner đồ họa kêu gọi Đăng ký & Like video hiển thị ở cuối phim review (tỷ lệ chuẩn HD):
        - Nền: Viên thuốc bo góc (Pill) màu tối bán trong suốt (230 alpha) viền đỏ rực rỡ.
        - Nút đỏ nổi bật: '🔔 ĐĂNG KÝ'.
        - Dòng chữ vàng/trắng cuốn hút: 'BẤM LIKE & ĐĂNG KÝ KÊNH @CoolMeoPhim NHÉ!'
        """
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "temp"))
        os.makedirs(output_dir, exist_ok=True)
        out_file = os.path.join(output_dir, f"outro_banner_{task_id}.png")

        try:
            w, h = 980, 110
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            # Nền bo góc bán trong suốt viền đỏ
            draw.rounded_rectangle([(4, 4), (w - 4, h - 4)], radius=24, fill=(18, 18, 24, 230), outline=(230, 35, 35, 255), width=3)

            font_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "font.ttf"))
            try:
                font_btn = ImageFont.truetype(font_path, 22)
                font_main = ImageFont.truetype(font_path, 26)
                font_sub = ImageFont.truetype(font_path, 18)
            except Exception:
                font_btn = font_main = font_sub = ImageFont.load_default()

            # Nút Đăng ký đỏ ở bên trái
            draw.rounded_rectangle([(25, 25), (210, 85)], radius=14, fill=(230, 35, 35, 255))
            draw.text((117, 55), "🔔 ĐĂNG KÝ", fill=(255, 255, 255, 255), font=font_btn, anchor="mm")

            # Tiêu đề kêu gọi Like & Sub
            draw.text((235, 34), f"👍 BẤM LIKE & ĐĂNG KÝ KÊNH {channel_name} NHÉ! ❤️", fill=(255, 225, 0, 255), font=font_main)
            draw.text((235, 70), "Bật chuông thông báo để đón xem những bộ phim kịch tính mỗi ngày", fill=(240, 240, 240, 240), font=font_sub)

            img.save(out_file, "PNG")
            LogManager.log(f"Đã tạo Outro Banner kêu gọi Like & Sub: {out_file}", "SUCCESS", "THUMBNAIL")
            return out_file
        except Exception as e:
            LogManager.log(f"Lỗi khi tạo Outro Banner: {e}", "WARNING", "THUMBNAIL")
            return None

    @staticmethod
    def create_thumbnail(
        video_path: Optional[str],
        fallback_image_path: Optional[str],
        title_text: str,
        task_id: str,
        style: str = "modern_yellow"
    ) -> Optional[str]:
        """Phương thức tương thích ngược với luồng cũ."""
        output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "thumbnails"))
        os.makedirs(output_dir, exist_ok=True)
        out_file = os.path.join(output_dir, f"thumb_{task_id}.jpg")

        if fallback_image_path and os.path.exists(fallback_image_path) and os.path.getsize(fallback_image_path) > 5000:
            try:
                with Image.open(fallback_image_path) as src_img:
                    thumb_img = src_img.convert("RGB")
                    if thumb_img.size != (1280, 720):
                        thumb_img = thumb_img.resize((1280, 720), Image.Resampling.LANCZOS)
                    crop_w = int(thumb_img.width * 0.015)
                    crop_h = int(thumb_img.height * 0.015)
                    thumb_img = thumb_img.crop((crop_w, crop_h, thumb_img.width - crop_w, thumb_img.height - crop_h))
                    thumb_img = thumb_img.resize((1280, 720), Image.Resampling.LANCZOS)
                    thumb_img = ImageEnhance.Color(thumb_img).enhance(1.08)
                    thumb_img = ImageEnhance.Contrast(thumb_img).enhance(1.06)
                    thumb_img.save(out_file, "JPEG", quality=95, optimize=True)
                    return out_file
            except Exception:
                pass
        return fallback_image_path
