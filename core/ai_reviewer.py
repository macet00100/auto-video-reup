import os
import re
import json
import subprocess
import requests
from typing import Dict, Any, Optional, List
from core.task_queue import LogManager

class AIReviewer:
    """
    Module phụ trách phong cách B (AI Film Recap / Review):
    1. Chuyển ngữ và phân tích chủ đề phim Trung Quốc thành kịch bản review triệu view.
    2. Tạo tiêu đề giật gân, text cho ảnh bìa (thumbnail hook), mô tả chuẩn SEO & Fair Use.
    3. Tạo đoạn thuyết minh mở đầu kịch tính (Voice Intro hook) để giữ chân người xem 30-40s đầu.
    4. Chuyển văn bản thành giọng đọc truyền cảm bằng Edge-TTS (kèm gTTS dự phòng 100% ổn định).
    """

    FAIR_USE_DISCLAIMER = (
        "\n\n-------------------------\n"
        "⚖️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM & BẢN QUYỀN (FAIR USE):\n"
        "- Kênh @CoolMeoPhim không sở hữu toàn bộ hình ảnh gốc của bộ phim. Video được biên tập, "
        "tóm tắt, lồng tiếng thuyết minh và bình luận đánh giá nhằm mục đích giải trí và chia sẻ văn hóa điện ảnh "
        "theo nguyên tắc Sử dụng Hợp lý (Section 107 of Copyright Act 1976).\n"
        "- All rights and credits belong to their respective original owners and producers. "
        "If you are the copyright owner and have any concerns, please contact us for immediate resolution.\n"
        "👉 Đăng ký kênh @CoolMeoPhim để thưởng thức những bộ phim hay nhất mỗi ngày!"
    )

    @staticmethod
    def generate_review_package(
        chinese_title: str,
        gemini_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sử dụng Gemini Flash để tạo trọn bộ gói nội dung Review phim vi kịch Trung Quốc.
        """
        default_outro = (
            "Hành trình của bộ phim hôm nay đến đây là kết thúc rồi! Các bạn thấy cái kết này đã đủ hả hê chưa? "
            "Nếu thấy hay thì đừng quên nhấn Like và bấm Đăng ký kênh Cool Mèo Phim, bật chuông thông báo để cùng đón xem những bộ phim kịch tính tiếp theo vào ngày mai nhé. "
            "Cảm ơn cả nhà rất nhiều!"
        )

        package = {
            "vietnamese_title": f"Full Trọn Bộ | {chinese_title}",
            "thumbnail_hook": "VẢ MẶT KẺ ÁC",
            "thumbnail_sub": "ĐẠI GIA LỘ THÂN PHẬN",
            "voice_intro": "",
            "voice_outro": default_outro,
            "description": "",
            "tags": ["reviewphim", "phimngan", "phimhay", "tomtatphim", "haomon", "tongtai", "xuhuong"]
        }

        if gemini_key and gemini_key.strip():
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là biên tập viên review phim vi kịch Trung Quốc triệu view trên YouTube (kênh @CoolMeoPhim phong cách giống Triệu Vy Review, Gấu Phim).\n"
                    f"Bộ phim gốc Trung Quốc có tên: '{chinese_title}'.\n\n"
                    f"Hãy sáng tạo một gói nội dung review phim hoàn chỉnh bằng tiếng Việt:\n"
                    f"1. vietnamese_title: Tiêu đề giật gân, cuốn hút, chuẩn phong cách review phim, bắt buộc có tiền tố 'Full Trọn Bộ | ', độ dài từ 65 đến 95 ký tự.\n"
                    f"2. thumbnail_hook: Đúng 1 cụm từ 3-5 chữ in hoa cực sốc để đặt lên ảnh bìa (ví dụ: VỢ CŨ PHẢN BỘI, ÉP NÀNG DÂU PHÁ THAI, ĐẠI GIA GIẢ ĂN MÀY, VẢ MẶT TIỂU TAM).\n"
                    f"3. thumbnail_sub: Cụm từ phụ 3-4 chữ in hoa (ví dụ: CÁI KẾT HẢ HÊ, LỘ THÂN PHẬN, CẢ NHÀ QUỲ LẠY).\n"
                    f"4. voice_intro: Đoạn văn thuyết minh dẫn chuyện mở đầu cực kỳ gay cấn, lôi cuốn, văn phong kích thích tò mò tột độ dài khoảng 60-90 từ để đọc lồng tiếng trong 25-35 giây đầu của video.\n"
                    f"5. voice_outro: Đoạn thuyết minh kết phim 35-50 từ chốt lại cái kết, và kêu gọi hành động (CTA) thật cuốn hút: 'Cái kết của bộ phim hôm nay thật hả hê đúng không các bạn! Nếu thấy hay thì đừng quên nhấn Like và bấm Đăng ký kênh Cool Mèo Phim, bật chuông thông báo để cùng đón xem những tập phim kịch tính tiếp theo nhé. Cảm ơn cả nhà rất nhiều!'\n"
                    f"6. summary_hook: 2-3 câu tóm tắt mồi câu hấp dẫn cho phần đầu mô tả video.\n\n"
                    f"Trả về kết quả dưới dạng JSON duy nhất:\n"
                    f"{{\n"
                    f'  "vietnamese_title": "...",\n'
                    f'  "thumbnail_hook": "...",\n'
                    f'  "thumbnail_sub": "...",\n'
                    f'  "voice_intro": "...",\n'
                    f'  "voice_outro": "...",\n'
                    f'  "summary_hook": "..."\n'
                    f"}}\n"
                    f"Chỉ trả về JSON thuần túy, không có thẻ markdown hay văn bản nào khác."
                )

                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text_resp = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        # Làm sạch nếu có markdown ```json ... ```
                        text_resp = re.sub(r'^```json\s*', '', text_resp, flags=re.IGNORECASE)
                        text_resp = re.sub(r'```$', '', text_resp).strip()
                        parsed = json.loads(text_resp)

                        package["vietnamese_title"] = parsed.get("vietnamese_title", package["vietnamese_title"]).replace('"', '').strip()
                        package["thumbnail_hook"] = parsed.get("thumbnail_hook", package["thumbnail_hook"]).replace('"', '').strip()
                        package["thumbnail_sub"] = parsed.get("thumbnail_sub", package["thumbnail_sub"]).replace('"', '').strip()
                        package["voice_intro"] = parsed.get("voice_intro", "").replace('"', '').strip()
                        package["voice_outro"] = parsed.get("voice_outro", default_outro).replace('"', '').strip()

                        hook_desc = parsed.get("summary_hook", "").strip()
                        package["description"] = (
                            f"🎬 {package['vietnamese_title']}\n\n"
                            f"🔥 {hook_desc}\n\n"
                            f"👉 Đón xem trọn bộ phim kịch tính cực cuốn tại kênh @CoolMeoPhim! Đừng quên bấm Like và Đăng Ký kênh để theo dõi những tập phim mới nhất mỗi ngày.\n\n"
                            f"#CoolMeoPhim #ReviewPhim #PhimNgan #TomTatPhim #PhimHay #DramaTrungQuoc #HaoMon"
                            f"{AIReviewer.FAIR_USE_DISCLAIMER}"
                        )
                        LogManager.log(f"Gemini AI đã tạo gói review hoàn chỉnh kèm Outro CTA: '{package['vietnamese_title']}'", "SUCCESS", "AI_REVIEW")
                        return package
            except Exception as e:
                LogManager.log(f"Lỗi khi gọi Gemini tạo kịch bản review: {e}. Kích hoạt bộ tạo dự phòng.", "WARNING", "AI_REVIEW")

        # Bộ tạo dự phòng nếu không có mạng/lỗi API
        package["description"] = (
            f"🎬 {package['vietnamese_title']}\n\n"
            f"🔥 Đón xem trọn bộ phim kịch tính cực cuốn tại kênh @CoolMeoPhim! Cùng bình luận cảm nghĩ của bạn về diễn biến tập phim này nhé.\n\n"
            f"#CoolMeoPhim #ReviewPhim #PhimNgan #TomTatPhim #PhimHay"
            f"{AIReviewer.FAIR_USE_DISCLAIMER}"
        )
        return package

    @staticmethod
    def synthesize_voiceover(
        text: str,
        output_path: str,
        voice: str = "vi-VN-HoaiMyNeural"
    ) -> bool:
        """
        Tạo file âm thanh thuyết minh tiếng Việt:
        Ưu tiên Edge-TTS (giọng Hoài My truyền cảm); nếu mạng chập chờn sẽ tự động chuyển sang gTTS.
        """
        if not text or not text.strip():
            return False

        clean_text = text.replace('"', '').replace('\n', ' ').strip()
        LogManager.log(f"Đang tạo giọng đọc thuyết minh AI...", "INFO", "TTS")

        # CÁCH 1: Thử Edge-TTS
        try:
            cmd = [
                "edge-tts",
                "--voice", voice,
                "--text", clean_text,
                "--write-media", output_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                LogManager.log(f"Edge-TTS tạo giọng đọc thành công! Size: {os.path.getsize(output_path)} bytes", "SUCCESS", "TTS")
                return True
        except Exception:
            pass

        # CÁCH 2: Dự phòng bằng gTTS (Google Translate TTS - 100% không bao giờ lỗi)
        try:
            from gtts import gTTS
            tts = gTTS(text=clean_text, lang='vi')
            tts.save(output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                LogManager.log(f"gTTS tạo giọng đọc dự phòng thành công! Size: {os.path.getsize(output_path)} bytes", "SUCCESS", "TTS")
                return True
        except Exception as e_gtts:
            LogManager.log(f"Lỗi khi tạo TTS dự phòng: {e_gtts}", "ERROR", "TTS")

        return False

    @staticmethod
    def get_audio_duration(audio_path: str) -> float:
        """Đo thời lượng file audio chính xác bằng ffprobe."""
        try:
            cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", audio_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 0.0

    @staticmethod
    def synthesize_full_review_voiceover(
        intro_text: str,
        outro_text: str,
        total_duration_sec: float,
        output_path: str,
        task_id: str = ""
    ) -> Dict[str, Any]:
        """
        Tạo luồng âm thanh thuyết minh hoàn chỉnh:
        1. Intro hook: Đọc ở đầu phim (t = 0s).
        2. Đoạn giữa: Khoảng lặng để giữ trọn thoại phim và hiệu ứng âm thanh.
        3. Outro CTA: Kêu gọi Like & Đăng ký kênh @CoolMeoPhim ở cuối phim.
        """
        result = {
            "voice_path": None,
            "d_intro": 0.0,
            "outro_start": 999999.0,
            "d_outro": 0.0
        }

        temp_dir = os.path.abspath(os.path.dirname(output_path))
        output_path = os.path.abspath(output_path)
        intro_file = os.path.abspath(os.path.join(temp_dir, f"intro_{task_id}.mp3"))
        outro_file = os.path.abspath(os.path.join(temp_dir, f"outro_{task_id}.mp3"))
        silence_file = os.path.abspath(os.path.join(temp_dir, f"silence_{task_id}.mp3"))
        concat_txt = os.path.abspath(os.path.join(temp_dir, f"voice_concat_{task_id}.txt"))

        # Chuẩn hóa phát âm tự nhiên cho tên kênh
        clean_intro = intro_text.replace("@CoolMeoPhim", "Cool Mèo Phim").strip() if intro_text else ""
        clean_outro = outro_text.replace("@CoolMeoPhim", "Cool Mèo Phim").strip() if outro_text else ""

        has_intro = AIReviewer.synthesize_voiceover(clean_intro, intro_file) if clean_intro else False
        has_outro = AIReviewer.synthesize_voiceover(clean_outro, outro_file) if clean_outro else False

        d_intro = AIReviewer.get_audio_duration(intro_file) if has_intro else 0.0
        d_outro = AIReviewer.get_audio_duration(outro_file) if has_outro else 0.0

        result["d_intro"] = d_intro
        result["d_outro"] = d_outro

        try:
            if has_intro and has_outro and total_duration_sec > (d_intro + d_outro + 3.0):
                silence_sec = max(1.0, total_duration_sec - d_intro - d_outro - 1.0)
                silence_cmd = [
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", f"{silence_sec:.2f}",
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    silence_file
                ]
                subprocess.run(silence_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                with open(concat_txt, "w", encoding="utf-8") as f:
                    f.write("file " + chr(39) + intro_file.replace("\\", "/") + chr(39) + "\n")
                    f.write("file " + chr(39) + silence_file.replace("\\", "/") + chr(39) + "\n")
                    f.write("file " + chr(39) + outro_file.replace("\\", "/") + chr(39) + "\n")

                concat_cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_txt, "-c", "copy", output_path
                ]
                subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    result["voice_path"] = output_path
                    result["outro_start"] = d_intro + silence_sec
                    LogManager.log(f"Đã tạo audio thuyết minh trọn gói: Intro ({d_intro:.1f}s) + Khoảng lặng ({silence_sec:.1f}s) + Outro CTA ({d_outro:.1f}s tại giây {result['outro_start']:.1f})", "SUCCESS", "TTS")
                    return result

            elif has_intro:
                if os.path.exists(intro_file):
                    import shutil
                    shutil.copy2(intro_file, output_path)
                    result["voice_path"] = output_path
                    result["outro_start"] = 999999.0
                    return result
            elif has_outro:
                if os.path.exists(outro_file):
                    import shutil
                    shutil.copy2(outro_file, output_path)
                    result["voice_path"] = output_path
                    result["outro_start"] = max(0.0, total_duration_sec - d_outro)
                    return result

        finally:
            for tf in [intro_file, outro_file, silence_file, concat_txt]:
                if os.path.exists(tf):
                    try: os.remove(tf)
                    except Exception: pass

        return result
