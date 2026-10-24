import re
from typing import Optional, Tuple, List
from core.task_queue import LogManager

class AIRewriter:
    # Từ điển từ đồng nghĩa chuyên sâu về văn phong review phim / vi kịch / phim bộ
    PHRASE_SYNONYMS = [
        # Cụm dài đặc thù
        ("lấy nhầm chồng khiến cả nhà cô tan nát", "gả nhầm người làm gia đình lụi tàn"),
        ("lấy nhầm chồng khiến cả nhà", "gả nhầm người làm gia đình"),
        ("kiếp trước lấy nhầm chồng", "đời trước gả nhầm người"),
        ("lấy nhầm chồng", "gả nhầm người"),
        ("thân phận thật xuất thế", "thân phận thực sự hé lộ"),
        ("thân phận thật sự", "thân phận thực chất"),
        ("thân phận thật", "thân phận thực sự"),
        ("khiến cả nhà quỳ lạy", "làm cả nhà kinh sợ"),
        ("khiến cả nhà", "làm gia đình"),
        ("khiến gia tộc", "làm gia tộc"),
        ("bị vợ cũ coi thường", "bị vợ trước xem nhẹ"),
        ("bị vợ cũ khinh thường", "bị vợ trước xem thường"),
        ("cô mừng vì quê cũ", "nàng mừng rỡ về quê"),
        ("dùng kiến thức khai hoang", "vận dụng tài trí lập nghiệp"),
        ("dùng kiến thức", "vận dụng tài trí"),
        ("kẻ phản bội", "kẻ quay lưng"),
        ("tổng tài giả nghèo", "chủ tịch giấu thân phận"),
        ("chủ tịch tập đoàn", "ông trùm tập đoàn"),
        ("con rể phế vật", "chàng rể vô dụng"),
        ("bị nhà vợ coi thường", "bị gia đình vợ xem thường"),
        ("bị đày lĩnh nam", "bị lưu đày lĩnh nam"),
        ("hủy hôn, cứu", "từ hôn, bảo vệ"),
        ("hủy hôn", "từ hôn"),

        # Cụm từ và thuật ngữ phim ảnh
        ("kiếp trước", "đời trước"),
        ("kiếp này", "sống lại"),
        ("lấy nhầm", "chọn nhầm"),
        ("tan nát", "lụi tàn"),
        ("cứu gia tộc", "bảo vệ gia tộc"),
        ("cứu gia đình", "bảo vệ gia đình"),
        ("cứu cả nhà", "giải cứu gia đình"),
        ("cứu gi", "bảo vệ gi"),
        ("xuyên thành phu nhân", "xuyên không làm phu nhân"),
        ("xuyên thành", "trở thành"),
        ("bị đày", "bị lưu đày"),
        ("cô mừng vì", "nàng vui mừng vì"),
        ("khai hoang", "lập nghiệp"),
        ("tổng tài", "chủ tịch"),
        ("giả nghèo", "giấu thân phận"),
        ("khinh thường", "xem thường"),
        ("coi thường", "xem nhẹ"),
        ("vợ cũ", "vợ trước"),
        ("chồng cũ", "chồng trước"),
        ("hóa ra là", "ngờ đâu là"),
        ("thực ra là", "thực chất là"),
        ("trả thù", "tính sổ"),
        ("báo thù", "đòi lại công đạo"),
        ("phản bội", "quay lưng"),
        ("bị bỏ rơi", "bị xua đuổi"),
        ("bỏ rơi", "ruồng bỏ"),
        ("hối hận", "muộn màng nhận ra"),
        ("quỳ lạy", "kinh sợ")
    ]

    @staticmethod
    def extract_part_and_clean(raw_title: str) -> Tuple[Optional[str], str]:
        """
        1. Bỏ toàn bộ các từ giật tít vô nghĩa: 'Cực sốc', 'Cận cảnh', 'Khám phá ngay'...
        2. Bỏ hashtag (#reviewphim...) và hậu tố rác '(Cực cuốn)', '(Full HD)'...
        3. Tách phần phim (P3, P6, Phần 3, Tập 3...) nếu có.
        Trả về (part_num, clean_title_body)
        """
        t = re.sub(r'#\w+', '', raw_title).strip()

        # Bỏ các hook giật tít rác ở đầu và đuôi
        junk_patterns = [
            r'^(cực sốc|cận cảnh|khám phá ngay|toàn cảnh bí mật|bất ngờ với|không thể tin được|sự thật về|xem ngay kẻo lỡ|chi tiết về|đỉnh cao của)[\s:\-]+',
            r'[\(\[](cực cuốn|không xem sẽ tiếc|quá bất ngờ|đỉnh cao|mới nhất hôm nay|chi tiết a-z|xem là nghiện|bản full|full hd|thuyết minh|vietsub|review phim|tóm tắt phim|full bộ|trọn bộ|review|full)[\)\]]',
            r'[\s\|\-]+(full bộ|trọn bộ|bản full|full hd|thuyết minh|vietsub|review phim|tóm tắt phim|review|full)$'
        ]
        for p in junk_patterns:
            t = re.sub(p, '', t, flags=re.IGNORECASE).strip()

        # Phát hiện phần phim: P3, P4, P5, P.3, P 3, Phần 3, Tập 3, Part 3...
        part_num = None
        m = re.search(r'\b(?:P|Phần|Tập|Part)\.?\s*(\d+)\b', t, flags=re.IGNORECASE)
        if m:
            part_num = m.group(1)
            t = re.sub(r'\b(?:P|Phần|Tập|Part)\.?\s*' + part_num + r'\b[\s:\-\.]*', '', t, flags=re.IGNORECASE).strip()

        # Làm sạch ký tự phân cách ở đầu và đuôi
        t = re.sub(r'^[\s:\-\.\,\|]+', '', t).strip()
        t = re.sub(r'[\s:\-\.\,\|]+$', '', t).strip()

        return part_num, t

    @staticmethod
    def clean_and_format_title(raw_title: str) -> str:
        """
        Làm sạch và quy chuẩn hóa tên phim: đưa Phần X lên đầu và bỏ từ rác.
        """
        part_num, clean_body = AIRewriter.extract_part_and_clean(raw_title)
        if part_num:
            return f"Phần {part_num} - {clean_body}".strip()
        return clean_body.strip()

    @staticmethod
    def paraphrase_text(text: str) -> str:
        """
        Bộ biến tấu từ vựng & ngữ nghĩa thông minh (Smart Vietnamese Paraphraser):
        - Thay thế các cụm từ quen thuộc bằng từ đồng nghĩa tự nhiên trong văn phong review phim.
        - Giữ nguyên nghĩa cốt truyện nhưng tạo câu từ mới mẻ để tránh bị quét trùng lặp / bản quyền với kênh nguồn.
        - Tự động duy trì kiểu chữ (Title Case / Lowercase).
        """
        res = text
        for orig, syn in AIRewriter.PHRASE_SYNONYMS:
            pattern = re.compile(re.escape(orig), re.IGNORECASE)
            def repl(m):
                val = m.group(0)
                if val.istitle() or (len(val) > 1 and val[0].isupper() and val[1:].islower()):
                    return syn.title()
                elif val.isupper():
                    return syn.upper()
                else:
                    return syn
            res = pattern.sub(repl, res)
        return res

    @staticmethod
    def rewrite_title(original_title: str, gemini_key: Optional[str] = None, openai_key: Optional[str] = None) -> str:
        # Bước 1: Tách phần phim và làm sạch rác
        part_num, clean_body = AIRewriter.extract_part_and_clean(original_title)

        rewritten_body = None

        # Bước 2: Thử dùng Google Gemini nếu có cấu hình key
        if gemini_key and gemini_key.strip():
            try:
                import requests
                # Sử dụng API REST với model gemini-flash-lite-latest phản hồi siêu nhanh và ổn định
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là biên tập viên review phim chuyên nghiệp.\n"
                    f"Nhiệm vụ: Viết lại tiêu đề phim sau đây sang cách diễn đạt mới mẻ, tự nhiên và cuốn hút:\n"
                    f"1. Giữ trọn vẹn ý nghĩa cốt truyện, nhân vật và bối cảnh.\n"
                    f"2. Thay đổi từ ngữ, đảo ngữ hoặc dùng từ đồng nghĩa để câu văn hoàn toàn mới lạ, hấp dẫn, KHÔNG BỊ TRÙNG VĂN BẢN với nguồn để tránh quét bản quyền.\n"
                    f"3. TUYỆT ĐỐI KHÔNG thêm từ giật tít rẻ tiền như: Cực sốc, Cận cảnh, Khám phá ngay, Bất ngờ, Xem ngay.\n"
                    f"4. TUYỆT ĐỐI KHÔNG thêm Phần X vào nếu trong tiêu đề không có.\n"
                    f"5. QUAN TRỌNG: Độ dài BẮT BUỘC dưới 85 ký tự (khoảng 10-15 từ) chuẩn SEO YouTube và Facebook.\n"
                    f"Chỉ trả về đúng 1 câu tiêu đề duy nhất, không giải thích, không để trong ngoặc kép.\n"
                    f"Tiêu đề gốc: '{clean_body}'"
                )
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=12)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        res_text = raw_text.strip().replace('"', '').replace("'", "")
                        _, res_clean = AIRewriter.extract_part_and_clean(res_text)
                        if res_clean:
                            rewritten_body = res_clean
                            LogManager.log(f"Gemini AI đã viết lại tiêu đề: '{rewritten_body}'", "INFO", "AI")
            except Exception as e:
                LogManager.log(f"Lỗi gọi Gemini API (chuyển sang bộ biến tấu từ vựng): {e}", "WARNING", "AI")

        # Bước 3: Thử dùng OpenAI nếu có cấu hình key và Gemini chưa xử lý
        if not rewritten_body and openai_key and openai_key.strip():
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key.strip())
                completion = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": "Bạn là biên tập viên review phim. Viết lại tiêu đề bằng từ đồng nghĩa mới mẻ, giữ nguyên cốt truyện, không giật tít rác, không thêm Phần X. Dưới 85 ký tự."
                        },
                        {"role": "user", "content": f"Viết lại tiêu đề: '{clean_body}'"}
                    ],
                    max_tokens=80
                )
                res_text = completion.choices[0].message.content.strip().replace('"', '')
                _, res_clean = AIRewriter.extract_part_and_clean(res_text)
                if res_clean:
                    rewritten_body = res_clean
                    LogManager.log(f"OpenAI đã viết lại tiêu đề: '{rewritten_body}'", "INFO", "AI")
            except Exception as e:
                LogManager.log(f"Lỗi gọi OpenAI API (chuyển sang bộ biến tấu từ vựng): {e}", "WARNING", "AI")

        # Bước 4: Nếu không có API Key hoặc API lỗi, kích hoạt bộ Smart Paraphraser nội bộ
        if not rewritten_body:
            rewritten_body = AIRewriter.paraphrase_text(clean_body)
            # Nếu tiêu đề vẫn chưa thay đổi (không khớp từ điển) và độ dài hợp lý, thêm hậu tố nhận diện
            if rewritten_body == clean_body and len(rewritten_body) <= 75:
                rewritten_body = f"{rewritten_body} | Bản Đẹp Trọn Bộ"
            LogManager.log(f"Smart Paraphraser đã biến tấu tiêu đề: '{rewritten_body}'", "INFO", "AI")

        # Bước 5: Ghép phần phim (Phần X) lên đầu nếu nguồn có phần
        if part_num:
            final_title = f"Phần {part_num} - {rewritten_body}"
        else:
            final_title = rewritten_body

        # Giới hạn độ dài an toàn tối đa 95 ký tự để không bị cắt trên YouTube/Facebook
        if len(final_title) > 95:
            final_title = final_title[:95].rsplit(' ', 1)[0]

        return final_title.strip()

    @staticmethod
    def get_recommended_tags(title: str) -> List[str]:
        """
        Tạo danh sách 20-30 thẻ tags chuẩn SEO YouTube:
        - Tags cốt lõi có lượt tìm kiếm cao nhất (high search volume).
        - Tags theo thể loại được bóc tách tự động từ tiêu đề (xuyên không, tổng tài, trọng sinh, cổ trang...).
        - Giới hạn tổng ký tự dưới 450 (YouTube cho phép tối đa 500 ký tự).
        """
        title_lower = title.lower()
        tags = [
            "review phim",
            "review phim hay",
            "tóm tắt phim",
            "phim ngắn trung quốc",
            "phim trung quốc",
            "phim hay 2026",
            "phim mới",
            "phim thuyết minh",
            "phim full bộ",
            "review phim ngắn",
            "phim trung quốc mới nhất",
            "phim hay mỗi ngày",
            "tóm tắt phim hay",
            "mọt phim",
            "phim ngắn hay",
            "phim trọn bộ"
        ]

        # Bổ sung tags theo chủ đề / từ khóa phát hiện trong tiêu đề
        if any(k in title_lower for k in ["xuyên", "xuyên không"]):
            tags.extend(["phim xuyên không", "xuyên không", "xuyên không cổ đại"])
        if any(k in title_lower for k in ["trọng sinh", "sống lại", "đời trước", "kiếp trước"]):
            tags.extend(["phim trọng sinh", "trọng sinh", "trọng sinh báo thù"])
        if any(k in title_lower for k in ["tổng tài", "chủ tịch", "giả nghèo", "tập đoàn"]):
            tags.extend(["phim tổng tài", "tổng tài", "chủ tịch giả nghèo", "tổng tài bá đạo"])
        if any(k in title_lower for k in ["phu nhân", "tiểu thư", "hào môn", "thiếu gia"]):
            tags.extend(["hào môn thế gia", "phim hào môn", "phu nhân"])
        if any(k in title_lower for k in ["gia đình", "mẹ", "cha", "con gái", "con trai", "nhà", "nhà nghèo"]):
            tags.extend(["phim gia đình", "tâm lý tình cảm", "phim cảm động"])
        if any(k in title_lower for k in ["báo thù", "trả thù", "đòi lại", "tính sổ"]):
            tags.extend(["phim báo thù", "báo thù cực cuốn"])
        if any(k in title_lower for k in ["cổ đại", "hoàng cung", "nương nương", "vương gia", "hoàng đế"]):
            tags.extend(["phim cổ trang", "cổ trang trung quốc"])

        # Lọc unique duy trì thứ tự
        seen = set()
        unique_tags = []
        for tag in tags:
            tag_clean = tag.strip().lower()
            if tag_clean and tag_clean not in seen:
                seen.add(tag_clean)
                unique_tags.append(tag.strip())

        # Kiểm tra tổng độ dài ký tự < 450
        final_tags = []
        current_len = 0
        for tag in unique_tags:
            if current_len + len(tag) + 1 > 450 or len(final_tags) >= 30:
                break
            final_tags.append(tag)
            current_len += len(tag) + 1

        return final_tags

    @staticmethod
    def generate_seo_description(
        title: str,
        orig_title: str = "",
        video_id: str = "",
        gemini_key: Optional[str] = None,
        openai_key: Optional[str] = None
    ) -> str:
        """
        Tạo mô tả video chuẩn SEO YouTube thuật toán đề xuất:
        1. Tiêu đề nổi bật + Hook thu hút.
        2. Tóm tắt cốt truyện lôi cuốn (AI Gemini / template dự phòng).
        3. Lời kêu gọi hành động (Call To Action: Like, Subscribe, Comment).
        4. Cụm từ khóa tìm kiếm (Search Keywords) & Hashtags thịnh hành.
        5. RefID để theo dõi chống trùng lặp.
        """
        synopsis = ""
        # Thử sinh tóm tắt bằng Gemini nếu có key
        if gemini_key and gemini_key.strip():
            try:
                import requests
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là biên tập viên review phim ngắn.\n"
                    f"Dựa vào tiêu đề phim: '{title}', hãy viết đúng 2-3 câu tóm tắt cốt truyện mở đầu thật kịch tính, lôi cuốn và tạo tò mò cho khán giả.\n"
                    f"Yêu cầu: Không spoilers kết thúc, văn phong tự nhiên lôi cuốn, dưới 60 từ. Chỉ trả về đoạn văn tóm tắt, không giải thích."
                )
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if raw_text.strip():
                            synopsis = raw_text.strip().replace('"', '')
            except Exception as e:
                LogManager.log(f"Lỗi tạo tóm tắt qua Gemini: {e}", "WARNING", "AI")

        if not synopsis:
            synopsis = (
                "Một câu chuyện đầy bất ngờ và kịch tính với những tình tiết hấp dẫn không thể rời mắt. "
                "Liệu số phận của các nhân vật sẽ đi về đâu khi những bí mật dần được hé lộ? "
                "Cùng theo dõi trọn vẹn diễn biến bộ phim ngay sau đây!"
            )

        ref_line = f"\n\n[RefID: {video_id}]" if video_id else ""

        desc = (
            f"🎬 {title}\n\n"
            f"📖 NỘI DUNG PHIM:\n"
            f"{synopsis}\n\n"
            f"🔔 ĐĂNG KÝ KÊNH ỦNG HỘ:\n"
            f"👉 Nhấn Like & Đăng Ký Kênh để không bỏ lỡ những bộ phim mới và hay nhất mỗi ngày!\n"
            f"👉 Đừng quên để lại cảm nghĩ của bạn dưới phần bình luận nhé!\n\n"
            f"📌 TỪ KHÓA TÌM KIẾM:\n"
            f"review phim, tóm tắt phim, phim ngắn trung quốc, phim trung quốc mới nhất, "
            f"phim thuyết minh, phim hay 2026, phim ngắn chọn lọc, phim full bộ\n\n"
            f"#reviewphim #phimhay #phimngantrungquoc #tomtatphim #phimmoi #phimthuyetminh #xuhuong"
            f"{ref_line}"
        )
        return desc
