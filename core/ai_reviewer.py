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
    2. Chuẩn hóa tiêu đề: Bắt buộc bắt đầu bằng 'Review Phim ', không gạch đứng '|', không hai chấm ':', tối đa 80 ký tự.
    3. Tạo kịch bản thuyết minh xuyên suốt (Full Narration) 600 - 850 từ liền mạch, gay cấn.
    4. Tạo giọng đọc thuyết minh tiếng Việt AI bằng Edge-TTS tốc độ x1.5 (+50%) không đứt quãng.
    5. Đẩy toàn bộ lời kêu gọi Like, Đăng ký kênh (CTA) ra đoạn kết thúc phim.
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
    def clean_review_title(title: str, max_len: int = 80) -> str:
        """
        Chuẩn hóa tiêu đề review phim:
        - Bắt buộc bắt đầu bằng: 'Review Phim '
        - Loại bỏ hoàn toàn: 'Full Trọn Bộ', 'Trọn Bộ', 'Tập Full', '|', ':', '–', '—', '-'
        - Giới hạn độ dài: tối đa max_len ký tự (mặc định 80, tuyệt đối không bị YouTube cắt cụt từ).
        - Cắt từ nguyên vẹn tại khoảng trắng cuối cùng, không bao giờ cắt cụt giữa chừng từ.
        """
        if not title:
            return "Review Phim Hay Ngắn Kịch Tính"
        t = re.sub(r'[|:–—\-]+', ' ', title)
        t = re.sub(r'\b(full\s*trọn\s*bộ|trọn\s*bộ|tập\s*full)\b', '', t, flags=re.IGNORECASE)
        t = re.sub(r'^(review\s*phim\s*)+', '', t.strip(), flags=re.IGNORECASE)
        t = re.sub(r'\s+', ' ', t).strip()
        full_title = f"Review Phim {t}"
        if len(full_title) > max_len:
            trimmed = full_title[:max_len]
            if ' ' in trimmed:
                full_title = trimmed.rsplit(' ', 1)[0].rstrip(' ,.-')
            else:
                full_title = trimmed
        return full_title

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
        Đảm bảo 100% tiêu đề tiếng Việt chuẩn, không gạch đứng, kịch bản thuyết minh xuyên suốt từ đầu đến kết.
        """
        translated_title = AIReviewer.translate_chinese_to_vietnamese(chinese_title)
        if not translated_title or translated_title == chinese_title:
            translated_title = "Tổng Tài Lộ Diện Vả Mặt Kẻ Bội Bạc"

        vi_title_clean = " ".join([w.capitalize() for w in translated_title.split()])
        safe_vi_title = AIReviewer.clean_review_title(vi_title_clean, max_len=80)

        default_p1 = (
            f"Chào mừng cả nhà đã quay trở lại với kênh review phim! Ngày hôm nay, chúng ta sẽ cùng theo dõi bộ phim kịch tính mang tên {vi_title_clean}. "
            f"Câu chuyện mở đầu với những uất ức tột cùng mà nhân vật chính phải gánh chịu từ chính những người mà mình từng tin tưởng nhất."
        )
        default_p2 = (
            f"Những âm mưu toan tính bẩn thỉu liên tục được giăng ra hòng dồn nhân vật chính vào chân tường không lối thoát. "
            f"Thế nhưng, kẻ ác không thể ngờ rằng từng bước đi đê tiện của chúng đều đã nằm trong tính toán phản kích."
        )
        default_p3 = (
            f"Thời khắc định mệnh đã đến, toàn bộ chứng cứ vạch trần bộ mặt thật của kẻ phản diện được tung ra ngay trước mắt mọi người. "
            f"Màn lật ngược tình thế và những cái tát vả mặt thích đáng khiến kẻ ác run sợ quỳ gối xin tha thứ trong nhục nhã."
        )
        default_p4 = (
            "Cái kết của bộ phim hôm nay thật hả hê đúng không các bạn! Nếu thấy hay thì đừng quên nhấn Like và bấm Đăng ký kênh Cool Mèo Phim, bật chuông thông báo để cùng đón xem những tập phim kịch tính tiếp theo nhé. Cảm ơn các bạn rất nhiều!"
        )
        default_full_narration = f"{default_p1}\n\n{default_p2}\n\n{default_p3}\n\n{default_p4}"

        package = {
            "vietnamese_title": safe_vi_title,
            "full_narration": default_full_narration,
            "thumbnail_hook": "VẢ MẶT KẺ ÁC",
            "thumbnail_sub": "LỘ THÂN PHẬN",
            "voice_intro": default_p1,
            "voice_mid": f"{default_p2}\n\n{default_p3}",
            "voice_outro": default_p4,
            "description": "",
            "tags": ["reviewphim", "phimngan", "phimhay", "tomtatphim", "haomon", "tongtai", "xuhuong"]
        }

        if gemini_key and gemini_key.strip():
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là biên tập viên review phim vi kịch Trung Quốc triệu view trên YouTube (kênh @CoolMeoPhim phong cách cuốn hút, dồn dập, gay cấn).\n"
                    f"Bộ phim gốc Trung Quốc có tên: '{chinese_title}' (tạm dịch nghĩa tiếng Việt: '{translated_title}').\n\n"
                    f"Hãy sáng tạo trọn bộ nội dung review phim hoàn chỉnh bằng tiếng Việt:\n"
                    f"1. vietnamese_title: Tiêu đề giật gân, cuốn hút. BẮT BUỘC bắt đầu bằng 'Review Phim ' (tuyệt đối KHÔNG dùng ký tự gạch đứng '|', KHÔNG dùng hai chấm ':', và KHÔNG dùng 'Full Trọn Bộ'). Độ dài tiêu đề BẮT BUỘC từ 50 đến 75 ký tự (tối đa 80 ký tự, không được viết dài quá sẽ bị YouTube cắt xén cụt từ).\n"
                    f"2. full_narration: Toàn bộ kịch bản thuyết minh kể lại trọn vẹn câu chuyện phim từ đầu đến cuối dài khoảng 650 đến 850 từ tiếng Việt, chia làm 4 đoạn văn mạch lạc phân cách bởi 2 dấu xuống dòng:\n"
                    f"   - Đoạn 1 (Mở đầu - 100 từ): Mở màn sốc, biến cố bi kịch và thân phận nhân vật (TUYỆT ĐỐI KHÔNG kêu gọi Like hay Sub ở đây).\n"
                    f"   - Đoạn 2 (Diễn biến - 250 từ): Những mưu mô hèn hạ của kẻ phản diện, sự ức hiếp và quá trình nhẫn nhịn tìm cơ hội phản đòn.\n"
                    f"   - Đoạn 3 (Cao trào - 250 từ): Thời khắc bùng nổ, thân phận thật lộ diện, màn lật ngược tình thế và vả mặt thích đáng kẻ ác trước mặt mọi người.\n"
                    f"   - Đoạn 4 (Hạ màn & Kêu gọi hành động - 60 từ): Cái kết hả hê và ĐẨY TOÀN BỘ KÊU GỌI HÀNH ĐỘNG RA ĐÂY: 'Cái kết của bộ phim hôm nay thật hả hê đúng không các bạn! Nếu thấy hay thì đừng quên nhấn Like và bấm Đăng ký kênh Cool Mèo Phim, bật chuông thông báo để cùng đón xem những tập phim kịch tính tiếp theo nhé. Cảm ơn các bạn rất nhiều!'\n"
                    f"3. thumbnail_hook: 1 cụm từ 3-5 chữ in hoa cực sốc (ví dụ: VẢ MẶT KẺ ÁC, LỘ THÂN PHẬN).\n"
                    f"4. thumbnail_sub: Cụm từ phụ 3-4 chữ in hoa (ví dụ: CẢ NHÀ QUỲ LẠY, CÁI KẾT HẢ HÊ).\n"
                    f"5. summary_hook: 2-3 câu tóm tắt gay cấn cho phần đầu mô tả video.\n\n"
                    f"Trả về kết quả dưới dạng JSON:\n"
                    f"{{\n"
                    f'  "vietnamese_title": "...",\n'
                    f'  "full_narration": "...",\n'
                    f'  "thumbnail_hook": "...",\n'
                    f'  "thumbnail_sub": "...",\n'
                    f'  "summary_hook": "..."\n'
                    f"}}\n"
                )

                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "response_mime_type": "application/json"
                    }
                }
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
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
                            for key in ["vietnamese_title", "full_narration", "thumbnail_hook", "thumbnail_sub", "summary_hook"]:
                                m = re.search(r'"' + key + r'"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', text_resp)
                                if m:
                                    parsed[key] = m.group(1).encode('utf-8').decode('unicode_escape', errors='ignore')

                        if parsed.get("vietnamese_title"):
                            package["vietnamese_title"] = AIReviewer.clean_review_title(parsed["vietnamese_title"], max_len=80)
                        if parsed.get("full_narration"):
                            fn = parsed["full_narration"].strip()
                            package["full_narration"] = fn
                            paras = [p.strip() for p in fn.split("\n") if p.strip()]
                            package["voice_intro"] = paras[0] if len(paras) > 0 else default_p1
                            package["voice_mid"] = "\n\n".join(paras[1:-1]) if len(paras) > 2 else default_p2
                            package["voice_outro"] = paras[-1] if len(paras) > 1 else default_p4
                        if parsed.get("thumbnail_hook"):
                            package["thumbnail_hook"] = parsed["thumbnail_hook"].replace('"', '').strip()
                        if parsed.get("thumbnail_sub"):
                            package["thumbnail_sub"] = parsed["thumbnail_sub"].replace('"', '').strip()

                        hook_desc = parsed.get("summary_hook", "").strip() or f"Đón xem review bộ phim kịch tính cực cuốn tại kênh @CoolMeoPhim!"
                        package["description"] = (
                            f"🎬 {package['vietnamese_title']}\n\n"
                            f"🔥 {hook_desc}\n\n"
                            f"👉 Đón xem trọn bộ review phim kịch tính cực cuốn tại kênh @CoolMeoPhim! Đừng quên bấm Like và Đăng Ký kênh để theo dõi những tập phim mới nhất mỗi ngày.\n\n"
                            f"#CoolMeoPhim #ReviewPhim #PhimNgan #TomTatPhim #PhimHay #DramaTrungQuoc #HaoMon"
                            f"{AIReviewer.FAIR_USE_DISCLAIMER}"
                        )
                        LogManager.log(f"Gemini AI đã tạo gói review hoàn chỉnh: '{package['vietnamese_title']}'", "SUCCESS", "AI_REVIEW")
                        return package
            except Exception as e:
                LogManager.log(f"Lỗi khi gọi Gemini tạo kịch bản review: {e}. Sử dụng kịch bản dự phòng chuẩn.", "WARNING", "AI_REVIEW")

        package["description"] = (
            f"🎬 {package['vietnamese_title']}\n\n"
            f"🔥 Đón xem trọn bộ review phim kịch tính cực cuốn tại kênh @CoolMeoPhim! Cùng bình luận cảm nghĩ của bạn về diễn biến tập phim này nhé.\n\n"
            f"#CoolMeoPhim #ReviewPhim #PhimNgan #TomTatPhim #PhimHay"
            f"{AIReviewer.FAIR_USE_DISCLAIMER}"
        )
        return package

    @staticmethod
    def synthesize_voiceover(
        text: str,
        output_path: str,
        voice: str = "vi-VN-NamMinhNeural",
        rate: str = "+50%"
    ) -> bool:
        """
        Tạo file âm thanh thuyết minh tiếng Việt đơn lẻ qua Edge-TTS.
        Mặc định NamMinhNeural tốc độ +50% (chuẩn x1.5 kịch tính, lôi cuốn).
        """
        if not text or not text.strip():
            return False

        clean_text = text.replace('"', '').replace('\n', ' ').strip()
        clean_text = re.sub(r'[\u4e00-\u9fff]+', '', clean_text)
        clean_text = re.sub(r'@?CoolMeoPhim', 'kênh Mèo review phim', clean_text, flags=re.IGNORECASE)
        clean_text = clean_text.replace("Cool Mèo Phim", "kênh Mèo review phim")
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        async def _save_stream(v, r):
            communicate = edge_tts.Communicate(clean_text, v, rate=r)
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
            return os.path.exists(output_path) and os.path.getsize(output_path) > 1000

        for candidate_voice in [voice, "vi-VN-HoaiMyNeural"]:
            for attempt in range(4):
                try:
                    ok = asyncio.run(_save_stream(candidate_voice, rate))
                    if ok:
                        return True
                except Exception:
                    time.sleep(1.2)

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
    def synthesize_continuous_voiceover(
        full_text: str,
        output_path: str,
        voice: str = "vi-VN-NamMinhNeural",
        rate: str = "+50%",
        task_id: str = ""
    ) -> Dict[str, Any]:
        """
        Tạo luồng âm thanh thuyết minh LIỀN MẠCH, XUYÊN SUỐT toàn bộ video review:
        1. Tách kịch bản thành các đoạn văn tự nhiên (100 - 200 từ).
        2. Tự động loại bỏ ký tự lạ/chữ Hán, chuẩn hóa tên kênh 'kênh Mèo review phim'.
        3. Sử dụng Edge-TTS (giọng NamMinhNeural tốc độ +50% chuẩn x1.5 kịch tính, dồn dập).
        4. Tự động retry 4 lần với backoff nếu Microsoft Edge-TTS từ chối kết nối ban đầu.
        5. Ghép nối thành 1 file audio hoàn chỉnh, đo thời lượng chính xác bằng ffprobe.
        """
        result = {
            "voice_path": None,
            "duration": 0.0,
            "d_intro": 30.0,
            "outro_start": 999999.0
        }

        if not full_text or not full_text.strip():
            return result

        temp_dir = os.path.abspath(os.path.dirname(output_path))
        os.makedirs(temp_dir, exist_ok=True)
        output_path = os.path.abspath(output_path)

        # Tách thành các đoạn văn
        raw_paragraphs = [p.strip() for p in full_text.split("\n") if p.strip()]
        if not raw_paragraphs:
            raw_paragraphs = [full_text.strip()]

        def clean_vietnamese_text(t: str) -> str:
            t = re.sub(r'[\u4e00-\u9fff]+', '', t)
            t = re.sub(r'@?CoolMeoPhim', 'kênh Mèo review phim', t, flags=re.IGNORECASE)
            t = t.replace("Cool Mèo Phim", "kênh Mèo review phim")
            t = re.sub(r'["\']', '', t)
            t = re.sub(r'\s+', ' ', t).strip()
            return t

        audio_parts = []
        all_temp_files = []

        LogManager.log(f"[{task_id}] Đang tổng hợp giọng đọc thuyết minh XUYÊN SUỐT ({len(raw_paragraphs)} đoạn văn, tốc độ x1.5)...", "INFO", "TTS")

        async def _save_chunk(txt: str, v: str, r: str, f_path: str):
            communicate = edge_tts.Communicate(txt, v, rate=r)
            with open(f_path, "wb") as f_out:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f_out.write(chunk["data"])

        for idx, para in enumerate(raw_paragraphs):
            clean_p = clean_vietnamese_text(para)
            if not clean_p or len(clean_p) < 5:
                continue

            part_file = os.path.abspath(os.path.join(temp_dir, f"vpart_{task_id}_{idx}.mp3"))
            all_temp_files.append(part_file)

            part_ok = False
            for voice_candidate in [voice, "vi-VN-HoaiMyNeural"]:
                for attempt in range(4):
                    try:
                        asyncio.run(_save_chunk(clean_p, voice_candidate, rate, part_file))
                        if os.path.exists(part_file) and os.path.getsize(part_file) > 1000:
                            part_ok = True
                            break
                    except Exception:
                        time.sleep(1.2)
                if part_ok:
                    break

            if part_ok:
                audio_parts.append(part_file)
            else:
                LogManager.log(f"[{task_id}] Đoạn {idx+1}/{len(raw_paragraphs)} Edge-TTS gặp sự cố kết nối.", "WARNING", "TTS")

        if not audio_parts:
            LogManager.log(f"[{task_id}] Không thể tạo audio thuyết minh.", "ERROR", "TTS")
            return result

        concat_txt = os.path.abspath(os.path.join(temp_dir, f"vconcat_{task_id}.txt"))
        all_temp_files.append(concat_txt)
        with open(concat_txt, "w", encoding="utf-8") as f:
            for ap in audio_parts:
                f.write(f"file '{ap.replace(chr(92), '/')}'\n")

        concat_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_txt, "-c", "copy", output_path
        ]
        subprocess.run(concat_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for tf in all_temp_files:
            if os.path.exists(tf):
                try: os.remove(tf)
                except Exception: pass

        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            dur = AIReviewer.get_audio_duration(output_path)
            result["voice_path"] = output_path
            result["duration"] = dur
            result["d_intro"] = min(30.0, dur * 0.2)
            result["outro_start"] = max(0.0, dur - 15.0)
            LogManager.log(f"[{task_id}] Đã tạo hoàn thành audio thuyết minh XUYÊN SUỐT: {dur:.1f}s ({dur/60:.2f} phút) tốc độ x1.5!", "SUCCESS", "TTS")

        return result

    @staticmethod
    def synthesize_full_review_voiceover(
        intro_text: str,
        outro_text: str,
        total_duration_sec: float,
        output_path: str,
        mid_text: str = "",
        task_id: str = "",
        full_text: str = ""
    ) -> Dict[str, Any]:
        """
        Wrapper tương thích ngược: Tạo audio thuyết minh xuyên suốt toàn bộ video.
        """
        combined = full_text.strip() if full_text else ""
        if not combined:
            parts = [p.strip() for p in [intro_text, mid_text, outro_text] if p.strip()]
            combined = "\n\n".join(parts)
        return AIReviewer.synthesize_continuous_voiceover(
            full_text=combined,
            output_path=output_path,
            voice="vi-VN-NamMinhNeural",
            rate="+50%",
            task_id=task_id
        )
