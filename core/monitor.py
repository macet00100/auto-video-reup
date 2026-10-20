import re
import json
import urllib.request
import feedparser
from typing import Dict, Any, List
from core.config import ConfigManager
from core.task_queue import TaskQueue, LogManager

class ChannelMonitor:
    @staticmethod
    def get_channel_latest_videos(channel_id: str, cfg: Dict[str, Any] = None, max_results: int = 5) -> List[Dict[str, str]]:
        if cfg is None:
            cfg = ConfigManager.load()
        # 1. Thử YouTube Data API v3 (Chuẩn nhất, 100% không bao giờ 404)
        try:
            from core.uploader_yt import YouTubeUploader
            yt_dest = cfg.get("youtube", {}).get("destination", {})
            token = YouTubeUploader.get_valid_access_token(yt_dest)
            uploads_id = "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id
            url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=snippet,contentDetails&playlistId={uploads_id}&maxResults={max_results}"
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                items = data.get("items", [])
                if items:
                    vids = []
                    for it in items:
                        v_id = it.get("contentDetails", {}).get("videoId")
                        if v_id:
                            vids.append({
                                "id": v_id,
                                "title": it.get("snippet", {}).get("title", ""),
                                "url": f"https://www.youtube.com/watch?v={v_id}"
                            })
                    if vids:
                        return vids
        except Exception as e:
            LogManager.log(f"YouTube Data API không lấy được video kênh {channel_id}: {e}. Đang chuyển sang tầng dự phòng yt-dlp.", "WARNING", "SCANNER")

        # 2. Thử yt-dlp flat-playlist (không bao giờ 404)
        try:
            import yt_dlp
            ydl_opts = {"extract_flat": True, "quiet": True, "playlistend": max_results}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(f"https://www.youtube.com/channel/{channel_id}/videos", download=False)
                entries = res.get("entries", [])
                if entries:
                    vids = []
                    for e in entries:
                        v_id = e.get("id")
                        if v_id:
                            vids.append({
                                "id": v_id,
                                "title": e.get("title", ""),
                                "url": f"https://www.youtube.com/watch?v={v_id}"
                            })
                    if vids:
                        return vids
        except Exception as e:
            LogManager.log(f"yt-dlp flat-playlist lỗi: {e}. Đang chuyển sang RSS.", "WARNING", "SCANNER")

        # 3. Thử RSS
        try:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            feed = feedparser.parse(rss_url)
            vids = []
            for entry in feed.entries[:max_results]:
                v_id = getattr(entry, "yt_videoid", None)
                if not v_id:
                    m = re.search(r"v=([a-zA-Z0-9_-]+)", getattr(entry, "link", ""))
                    if m: v_id = m.group(1)
                if v_id:
                    vids.append({
                        "id": v_id,
                        "title": getattr(entry, "title", ""),
                        "url": getattr(entry, "link", f"https://www.youtube.com/watch?v={v_id}")
                    })
            return vids
        except Exception:
            pass

        return []
    @staticmethod
    def extract_youtube_channel_id(url_or_id: str) -> str:
        url_or_id = url_or_id.strip()
        if url_or_id.startswith("UC") and len(url_or_id) == 24:
            return url_or_id
        
        # Check standard channel URL: youtube.com/channel/UC...
        m = re.search(r"youtube\.com/channel/(UC[\w-]{22})", url_or_id)
        if m:
            return m.group(1)

        # Hỗ trợ tự phân giải link @handle (ví dụ @tayvuongmaureview)
        if "@" in url_or_id:
            try:
                import yt_dlp
                with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    info = ydl.extract_info(url_or_id, download=False)
                    ch_id = info.get('channel_id') or info.get('id')
                    if ch_id and ch_id.startswith('UC'):
                        return ch_id
            except Exception:
                pass

        return url_or_id

    @staticmethod
    def scan_youtube_sources() -> int:
        cfg = ConfigManager.load()
        yt_cfg = cfg.get("youtube", {})
        if not yt_cfg.get("enabled", True):
            return 0

        sources = yt_cfg.get("sources", [])
        new_videos_found = 0
        task_queue = TaskQueue()

        for s in sources:
            if not s.get("enabled", True):
                continue

            channel_id = ChannelMonitor.extract_youtube_channel_id(s.get("id") or s.get("url", ""))
            name = s.get("name", channel_id)
            last_seen = s.get("last_video_id", "")

            try:
                videos = ChannelMonitor.get_channel_latest_videos(channel_id, cfg, max_results=5)
                for vid in videos:
                    video_id = vid["id"]
                    if video_id and video_id != last_seen:
                        video_title = vid["title"]
                        video_url = vid["url"]
                        
                        LogManager.log(
                            f"Phát hiện video mới từ kênh [{name}]: '{video_title}' (ID: {video_id})",
                            "INFO", "YOUTUBE"
                        )

                        # Đưa vào hàng đợi
                        task_queue.add_task(
                            platform="youtube",
                            source_url=video_url,
                            video_title=video_title,
                            metadata={"source_name": name, "video_id": video_id}
                        )

                        # Cập nhật ID video mới nhất để tránh lặp
                        ConfigManager.update_source_last_video("youtube", s.get("id"), video_id)
                        new_videos_found += 1
                        break

            except Exception as e:
                LogManager.log(f"Lỗi khi quét YouTube kênh {name}: {str(e)}", "WARNING", "YOUTUBE")

        return new_videos_found

    @staticmethod
    def scan_facebook_sources() -> int:
        cfg = ConfigManager.load()
        fb_cfg = cfg.get("facebook", {})
        if not fb_cfg.get("enabled", True):
            return 0

        sources = fb_cfg.get("sources", [])
        new_videos_found = 0
        task_queue = TaskQueue()

        for s in sources:
            if not s.get("enabled", True):
                continue
            
            raw_url = s.get("url", "").strip()
            raw_id = s.get("id", "").strip()
            name = s.get("name", "Nguồn Facebook")
            last_seen = s.get("last_video_id", "")

            channel_id = ChannelMonitor.extract_youtube_channel_id(raw_id or raw_url)

            # Trường hợp 1: Nguồn là Kênh YouTube
            if channel_id.startswith("UC") or "youtube.com" in raw_url or "youtu.be" in raw_url:
                try:
                    videos = ChannelMonitor.get_channel_latest_videos(channel_id, cfg, max_results=5)
                    for vid in videos:
                        video_id = vid["id"]
                        if video_id and video_id != last_seen:
                            video_title = vid["title"]
                            video_url = vid["url"]
                            
                            LogManager.log(
                                f"Phát hiện video mới cho Facebook từ [{name}]: '{video_title}' (ID: {video_id})",
                                "INFO", "FACEBOOK"
                            )

                            task_queue.add_task(
                                platform="facebook",
                                source_url=video_url,
                                video_title=video_title,
                                metadata={"source_name": name, "video_id": video_id}
                            )

                            ConfigManager.update_source_last_video("facebook", s.get("id"), video_id)
                            new_videos_found += 1
                            break

                except Exception as e:
                    LogManager.log(f"Lỗi khi quét cho Facebook kênh {name}: {str(e)}", "WARNING", "FACEBOOK")

            # Trường hợp 2: Nguồn là Link video/reel trực tiếp
            elif raw_url and raw_url != last_seen:
                task_queue.add_task(
                    platform="facebook",
                    source_url=raw_url,
                    video_title=f"Video từ {name}",
                    metadata={"source_name": name}
                )
                ConfigManager.update_source_last_video("facebook", s.get("id"), raw_url)
                new_videos_found += 1

        return new_videos_found

    @staticmethod
    def scan_all() -> Dict[str, int]:
        LogManager.log("Bắt đầu chu kỳ quét tự động các kênh nguồn...", "INFO", "MONITOR")
        yt_count = ChannelMonitor.scan_youtube_sources()
        fb_count = ChannelMonitor.scan_facebook_sources()
        LogManager.log(f"Hoàn thành quét: Tìm thấy {yt_count} video YouTube mới, {fb_count} video Facebook mới.", "INFO", "MONITOR")
        return {"youtube": yt_count, "facebook": fb_count}
