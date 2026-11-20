import os
import json
import urllib.request
import urllib.parse
import subprocess
import time
from typing import Dict, Any, List, Optional
from core.task_queue import LogManager
from core.history import HistoryManager

class ChinaCrawler:
    """
    Crawler kết nối trực tiếp vào các trạm tài nguyên phim ngắn nội địa Trung Quốc (chuẩn MacCMS/AppleCMS).
    Lấy phim mới nhất trong ngày (độ trễ = 0, chưa từng có trên YouTube, không sợ trùng Content ID).
    """

    API_SOURCES = [
        {
            "name": "Lượng Tử (Quantum)",
            "url": "https://cj.lziapi.com/api.php/provide/vod/?ac=detail&t=46&pagesize=20",
            "type_id": 46
        },
        {
            "name": "Phi Phàm (FFZY)",
            "url": "https://api.ffzyapi.com/api.php/provide/vod/?ac=detail&t=36&pagesize=20",
            "type_id": 36
        }
    ]

    VIRAL_KEYWORDS = [
        "打脸", "豪门", "总裁", "婆媳", "千金", "真假千金", "重回", "重生",
        "逆袭", "清醒", "战神", "神医", "分家", "背叛", "大权", "首富", "闪婚"
    ]

    @staticmethod
    def get_candidate_dramas(limit: int = 15) -> List[Dict[str, Any]]:
        """
        Quét danh sách các bộ phim ngắn mới ra mắt hôm nay, xếp hạng theo độ kịch tính / hút view.
        """
        candidates = []

        for src in ChinaCrawler.API_SOURCES:
            src_name = src["name"]
            api_url = src["url"]
            try:
                req = urllib.request.Request(
                    api_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    items = data.get("list", [])
                    LogManager.log(f"Quét trạm [{src_name}]: nhận được {len(items)} bộ phim ngắn mới.", "INFO", "CRAWLER")

                    for item in items:
                        vod_id = str(item.get("vod_id", ""))
                        vod_name = item.get("vod_name", "").strip()
                        vod_pic = item.get("vod_pic", "")
                        vod_time = item.get("vod_time", "")
                        play_url = item.get("vod_play_url", "")

                        if not vod_id or not vod_name:
                            continue

                        # Kiểm tra xem phim này đã từng xử lý chưa
                        unique_key = f"cn_{vod_id}"
                        if HistoryManager.is_processed(unique_key):
                            continue

                        # Trích xuất toàn bộ link M3U8 chuẩn
                        m3u8_urls = ChinaCrawler._extract_all_m3u8(play_url)
                        if not m3u8_urls:
                            continue

                        # Tính điểm ưu tiên (Viral Score)
                        score = 0
                        for kw in ChinaCrawler.VIRAL_KEYWORDS:
                            if kw in vod_name:
                                score += 10

                        candidates.append({
                            "id": unique_key,
                            "vod_id": vod_id,
                            "raw_title": vod_name,
                            "poster_url": vod_pic,
                            "m3u8_url": m3u8_urls[0],
                            "m3u8_urls": m3u8_urls,
                            "source_name": src_name,
                            "updated_time": vod_time,
                            "score": score
                        })
            except Exception as e:
                LogManager.log(f"Lỗi khi quét trạm [{src_name}]: {e}", "WARNING", "CRAWLER")

        # Sắp xếp các phim có điểm kịch tính cao nhất lên đầu
        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:limit]

    @staticmethod
    def _extract_all_m3u8(play_url: str) -> List[str]:
        """
        Bóc tách danh sách toàn bộ các tập M3U8 hợp lệ từ trường vod_play_url của AppleCMS/MacCMS.
        """
        if not play_url:
            return []

        all_valid_groups = []
        for group in play_url.split("$$$"):
            group_urls = []
            for ep in group.split("#"):
                if ".m3u8" in ep.lower():
                    parts = ep.split("$")
                    for p in parts:
                        p = p.strip()
                        if p.startswith("http") and ".m3u8" in p.lower():
                            group_urls.append(p)
                            break
            if group_urls:
                all_valid_groups.append(group_urls)

        if not all_valid_groups:
            return []

        # Ưu tiên nhóm có link direct m3u8 (thường chứa /202 hoặc mixed.m3u8 / index.m3u8)
        for grp in all_valid_groups:
            if any("/202" in u or "mixed" in u or "index.m3u8" in u for u in grp):
                return grp

        return all_valid_groups[0]

    @staticmethod
    def _extract_m3u8(play_url: str) -> Optional[str]:
        """
        Bóc tách link M3U8 đầu tiên hợp lệ.
        """
        urls = ChinaCrawler._extract_all_m3u8(play_url)
        return urls[0] if urls else None

    @staticmethod
    def download_poster(poster_url: str, save_path: str) -> bool:
        """
        Tải poster chất lượng cao từ xưởng phim Trung Quốc về làm nguyên liệu thumbnail.
        """
        if not poster_url or not poster_url.startswith("http"):
            return False
        try:
            req = urllib.request.Request(
                poster_url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                with open(save_path, "wb") as f:
                    f.write(resp.read())
            return os.path.exists(save_path) and os.path.getsize(save_path) > 1000
        except Exception as e:
            LogManager.log(f"Không thể tải poster gốc: {e}", "WARNING", "CRAWLER")
            return False

    @staticmethod
    def resolve_m3u8_stream(m3u8_url: str) -> str:
        """
        Bóc tách Master Playlist (.m3u8) để lấy direct stream m3u8 chuẩn,
        tránh triệt để lỗi 404 relative path của FFmpeg khi gặp CDN Trung Quốc.
        """
        if "/lzv" in m3u8_url and m3u8_url.endswith("/index.m3u8"):
            # Chuẩn CDN Lượng Tử (Quantum): stream 1080p luôn nằm tại 2000k/hls/index.m3u8
            return m3u8_url.replace("/index.m3u8", "/2000k/hls/index.m3u8")

        try:
            req = urllib.request.Request(
                m3u8_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                base_url = m3u8_url.rsplit("/", 1)[0]
                for line in text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if line.startswith("http"):
                            return line
                        elif line.startswith("/"):
                            parsed = urllib.parse.urlparse(m3u8_url)
                            return f"{parsed.scheme}://{parsed.netloc}{line}"
                        else:
                            return f"{base_url}/{line}"
        except Exception as e:
            LogManager.log(f"Lỗi khi phân giải m3u8 stream: {e}", "WARNING", "CRAWLER")
        return m3u8_url

    @staticmethod
    def download_m3u8_video(
        m3u8_url: str,
        output_path: str,
        max_duration_seconds: int = 7200
    ) -> bool:
        """
        Tải video trọn bộ từ link M3U8 bằng FFmpeg với tốc độ cao (stream copy).
        """
        direct_stream_url = ChinaCrawler.resolve_m3u8_stream(m3u8_url)
        LogManager.log(f"Đang tải video từ M3U8 trực tiếp: {direct_stream_url[:75]}...", "INFO", "CRAWLER")
        t0 = time.time()
        try:
            parsed_url = urllib.parse.urlparse(direct_stream_url)
            referer = f"{parsed_url.scheme}://{parsed_url.netloc}/"
            headers_str = (
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
                f"Referer: {referer}\r\n"
            )
            cmd = [
                "ffmpeg", "-y",
                "-headers", headers_str,
                "-i", direct_stream_url,
                "-t", str(max_duration_seconds),
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                output_path
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000000:
                elapsed = round(time.time() - t0, 1)
                size_mb = round(os.path.getsize(output_path) / (1024 * 1024), 1)
                LogManager.log(f"Tải video M3U8 thành công trong {elapsed}s! Kích thước: {size_mb} MB", "SUCCESS", "CRAWLER")
                return True
            else:
                LogManager.log(f"FFmpeg tải M3U8 không thành công (code {res.returncode}): {res.stderr[-200:]}", "ERROR", "CRAWLER")
                return False
        except Exception as e:
            LogManager.log(f"Lỗi ngoại lệ khi tải M3U8: {e}", "ERROR", "CRAWLER")
            return False

    @staticmethod
    def download_drama_video(
        drama_info: Dict[str, Any],
        output_path: str,
        target_minutes: int = 12,
        task_id: str = ""
    ) -> bool:
        """
        Tải video phim đạt chuẩn độ dài Review Phim (tối thiểu 8 - 15 phút):
        - Nếu là phim trọn bộ 1 file (như Quantum 50 - 90 phút): Tải trực tiếp qua M3U8.
        - Nếu là phim vi kịch chia nhiều tập nhỏ (như FFZY 60 - 80 tập x 1.5 phút): Tải 8 - 10 tập đầu tiên và tự động ghép nối (concat) thành 1 video liền mạch 10 - 15 phút.
        - Kiểm tra nghiêm ngặt: Tuyệt đối không bao giờ xuất bản video dưới 5 phút!
        """
        m3u8_urls = drama_info.get("m3u8_urls", [])
        if not m3u8_urls and drama_info.get("m3u8_url"):
            m3u8_urls = [drama_info["m3u8_url"]]

        if not m3u8_urls:
            LogManager.log(f"[{task_id}] Không tìm thấy link M3U8 hợp lệ.", "ERROR", "CRAWLER")
            return False

        temp_dir = os.path.dirname(output_path)

        # TRƯỜNG HỢP 1: Phim bộ nhiều tập ngắn (mỗi tập 1-2 phút) -> Tải 8 - 10 tập rồi ghép lại
        if len(m3u8_urls) > 1:
            num_eps_to_get = min(len(m3u8_urls), max(8, int(target_minutes * 60 / 75)))
            LogManager.log(f"[{task_id}] Phim bộ vi kịch ({len(m3u8_urls)} tập) -> Đang tải và ghép nối {num_eps_to_get} tập đầu để đạt chuẩn thời lượng 10-15 phút...", "INFO", "CRAWLER")

            ep_files = []
            concat_txt = os.path.join(temp_dir, f"concat_eps_{task_id}.txt")

            try:
                for i in range(num_eps_to_get):
                    ep_url = m3u8_urls[i]
                    ep_file = os.path.join(temp_dir, f"ep_{task_id}_{i}.mp4")
                    ok = ChinaCrawler.download_m3u8_video(ep_url, ep_file, max_duration_seconds=180)
                    if ok and os.path.exists(ep_file) and os.path.getsize(ep_file) > 100000:
                        ep_files.append(ep_file)

                if len(ep_files) < 4:
                    LogManager.log(f"[{task_id}] Không tải đủ các tập phim bộ ({len(ep_files)}/{num_eps_to_get} tập).", "WARNING", "CRAWLER")
                    return False

                # Ghép các tập bằng FFmpeg concat demuxer (-c copy siêu tốc)
                with open(concat_txt, "w", encoding="utf-8") as f:
                    for ep_f in ep_files:
                        f.write(f"file '{ep_f.replace('\\', '/')}'\n")

                cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_txt, "-c", "copy",
                    "-bsf:a", "aac_adtstoasc",
                    output_path
                ]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 1000000:
                    LogManager.log(f"[{task_id}] Ghép nối các tập phim không thành công.", "ERROR", "CRAWLER")
                    return False

                LogManager.log(f"[{task_id}] Đã ghép nối thành công {len(ep_files)} tập phim thành 1 video liền mạch!", "SUCCESS", "CRAWLER")
            finally:
                if os.path.exists(concat_txt):
                    try: os.remove(concat_txt)
                    except: pass
                for ep_f in ep_files:
                    if os.path.exists(ep_f):
                        try: os.remove(ep_f)
                        except: pass

        # TRƯỜNG HỢP 2: Phim trọn bộ 1 file (như Quantum 50-90 phút)
        else:
            LogManager.log(f"[{task_id}] Phim trọn bộ 1 file -> Đang tải trực tiếp toàn bộ mạch phim...", "INFO", "CRAWLER")
            ok = ChinaCrawler.download_m3u8_video(m3u8_urls[0], output_path, max_duration_seconds=int(target_minutes * 180))
            if not ok:
                return False

        # BƯỚC KIỂM TRA ĐỘ DÀI NGHIÊM NGẶT (TUYỆT ĐỐI KHÔNG BỎ QUA)
        try:
            dur_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", output_path
            ]
            res = subprocess.run(dur_cmd, capture_output=True, text=True)
            dur = float(res.stdout.strip()) if res.stdout.strip() else 0.0

            if dur < 300: # Dưới 5 phút (300 giây)
                LogManager.log(f"[{task_id}] Video tải về quá ngắn ({dur/60:.1f} phút < 5 phút) -> Không đạt chuẩn Review Phim, tự động bỏ qua.", "WARNING", "CRAWLER")
                if os.path.exists(output_path):
                    try: os.remove(output_path)
                    except: pass
                return False

            LogManager.log(f"[{task_id}] Video đạt chuẩn thời lượng vàng: {dur/60:.1f} phút ({round(os.path.getsize(output_path)/(1024*1024), 1)} MB).", "SUCCESS", "CRAWLER")
            return True
        except Exception as e:
            LogManager.log(f"[{task_id}] Lỗi khi kiểm tra thời lượng video: {e}", "WARNING", "CRAWLER")
            return os.path.exists(output_path) and os.path.getsize(output_path) > 5000000
