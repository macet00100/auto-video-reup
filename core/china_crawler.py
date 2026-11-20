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

                        # Trích xuất link M3U8 chuẩn
                        m3u8_url = ChinaCrawler._extract_m3u8(play_url)
                        if not m3u8_url:
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
                            "m3u8_url": m3u8_url,
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
    def _extract_m3u8(play_url: str) -> Optional[str]:
        """
        Bóc tách link M3U8 hợp lệ từ trường vod_play_url của AppleCMS.
        """
        if not play_url:
            return None

        for group in play_url.split("$$$"):
            for ep in group.split("#"):
                if ".m3u8" in ep.lower():
                    parts = ep.split("$")
                    for p in parts:
                        p = p.strip()
                        if p.startswith("http") and ".m3u8" in p.lower():
                            return p
        return None

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
        except Exception:
            pass
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
