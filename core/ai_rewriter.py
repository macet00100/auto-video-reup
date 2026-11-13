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
    def is_multi_part_video(title: str) -> Tuple[bool, Optional[str]]:
        """
        Kiểm tra xem video có phải là video chia phần / nhiều tập không.
        Ví dụ: P1, P2, Phần 1, Tập 2, Part 3, Ep 4, Tập Cuối, Hồi 1...
        (Cẩn thận không khớp nhầm 'Tập đoàn', 'Phần lớn', 'Phim'...).
        Trả về (True, 'P1') hoặc (False, None).
        """
        pat = r'(?:^|[\s\(\[\|_\-])(?:P|Phần|Tập|Part|Ep|Episode|Hồi)\.?\s*(\d+|cuối|đầu)(?:$|[\s\)\]\|:\.\-_])'
        m = re.search(pat, title, flags=re.IGNORECASE)
        if m:
            return True, m.group(0).strip()
        return False, None

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

        # Phát hiện phần phim: P3, P4, P5, P.3, P 3, Phần 3, Tập 3, Part 3, (P4), [P4]...
        part_num = None
        m = re.search(r'[\(\[]?\s*(?:P|Phần|Tập|Part)\.?\s*(\d+)\s*[\)\]]?', t, flags=re.IGNORECASE)
        if m:
            part_num = m.group(1)
            t = re.sub(r'[\(\[]?\s*(?:P|Phần|Tập|Part)\.?\s*' + part_num + r'\s*[\)\]]?[\s:\-\.]*', '', t, flags=re.IGNORECASE).strip()

        # Dọn sạch các cặp ngoặc rỗng nếu còn sót
        t = re.sub(r'[\(\[]\s*[\)\]]', '', t).strip()

        # Làm sạch ký tự phân cách ở đầu và đuôi
        t = re.sub(r'^[\s:\-\.\,\|\[\]\(\)]+', '', t).strip()
        t = re.sub(r'[\s:\-\.\,\|\[\]\(\)]+$', '', t).strip()

        return part_num, t

    @staticmethod
    def clean_and_format_title(raw_title: str) -> str:
        """
        Làm sạch và quy chuẩn hóa tên phim: đưa Phần X hoặc 'Full Trọn Bộ | ' lên đầu và bỏ từ rác.
        """
        part_num, clean_body = AIRewriter.extract_part_and_clean(raw_title)
        clean_body = re.sub(r'^(?:full\s+trọn\s+bộ|trọn\s+bộ|bản\s+full|full)\s*[\:\|\-]?\s*', '', clean_body, flags=re.IGNORECASE).strip()
        if part_num:
            return f"Phần {part_num} - {clean_body}".strip()
        return f"Full Trọn Bộ | {clean_body}".strip()

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
        # Bỏ các tiền tố full / trọn bộ có sẵn để tránh bị lặp lại
        clean_body = re.sub(r'^(?:full\s+trọn\s+bộ|trọn\s+bộ|bản\s+full|full)\s*[\:\|\-]?\s*', '', clean_body, flags=re.IGNORECASE).strip()

        rewritten_body = None

        # Bước 2: Thử dùng Google Gemini nếu có cấu hình key
        if gemini_key and gemini_key.strip():
            try:
                import requests
                # Sử dụng API REST với model gemini-flash-lite-latest phản hồi siêu nhanh và ổn định
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là chuyên gia giật tít triệu view review phim trên YouTube & Facebook.\n"
                    f"Nhiệm vụ: Viết lại tiêu đề phim sau theo CÔNG THỨC 3 VẾ GÂY TÒ MÒ ĐỈNH CAO:\n"
                    f"Cấu trúc: [Hoàn cảnh éo le / Bị sỉ nhục, khinh thường] + [Biến cố bất ngờ / Thân phận bí mật lộ diện] + [Cái kết hả hê / Vả mặt cực gắt]\n"
                    f"Ví dụ mẫu: 'Bị Mẹ Chồng Ép Ăn Cơm Thừa Ngay Ngày Cưới, Nào Ngờ Cô Là Chị Đại Giang Hồ Khiến Cả Nhà Quỳ Lạy'\n"
                    f"Quy tắc sống còn:\n"
                    f"1. Đưa tình huống kích thích tò mò và kịch tính nhất lên 45 ký tự đầu tiên để tối ưu cho người xem điện thoại.\n"
                    f"2. Dùng các động từ mạnh, giàu cảm xúc: ép, đuổi, tát, quỳ lạy, vả mặt, san bằng, trả đũa, trắng tay, hối hận.\n"
                    f"3. TUYỆT ĐỐI KHÔNG thêm từ giật tít rẻ tiền như: Cực sốc, Cận cảnh, Khám phá ngay, Bất ngờ, Xem ngay.\n"
                    f"4. TUYỆT ĐỐI KHÔNG thêm Phần X vào nếu trong tiêu đề không có.\n"
                    f"5. Độ dài chuẩn mực: 65 đến 95 ký tự (chuẩn SEO YouTube và Facebook Reels).\n"
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

        # Bước 5: Ghép tiền tố "Full Trọn Bộ | " (nếu không chia phần) hoặc "Phần X -" (nếu có phần)
        if part_num:
            final_title = f"Phần {part_num} - {rewritten_body}"
        else:
            final_title = f"Full Trọn Bộ | {rewritten_body}"

        # Giới hạn độ dài an toàn tối đa 100 ký tự (chuẩn SEO YouTube và Facebook)
        if len(final_title) > 100:
            final_title = final_title[:100].rsplit(' ', 1)[0]

        return final_title.strip()

    @staticmethod
    def generate_shorts_titles(
        base_title: str,
        gemini_key: Optional[str] = None,
        openai_key: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Sử dụng AI tạo 2 tiêu đề Short/Reel giật gân, độc lập, không dùng tiền tố máy móc như [Cao Trào 1].
        - Short 1: Nửa đầu phim - xung đột bùng nổ / éo le / uất ức.
        - Short 2: Nửa sau phim - vả mặt đỉnh cao / lật kèo hả hê.
        """
        clean_base = re.sub(r'^(?:\[.*?\]\s*)?(?:full\s+trọn\s+bộ|trọn\s+bộ|bản\s+full|full)\s*[\:\|\-]?\s*', '', base_title, flags=re.IGNORECASE).strip()
        clean_base = re.sub(r'^(?:\[\s*(?:tập|phần|p)\.?\s*\d+\s*\]|(?:tập|phần|p)\.?\s*\d+[\s:\-\|])\s*', '', clean_base, flags=re.IGNORECASE).strip()

        title_1 = None
        title_2 = None

        if gemini_key and gemini_key.strip():
            try:
                import requests
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={gemini_key.strip()}"
                prompt = (
                    f"Bạn là chuyên gia biên tập video ngắn (YouTube Shorts & Facebook Reels) triệu view review phim vi kịch Trung Quốc.\n"
                    f"Nhiệm vụ: Tạo đúng 2 TIÊU ĐỀ VIDEO NGẮN GIẬT GÂN RIÊNG BIỆT từ nội dung bộ phim: '{clean_base}'\n\n"
                    f"1. Tiêu đề Short 1 (Cắt từ nửa đầu phim - Xung đột / Uất ức / Biến cố éo le khởi đầu): Tít kích thích tò mò về sự bất công hoặc biến cố.\n"
                    f"2. Tiêu đề Short 2 (Cắt từ nửa sau phim - Cao trào / Vả mặt cực gắt / Cái kết hả hê): Tít kích thích cảm giác thỏa mãn, lật mặt kẻ ác.\n\n"
                    f"Quy tắc sống còn:\n"
                    f"- TUYỆT ĐỐI KHÔNG dùng từ: 'Cao trào', 'Short', 'Tập', 'Phần', 'Full Trọn Bộ', 'Tập 1', 'Tập 2'.\n"
                    f"- Viết tự nhiên như biên tập viên triệu view, dùng từ ngữ giật gân, cuốn hút, kích thích click.\n"
                    f"- Độ dài mỗi tiêu đề: 45 đến 85 ký tự (chuẩn điện thoại).\n"
                    f"- Trả về chính xác 2 dòng:\n"
                    f"Dòng 1: [Tiêu đề Short 1]\n"
                    f"Dòng 2: [Tiêu đề Short 2]\n"
                    f"KHÔNG thêm số thứ tự, không gạch đầu dòng, không giải thích gì khác."
                )
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=12)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                        cleaned_lines = []
                        for l in lines:
                            cl = re.sub(r'^(?:dòng\s*\d+\s*[:\-]|short\s*\d+\s*[:\-]|tiêu\s*đề\s*\d+\s*[:\-]|[\d]+[\.\)\-]\s*)', '', l, flags=re.IGNORECASE).strip()
                            cl = cl.replace('"', '').replace("'", "")
                            if cl:
                                cleaned_lines.append(cl)
                        if len(cleaned_lines) >= 2:
                            title_1 = cleaned_lines[0]
                            title_2 = cleaned_lines[1]
                            LogManager.log(f"Gemini AI đã tạo 2 tiêu đề Short tự nhiên:\n  1. {title_1}\n  2. {title_2}", "SUCCESS", "AI")
            except Exception as e:
                LogManager.log(f"Lỗi khi dùng Gemini tạo tiêu đề Shorts: {e}", "WARNING", "AI")

        if not title_1 or not title_2:
            if openai_key and openai_key.strip():
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=openai_key.strip())
                    prompt = (
                        f"Tạo 2 tiêu đề video ngắn Shorts/Reels review phim giật gân từ: '{clean_base}'.\n"
                        f"Dòng 1: Short 1 (nửa đầu phim - xung đột éo le).\n"
                        f"Dòng 2: Short 2 (nửa sau phim - vả mặt hả hê).\n"
                        f"Không ghi số dòng, không ghi Cao trào hay Tập. Mỗi tiêu đề 45-85 ký tự."
                    )
                    completion = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.8,
                        max_tokens=150
                    )
                    raw_text = completion.choices[0].message.content or ""
                    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                    cleaned_lines = []
                    for l in lines:
                        cl = re.sub(r'^(?:dòng\s*\d+\s*[:\-]|short\s*\d+\s*[:\-]|tiêu\s*đề\s*\d+\s*[:\-]|[\d]+[\.\)\-]\s*)', '', l, flags=re.IGNORECASE).strip()
                        cl = cl.replace('"', '').replace("'", "")
                        if cl:
                            cleaned_lines.append(cl)
                    if len(cleaned_lines) >= 2:
                        title_1 = cleaned_lines[0]
                        title_2 = cleaned_lines[1]
                except Exception as e:
                    LogManager.log(f"Lỗi khi dùng OpenAI tạo tiêu đề Shorts: {e}", "WARNING", "AI")

        # Fallback tự nhiên nếu không có AI hoặc lỗi mạng:
        if not title_1:
            title_1 = f"Đoạn Hay Nhất | {clean_base}"
        if not title_2:
            title_2 = f"Cái Kết Cực Hả Hê | {clean_base}"

        # Đảm bảo độ dài an toàn tối đa 90 ký tự
        if len(title_1) > 90:
            title_1 = title_1[:90].rsplit(' ', 1)[0]
        if len(title_2) > 90:
            title_2 = title_2[:90].rsplit(' ', 1)[0]

        return (title_1.strip(), title_2.strip())

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
        if any(k in title_lower for k in ["mẹ chồng", "con dâu", "mẹ kế", "nhà chồng", "bà cụ"]):
            tags.extend(["mẹ chồng nàng dâu", "phim mẹ chồng nàng dâu", "con dâu", "mẹ chồng ác độc", "mẹ kế"])
        if any(k in title_lower for k in ["tiểu tam", "ly hôn", "ngoại tình", "tra nam", "phản bội", "bắt quả tang"]):
            tags.extend(["đánh ghen", "tiểu tam", "trừng trị tiểu tam", "ly hôn", "ngoại tình"])
        if any(k in title_lower for k in ["vả mặt", "dằn mặt", "lộ thân phận", "thân bại danh liệt", "thiên kim"]):
            tags.extend(["vả mặt", "lộ thân phận", "thiên kim tài phiệt", "phim sảng"])
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
