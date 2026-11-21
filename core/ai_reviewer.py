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
    2. Chuẩn hóa tiêu đề: Bắt buộc bắt đầu bằng 'Review Phim ', không gạch đứng '|', không hai chấm ':', tối đa 80 ký tự, không lẫn chữ Hán.
    3. Tạo kịch bản thuyết minh xuyên suốt (Full Narration) 950 - 1250 từ (chuẩn thời lượng 5 - 7 phút), liền mạch, gay cấn.
    4. Tạo giọng đọc thuyết minh tiếng Việt AI bằng Edge-TTS tốc độ x1.5 (+50%) không đứt quãng, kèm gTTS cứu hộ tự động.
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
        - Loại bỏ hoàn toàn: chữ Hán, 'Full Trọn Bộ', 'Trọn Bộ', 'Tập Full', '|', ':', '–', '—', '-'
        - Giới hạn độ dài: tối đa max_len ký tự (mặc định 80, tuyệt đối không bị YouTube cắt cụt từ).
        - Cắt từ nguyên vẹn tại khoảng trắng cuối cùng, không bao giờ cắt cụt giữa chừng từ.
        """
        if not title:
            return "Review Phim Hay Ngắn Kịch Tính"
        t = re.sub(r'[\u4e00-\u9fff]+', '', title)
        t = re.sub(r'[|:–—\-]+', ' ', t)
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
        Đảm bảo 100% tiêu đề tiếng Việt chuẩn, không gạch đứng, kịch bản thuyết minh xuyên suốt từ đầu đến kết (5 - 7 phút).
        """
        translated_title = AIReviewer.translate_chinese_to_vietnamese(chinese_title)
        if not translated_title or translated_title == chinese_title:
            translated_title = "Tổng Tài Lộ Diện Vả Mặt Kẻ Bội Bạc"

        vi_title_clean = " ".join([w.capitalize() for w in translated_title.split()])
        safe_vi_title = AIReviewer.clean_review_title(vi_title_clean, max_len=80)

        default_p1 = (
            f"Chào mừng tất cả quý vị khán giả đã quay trở lại với kênh review phim Cool Mèo Phim! Ngày hôm nay, chúng ta sẽ cùng bước vào một hành trình đầy kịch tính và nghẹt thở mang tên {vi_title_clean}. "
            f"Ngay từ những phút đầu tiên, bộ phim đã đưa người xem vào một tình thế vô cùng trớ trêu và uất ức khi nhân vật chính bất ngờ rơi vào nghịch cảnh nghiệt ngã. "
            f"Những tưởng cuộc sống sẽ êm đềm trôi qua, nhưng sự đố kỵ và lòng tham vô đáy của những kẻ xung quanh đã nhanh chóng xé nát tất cả. "
            f"Từ một người lương thiện, nhân vật chính bỗng chốc trở thành mục tiêu công kích, bị chính những người thân thiết nhất quay lưng, phản bội và giáng xuống những đòn trừng phạt bất công."
        )
        default_p2 = (
            f"Càng về sau, dã tâm của những kẻ phản diện càng lộ rõ một cách trắng trợn và ghê tởm. "
            f"Chúng không từ bất kỳ thủ đoạn hèn hạ nào, từ việc đặt điều vu oan giáng họa, ngụy tạo bằng chứng giả mạo cho đến việc câu kết với các thế lực đen tối bên ngoài nhằm đẩy nhân vật chính vào bước đường cùng không lối thoát. "
            f"Từng cái nhìn khinh bỉ, từng lời sỉ nhục cay đắng giáng xuống như những mũi dao sắc nhọn cứa sâu vào lòng tự trọng. "
            f"Trước mặt bàn dân thiên hạ, chúng hả hê đắc thắng, ngỡ rằng bản thân đã hoàn toàn làm chủ cuộc chơi và có thể dẫm đạp lên công lý một cách dễ dàng."
        )
        default_p3 = (
            f"Thế nhưng, kẻ ác đã phạm phải một sai lầm chết người khi đánh giá quá thấp sự kiên cường và bản lĩnh của nhân vật chính. "
            f"Sau những chuỗi ngày nhẫn nhịn và chịu đựng trong cay đắng, đây chính là lúc ngọn lửa phản kháng bùng cháy dữ dội. "
            f"Thay vì gục ngã hay van xin lòng thương hại vô nghĩa, nhân vật chính đã âm thầm thức tỉnh, thu thập từng manh mối và vạch ra một kế hoạch phản công hoàn hảo đến từng chi tiết. "
            f"Từng cái bẫy mà kẻ ác giăng ra giờ đây đều được chuyển hóa thành những chiếc thòng lọng siết chặt lấy chính cổ họng của chúng."
        )
        default_p4 = (
            f"Và rồi, khoảnh khắc bùng nổ đỉnh cao mà tất cả khán giả mong chờ nhất cũng đã chính thức điểm tại đại sảnh sự kiện quan trọng nhất. "
            f"Khi những kẻ phản diện đang say sưa trên đỉnh cao ngạo mạn, nhân vật chính bất ngờ xuất hiện với phong thái đĩnh đạc và tung ra toàn bộ bằng chứng thép không thể chối cãi. "
            f"Màn lật bài ngửa diễn ra chớp nhoáng khiến toàn thể hội trường bàng hoàng chấn động, còn bộ mặt giả tạo của kẻ ác thì biến sắc trắng bệch trong kinh hãi. "
            f"Từng cái tát vả mặt nảy lửa, từng lời tuyên án đanh thép giáng xuống khiến kẻ ác run rẩy quỳ rạp dưới chân van xin tha thứ trong sự khinh bỉ của tất cả mọi người."
        )
        default_p5 = (
            f"Cái kết của bộ phim hôm nay thật sự quá đỗi hả hê và mãn nhãn đúng không các bạn! Kẻ thủ ác cuối cùng đã phải trả một cái giá vô cùng đắt cho những tội lỗi mà mình gây ra, đúng như quy luật nhân quả không chừa một ai. "
            f"Nếu các bạn thấy bản review phim hôm nay kịch tính và hấp dẫn thì đừng quên nhấn Like và bấm Đăng ký kênh Cool Mèo Phim, bật chuông thông báo để không bỏ lỡ những tập phim gay cấn tiếp theo nhé. Cảm ơn cả nhà rất nhiều!"
        )
        default_full_narration = f"{default_p1}\n\n{default_p2}\n\n{default_p3}\n\n{default_p4}\n\n{default_p5}"

        package = {
            "vietnamese_title": safe_vi_title,
            "full_narration": default_full_narration,
            "thumbnail_hook": "VẢ MẶT KẺ ÁC",
            "thumbnail_sub": "LỘ THÂN PHẬN",
            "voice_intro": default_p1,
            "voice_mid": f"{default_p2}\n\n{default_p3}\n\n{default_p4}",
            "voice_outro": default_p5,
            "description": "",
            "tags": ["reviewphim", "phimngan", "phimhay", "tomtatphim", "haomon", "tongtai", "xuhuong"]
        }

        if gemini_key and gemini_key.strip():
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là biên tập viên review phim vi kịch Trung Quốc triệu view trên YouTube (kênh @CoolMeoPhim phong cách cuốn hút, dồn dập, gay cấn).\n"
                    f"Bộ phim gốc Trung Quốc có tên: '{chinese_title}' (tạm dịch nghĩa tiếng Việt: '{translated_title}').\n\n"
                    f"YÊU CẦU ĐẶC BIỆT QUAN TRỌNG VỀ ĐỘ DÀI: Video review phải đạt chuẩn thời lượng 5 đến 7 phút. Do đó, bạn BẮT BUỘC phải viết kịch bản thuyết minh thật chi tiết, gay cấn, dài từ 950 đến 1250 từ tiếng Việt (tuyệt đối KHÔNG viết tóm tắt ngắn dưới 900 từ).\n\n"
                    f"Cấu trúc kịch bản gồm 5 đoạn văn rõ ràng, phân cách bởi 2 dấu xuống dòng:\n"
                    f"1. Đoạn 1 (Mở đầu - 180-220 từ): Bối cảnh sốc, thân phận trớ trêu của nhân vật chính, biến cố bất công ban đầu và sự phản bội của kẻ xấu (TUYỆT ĐỐI KHÔNG kêu gọi Like hay Sub ở đây).\n"
                    f"2. Đoạn 2 (Âm mưu - 200-250 từ): Những mưu mô hèn hạ, sự vu oan giáng họa, chèn ép dồn dập của kẻ phản diện và nỗi uất ức dồn nén.\n"
                    f"3. Đoạn 3 (Chuyển biến - 200-250 từ): Nhân vật chính thức tỉnh, nhẫn nhịn tìm sơ hở, âm thầm thu thập chứng cứ và giăng lưới phản kích.\n"
                    f"4. Đoạn 4 (Cao trào vả mặt - 220-270 từ): Thời khắc bùng nổ trước đông đảo mọi người, đòn phản kích chí mạng, lật ngược thế cờ và vả mặt thích đáng kẻ ác.\n"
                    f"5. Đoạn 5 (Hạ màn & Kêu gọi hành động - 80-100 từ): Cái kết hả hê trọn vẹn, bài học nhân quả và ĐẨY TOÀN BỘ KÊU GỌI HÀNH ĐỘNG RA ĐÂY: 'Cái kết của bộ phim hôm nay thật hả hê đúng không các bạn! Nếu thấy hay thì đừng quên nhấn Like và bấm Đăng ký kênh Cool Mèo Phim, bật chuông thông báo để cùng đón xem những tập phim kịch tính tiếp theo nhé. Cảm ơn các bạn rất nhiều!'\n\n"
                    f"YÊU CẦU TIÊU ĐỀ: vietnamese_title BẮT BUỘC bắt đầu bằng 'Review Phim ' (tuyệt đối KHÔNG dùng ký tự '|', KHÔNG dùng ':', KHÔNG dùng 'Full Trọn Bộ'). Độ dài từ 50 đến 75 ký tự (tối đa 80 ký tự, tuyệt đối không lẫn chữ Hán).\n\n"
                    f"Trả về duy nhất định dạng JSON:\n"
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
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=35)
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
                            # Kiểm tra độ dài kịch bản: Nếu ít hơn 500 từ thì nối thêm phần cao trào để đảm bảo đạt 5 phút
                            if len(fn.split()) < 500:
                                fn = f"{fn}\n\n{default_p3}\n\n{default_p4}\n\n{default_p5}"
                            package["full_narration"] = fn
                            paras = [p.strip() for p in fn.split("\n") if p.strip()]
                            package["voice_intro"] = paras[0] if len(paras) > 0 else default_p1
                            package["voice_mid"] = "\n\n".join(paras[1:-1]) if len(paras) > 2 else default_p2
                            package["voice_outro"] = paras[-1] if len(paras) > 1 else default_p5
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
                        LogManager.log(f"Gemini AI đã tạo kịch bản review dài chuẩn 5-7 phút: '{package['vietnamese_title']}' ({len(package['full_narration'].split())} từ)", "SUCCESS", "AI_REVIEW")
                        return package
            except Exception as e:
                LogManager.log(f"Lỗi khi gọi Gemini tạo kịch bản review: {e}. Sử dụng kịch bản dự phòng 5-7 phút chuẩn.", "WARNING", "AI_REVIEW")

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
        Tạo file âm thanh thuyết minh tiếng Việt đơn lẻ qua Edge-TTS (kèm gTTS cứu hộ).
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
            for attempt in range(3):
                try:
                    ok = asyncio.run(_save_stream(candidate_voice, rate))
                    if ok:
                        return True
                except Exception:
                    time.sleep(1.0)

        # Cứu hộ tự động bằng gTTS nếu Edge-TTS tạm thời bị nghẽn mạng
        try:
            from gtts import gTTS
            temp_gtts = output_path + ".gtts.mp3"
            tts = gTTS(clean_text, lang="vi")
            tts.save(temp_gtts)
            subprocess.run(["ffmpeg", "-y", "-i", temp_gtts, "-af", "atempo=1.45", output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(temp_gtts): os.remove(temp_gtts)
            return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
        except Exception:
            pass

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
        Tạo luồng âm thanh thuyết minh LIỀN MẠCH, XUYÊN SUỐT toàn bộ video review (5 - 7 phút):
        1. Tách kịch bản thành các đoạn văn tự nhiên (150 - 250 từ).
        2. Tự động loại bỏ ký tự lạ/chữ Hán, chuẩn hóa tên kênh 'kênh Mèo review phim'.
        3. Sử dụng Edge-TTS (giọng NamMinhNeural tốc độ +50% chuẩn x1.5 kịch tính, dồn dập).
        4. Tự động chuyển đổi gTTS cứu hộ 100% không bao giờ gián đoạn.
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

        LogManager.log(f"[{task_id}] Đang tổng hợp giọng đọc thuyết minh XUYÊN SUỐT ({len(raw_paragraphs)} đoạn văn, tốc độ x1.5 chuẩn 5-7 phút)...", "INFO", "TTS")

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
                for attempt in range(3):
                    try:
                        asyncio.run(_save_chunk(clean_p, voice_candidate, rate, part_file))
                        if os.path.exists(part_file) and os.path.getsize(part_file) > 1000:
                            part_ok = True
                            break
                    except Exception:
                        time.sleep(1.0)
                if part_ok:
                    break

            # Cứu hộ tự động bằng gTTS nếu Edge-TTS mạng chập chờn
            if not part_ok:
                try:
                    from gtts import gTTS
                    g_temp = os.path.abspath(os.path.join(temp_dir, f"gtemp_{task_id}_{idx}.mp3"))
                    tts = gTTS(clean_p, lang="vi")
                    tts.save(g_temp)
                    subprocess.run(["ffmpeg", "-y", "-i", g_temp, "-af", "atempo=1.45", part_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.exists(g_temp): os.remove(g_temp)
                    if os.path.exists(part_file) and os.path.getsize(part_file) > 1000:
                        part_ok = True
                        LogManager.log(f"[{task_id}] Đoạn {idx+1}/{len(raw_paragraphs)} đã tự động cứu hộ bằng giọng gTTS x1.45 thành công!", "SUCCESS", "TTS")
                except Exception as e_g:
                    LogManager.log(f"[{task_id}] Lỗi cứu hộ gTTS đoạn {idx+1}: {e_g}", "WARNING", "TTS")

            if part_ok:
                audio_parts.append(part_file)
            else:
                LogManager.log(f"[{task_id}] Đoạn {idx+1}/{len(raw_paragraphs)} không thể tạo âm thanh.", "WARNING", "TTS")

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
            result["d_intro"] = min(30.0, dur * 0.15)
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
