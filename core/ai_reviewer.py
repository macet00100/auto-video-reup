import os
import re
import json
import time
import asyncio
import subprocess
import requests
import edge_tts
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
    def translate_chinese_to_vietnamese(text: str) -> str:
        """
        Dịch tự động tiêu đề/nội dung tiếng Trung sang tiếng Việt 100% miễn phí,
        kết hợp MyMemory Translated API và Google Translate endpoint dự phòng.
        """
        if not text or not text.strip():
            return ""
        clean_text = text.strip()
        # Cách 1: MyMemory Translated API
        try:
            import urllib.request, urllib.parse
            url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(clean_text)}&langpair=zh-CN|vi"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read().decode("utf-8"))
                trans = data.get("responseData", {}).get("translatedText", "").strip()
                if trans and not trans.startswith("MYMEMORY WARNING") and len(trans) > 2:
                    return trans
        except Exception:
            pass

        # Cách 2: Google Translate mobile endpoint
        try:
            import urllib.request, urllib.parse
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=zh-CN&tl=vi&dt=t&q={urllib.parse.quote(clean_text)}"
            req = urllib.request.Request(url, headers={"User-Agent": "AndroidTranslate/5.3.0.RC02.130475354-53000263 5.1 phone TRANSLATE_OPM5_TEST_1"})
            with urllib.request.urlopen(req, timeout=6) as r:
                data = json.loads(r.read().decode("utf-8"))
                res_str = "".join([part[0] for part in data[0] if part and part[0]]).strip()
                if res_str and len(res_str) > 2:
                    return res_str
        except Exception:
            pass

        return clean_text

    @staticmethod
    def generate_review_package(
        chinese_title: str,
        gemini_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sử dụng Gemini Flash để tạo trọn bộ gói nội dung Review phim vi kịch Trung Quốc.
        Đảm bảo 100% tiêu đề tiếng Việt và luôn có lời thoại thuyết minh (Voiceover).
        """
        # Bước 1: Dịch tiêu đề gốc tiếng Trung sang tiếng Việt ngay từ đầu
        translated_title = AIReviewer.translate_chinese_to_vietnamese(chinese_title)
        if not translated_title or translated_title == chinese_title:
            translated_title = "Tổng Tài Lộ Diện Vả Mặt Kẻ Bội Bạc"

        # Đảm bảo chữ hoa đầu từ đẹp mắt
        vi_title_clean = " ".join([w.capitalize() for w in translated_title.split()])
        safe_vi_title = f"Review Phim {vi_title_clean}"

        default_intro = (
            f"Chào mừng cả nhà đã quay trở lại với kênh Cool Mèo Phim! Ngày hôm nay, chúng ta sẽ cùng theo dõi bộ phim kịch tính mang tên {vi_title_clean}. "
            f"Liệu nhân vật chính sẽ vượt qua những âm mưu hãm hại, vạch trần kẻ xảo quyệt và lật ngược tình thế như thế nào? Cùng theo dõi ngay sau đây!"
        )
        default_mid = (
            f"Càng về sau, những mưu mô tính toán và bộ mặt xảo quyệt của kẻ bội bạc càng lộ rõ. "
            f"Thế nhưng chúng không thể ngờ rằng, mọi toan tính bẩn thỉu đó đều đã nằm trong tầm kiểm soát. "
            f"Thời khắc vạch trần sự thật và màn phản đòn vả mặt thích đáng chuẩn bị bắt đầu!"
        )
        default_outro = (
            "Hành trình của bộ phim hôm nay đến đây là kết thúc rồi! Các bạn thấy cái kết này đã đủ hả hê chưa? "
            "Nếu thấy hay thì đừng quên nhấn Like và bấm Đăng ký kênh Cool Mèo Phim, bật chuông thông báo để cùng đón xem những bộ phim kịch tính tiếp theo vào ngày mai nhé. "
            "Cảm ơn cả nhà rất nhiều!"
        )

        package = {
            "vietnamese_title": safe_vi_title,
            "thumbnail_hook": "VẢ MẶT KẺ ÁC",
            "thumbnail_sub": "LỘ THÂN PHẬN",
            "voice_intro": default_intro,
            "voice_mid": default_mid,
            "voice_outro": default_outro,
            "description": "",
            "tags": ["reviewphim", "phimngan", "phimhay", "tomtatphim", "haomon", "tongtai", "xuhuong"]
        }

        if gemini_key and gemini_key.strip():
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là biên tập viên review phim vi kịch Trung Quốc triệu view trên YouTube (kênh @CoolMeoPhim phong cách cuốn hút, dồn dập, gay cấn).\n"
                    f"Bộ phim gốc Trung Quốc có tên: '{chinese_title}' (tạm dịch nghĩa tiếng Việt: '{translated_title}').\n\n"
                    f"Hãy sáng tạo một gói nội dung review phim hoàn chỉnh bằng tiếng Việt:\n"
                    f"1. vietnamese_title: Tiêu đề giật gân, cuốn hút, chuẩn phong cách review phim. BẮT BUỘC bắt đầu bằng 'Review Phim ' (tuyệt đối KHÔNG dùng ký tự gạch đứng '|', KHÔNG dùng hai chấm ':', và KHÔNG dùng 'Full Trọn Bộ'), độ dài từ 65 đến 95 ký tự.\n"
                    f"2. thumbnail_hook: Đúng 1 cụm từ 3-5 chữ in hoa cực sốc để đặt lên ảnh bìa (ví dụ: VỢ CŨ PHẢN BỘI, ÉP NÀNG DÂU PHÁ THAI, ĐẠI GIA GIẢ ĂN MÀY, VẢ MẶT TIỂU TAM).\n"
                    f"3. thumbnail_sub: Cụm từ phụ 3-4 chữ in hoa (ví dụ: CÁI KẾT HẢ HÊ, LỘ THÂN PHẬN, CẢ NHÀ QUỲ LẠY).\n"
                    f"4. voice_intro: Đoạn văn thuyết minh dẫn chuyện mở đầu cực kỳ gay cấn, lôi cuốn, giọng văn kích thích tò mò tột độ dài khoảng 80-110 từ để đọc lồng tiếng trong 35-45 giây đầu của video. LƯU Ý BẮT BUỘC: TUYỆT ĐỐI KHÔNG kêu gọi Like hay Đăng ký kênh ở đoạn mở đầu này để khán giả tập trung vào cốt truyện.\n"
                    f"5. voice_mid: Đoạn thuyết minh cao trào giữa phim khoảng 70-100 từ đẩy kịch tính lên đỉnh điểm khi các âm mưu bị phơi bày và màn phản đòn vả mặt sắp diễn ra.\n"
                    f"6. voice_outro: Đoạn thuyết minh kết phim 40-60 từ chốt lại cái kết hả hê, VÀ ĐẨY TOÀN BỘ KÊU GỌI HÀNH ĐỘNG (CTA) BẤM LIKE VÀ ĐĂNG KÝ KÊNH RA ĐÂY: 'Cái kết của bộ phim hôm nay thật hả hê đúng không các bạn! Nếu thấy hay thì đừng quên nhấn Like và bấm Đăng ký kênh Cool Mèo Phim, bật chuông thông báo để cùng đón xem những tập phim kịch tính tiếp theo nhé. Cảm ơn cả nhà rất nhiều!'\n"
                    f"7. summary_hook: 2-3 câu tóm tắt mồi câu hấp dẫn cho phần đầu mô tả video.\n\n"
                    f"Trả về kết quả dưới dạng JSON:\n"
                    f"{{\n"
                    f'  "vietnamese_title": "...",\n'
                    f'  "thumbnail_hook": "...",\n'
                    f'  "thumbnail_sub": "...",\n'
                    f'  "voice_intro": "...",\n'
                    f'  "voice_mid": "...",\n'
                    f'  "voice_outro": "...",\n'
                    f'  "summary_hook": "..."\n'
                    f"}}\n"
                )

                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "response_mime_type": "application/json"
                    }
                }
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text_resp = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        text_resp = re.sub(r'^```json\s*', '', text_resp, flags=re.IGNORECASE)
                        text_resp = re.sub(r'```$', '', text_resp).strip()

                        parsed = {}
                        try:
                            parsed = json.loads(text_resp)
                        except Exception:
                            # Cứu hộ bằng Regex trích xuất từng trường nếu json.loads gặp lỗi ký tự
                            for key in ["vietnamese_title", "thumbnail_hook", "thumbnail_sub", "voice_intro", "voice_mid", "voice_outro", "summary_hook"]:
                                m = re.search(r'"' + key + r'"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', text_resp)
                                if m:
                                    parsed[key] = m.group(1).encode('utf-8').decode('unicode_escape', errors='ignore')

                        if parsed.get("vietnamese_title"):
                            vt = parsed["vietnamese_title"].replace('"', '').strip()
                            # Loại bỏ triệt để tiền tố "Full Trọn Bộ" hoặc dấu gạch đứng "|" nếu AI vô tình sinh ra
                            vt = re.sub(r'^(Full\s*Trọn\s*Bộ\s*[:|–-]?\s*)+', '', vt, flags=re.IGNORECASE).strip()
                            vt = re.sub(r'^(Review\s*Phim\s*[:|–-]?\s*)+', '', vt, flags=re.IGNORECASE).strip()
                            vt = vt.lstrip('|:–- ').strip()
                            package["vietnamese_title"] = f"Review Phim {vt}"
                        if parsed.get("thumbnail_hook"):
                            package["thumbnail_hook"] = parsed["thumbnail_hook"].replace('"', '').strip()
                        if parsed.get("thumbnail_sub"):
                            package["thumbnail_sub"] = parsed["thumbnail_sub"].replace('"', '').strip()
                        if parsed.get("voice_intro"):
                            v_in = parsed["voice_intro"].replace('"', '').strip()
                            v_in = re.sub(r'(đừng quên|nhớ|hãy)?\s*(bấm|nhấn)?\s*(like|đăng ký|sub|theo dõi)[^.!?]*[.!?]', '', v_in, flags=re.IGNORECASE).strip()
                            package["voice_intro"] = v_in or default_intro
                        if parsed.get("voice_mid"):
                            package["voice_mid"] = parsed["voice_mid"].replace('"', '').strip() or default_mid
                        if parsed.get("voice_outro"):
                            package["voice_outro"] = parsed["voice_outro"].replace('"', '').strip()

                        hook_desc = parsed.get("summary_hook", "").strip() or f"Đón xem review bộ phim kịch tính cực cuốn tại kênh @CoolMeoPhim!"
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
                LogManager.log(f"Lỗi khi gọi Gemini tạo kịch bản review: {e}. Sử dụng kịch bản dự phòng tiếng Việt chuẩn.", "WARNING", "AI_REVIEW")

        # Bộ tạo dự phòng nếu không có mạng/lỗi API (100% Tiếng Việt)
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
        voice: str = "vi-VN-NamMinhNeural",
        rate: str = "+20%"
    ) -> bool:
        """
        Tạo file âm thanh thuyết minh tiếng Việt:
        Sử dụng Edge-TTS (mặc định giọng nam NamMinhNeural chuyên nghiệp, tốc độ +20% dồn dập, cảm xúc).
        Dự phòng tự động đổi sang giọng nữ HoaiMyNeural nếu giọng nam gặp sự cố.
        Tuyệt đối không dùng gTTS để giữ trọn vẹn cảm xúc và chất lượng phòng thu.
        """
        if not text or not text.strip():
            return False

        clean_text = text.replace('"', '').replace('\n', ' ').strip()
        # Chuẩn hóa tên kênh để tránh xung đột tokenizer
        clean_text = re.sub(r'@?CoolMeoPhim', 'Cool Mèo Phim', clean_text, flags=re.IGNORECASE)
        clean_text = clean_text.replace("Cool Mèo Phim", "kênh Mèo review phim")

        LogManager.log(f"Đang tạo giọng đọc thuyết minh AI ({voice}, tốc độ {rate})...", "INFO", "TTS")

        async def _save_stream(v, r):
            communicate = edge_tts.Communicate(clean_text, v, rate=r)
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
            return os.path.exists(output_path) and os.path.getsize(output_path) > 1000

        for candidate_voice in [voice, "vi-VN-HoaiMyNeural"]:
            for attempt in range(2):
                try:
                    ok = asyncio.run(_save_stream(candidate_voice, rate))
                    if ok:
                        LogManager.log(f"Edge-TTS tạo giọng đọc thành công ({candidate_voice})! Size: {os.path.getsize(output_path)} bytes", "SUCCESS", "TTS")
                        return True
                except Exception as e_tts:
                    LogManager.log(f"Thử tạo TTS ({candidate_voice}, lần {attempt+1}) thất bại: {e_tts}", "WARNING", "TTS")
                    time.sleep(1)

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
        mid_text: str = "",
        task_id: str = ""
    ) -> Dict[str, Any]:
        """
        Tạo luồng âm thanh thuyết minh kịch tính xuyên suốt video:
        1. Intro hook: Đọc mở đầu ở t = 0s (~35-45s) khơi gợi tò mò tột độ.
        2. Mid-point recap: Đọc ở giữa phim (t ~ 40-50% thời lượng) bình luận cao trào lật mặt / phản đòn.
        3. Outro CTA: Đọc ở cuối phim (t ~ kết thúc) chốt hạ cái kết hả hê và kêu gọi Like, Đăng ký kênh.
        4. Các khoảng giữa phát nhạc nền điện ảnh lôi cuốn (BGM ducking tự động).
        """
        result = {
            "voice_path": None,
            "d_intro": 0.0,
            "mid_start": 999999.0,
            "d_mid": 0.0,
            "outro_start": 999999.0,
            "d_outro": 0.0
        }

        temp_dir = os.path.abspath(os.path.dirname(output_path))
        output_path = os.path.abspath(output_path)
        intro_file = os.path.abspath(os.path.join(temp_dir, f"intro_{task_id}.mp3"))
        mid_file = os.path.abspath(os.path.join(temp_dir, f"mid_{task_id}.mp3"))
        outro_file = os.path.abspath(os.path.join(temp_dir, f"outro_{task_id}.mp3"))
        silence1_file = os.path.abspath(os.path.join(temp_dir, f"silence1_{task_id}.mp3"))
        silence2_file = os.path.abspath(os.path.join(temp_dir, f"silence2_{task_id}.mp3"))
        concat_txt = os.path.abspath(os.path.join(temp_dir, f"voice_concat_{task_id}.txt"))

        clean_intro = intro_text.strip() if intro_text else ""
        clean_mid = mid_text.strip() if mid_text else ""
        clean_outro = outro_text.strip() if outro_text else ""

        has_intro = AIReviewer.synthesize_voiceover(clean_intro, intro_file, voice="vi-VN-NamMinhNeural", rate="+20%") if clean_intro else False
        has_mid = AIReviewer.synthesize_voiceover(clean_mid, mid_file, voice="vi-VN-NamMinhNeural", rate="+20%") if clean_mid else False
        has_outro = AIReviewer.synthesize_voiceover(clean_outro, outro_file, voice="vi-VN-NamMinhNeural", rate="+20%") if clean_outro else False

        d_intro = AIReviewer.get_audio_duration(intro_file) if has_intro else 0.0
        d_mid = AIReviewer.get_audio_duration(mid_file) if has_mid else 0.0
        d_outro = AIReviewer.get_audio_duration(outro_file) if has_outro else 0.0

        result["d_intro"] = d_intro
        result["d_mid"] = d_mid
        result["d_outro"] = d_outro

        all_temp_files = [intro_file, mid_file, outro_file, silence1_file, silence2_file, concat_txt]

        try:
            # Trường hợp 1: Có đầy đủ Intro + Mid + Outro và video đủ dài (> d_intro + d_mid + d_outro + 6s)
            if has_intro and has_mid and has_outro and total_duration_sec > (d_intro + d_mid + d_outro + 6.0):
                mid_target = max(d_intro + 1.0, total_duration_sec * 0.42)
                outro_target = max(mid_target + d_mid + 1.0, total_duration_sec - d_outro - 1.0)

                silence1_sec = max(1.0, mid_target - d_intro)
                silence2_sec = max(1.0, outro_target - (d_intro + silence1_sec + d_mid))

                # Tạo silence 1
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", f"{silence1_sec:.2f}", "-c:a", "libmp3lame", "-b:a", "192k", silence1_file
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # Tạo silence 2
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", f"{silence2_sec:.2f}", "-c:a", "libmp3lame", "-b:a", "192k", silence2_file
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                with open(concat_txt, "w", encoding="utf-8") as f:
                    f.write("file " + chr(39) + intro_file.replace("\\", "/") + chr(39) + "\n")
                    f.write("file " + chr(39) + silence1_file.replace("\\", "/") + chr(39) + "\n")
                    f.write("file " + chr(39) + mid_file.replace("\\", "/") + chr(39) + "\n")
                    f.write("file " + chr(39) + silence2_file.replace("\\", "/") + chr(39) + "\n")
                    f.write("file " + chr(39) + outro_file.replace("\\", "/") + chr(39) + "\n")

                concat_cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_txt, "-c", "copy", output_path
                ]
                subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    result["voice_path"] = output_path
                    result["mid_start"] = d_intro + silence1_sec
                    result["outro_start"] = result["mid_start"] + d_mid + silence2_sec
                    LogManager.log(f"Đã tạo audio thuyết minh 3 phần: Intro ({d_intro:.1f}s) + Giữa phim ({d_mid:.1f}s tại giây {result['mid_start']:.1f}) + Outro CTA ({d_outro:.1f}s tại giây {result['outro_start']:.1f})", "SUCCESS", "TTS")
                    return result

            # Trường hợp 2: Có Intro + Outro
            elif has_intro and has_outro and total_duration_sec > (d_intro + d_outro + 3.0):
                silence_sec = max(1.0, total_duration_sec - d_intro - d_outro - 1.0)
                subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", f"{silence_sec:.2f}", "-c:a", "libmp3lame", "-b:a", "192k", silence1_file
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                with open(concat_txt, "w", encoding="utf-8") as f:
                    f.write("file " + chr(39) + intro_file.replace("\\", "/") + chr(39) + "\n")
                    f.write("file " + chr(39) + silence1_file.replace("\\", "/") + chr(39) + "\n")
                    f.write("file " + chr(39) + outro_file.replace("\\", "/") + chr(39) + "\n")

                concat_cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_txt, "-c", "copy", output_path
                ]
                subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                    result["voice_path"] = output_path
                    result["outro_start"] = d_intro + silence_sec
                    LogManager.log(f"Đã tạo audio thuyết minh: Intro ({d_intro:.1f}s) + Outro CTA ({d_outro:.1f}s tại giây {result['outro_start']:.1f})", "SUCCESS", "TTS")
                    return result

            # Trường hợp 3: Chỉ có Intro
            elif has_intro and os.path.exists(intro_file):
                import shutil
                shutil.copy2(intro_file, output_path)
                result["voice_path"] = output_path
                result["outro_start"] = 999999.0
                return result

            # Trường hợp 4: Chỉ có Outro
            elif has_outro and os.path.exists(outro_file):
                import shutil
                shutil.copy2(outro_file, output_path)
                result["voice_path"] = output_path
                result["outro_start"] = max(0.0, total_duration_sec - d_outro)
                return result

        finally:
            for tf in all_temp_files:
                if os.path.exists(tf):
                    try: os.remove(tf)
                    except Exception: pass

        return result
