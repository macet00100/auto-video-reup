import os
import time
import uuid
import threading
import traceback
from typing import Dict, Any, List, Optional
from datetime import datetime

class LogManager:
    _logs: List[Dict[str, Any]] = []
    _max_logs: int = 400
    _lock = threading.Lock()
    _log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "logs", "app.log"))

    @classmethod
    def log(cls, message: str, level: str = "INFO", category: str = "SYSTEM"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "level": level.upper(),
            "category": category.upper(),
            "message": message
        }
        with cls._lock:
            cls._logs.append(entry)
            if len(cls._logs) > cls._max_logs:
                cls._logs.pop(0)

        # Print to console for server stdout safely
        try:
            print(f"[{timestamp}] [{level.upper()}] [{category.upper()}] {message}")
        except Exception:
            try:
                print(f"[{timestamp}] [{level.upper()}] [{category.upper()}] {message.encode('ascii', 'replace').decode('ascii')}")
            except Exception:
                pass

        # Append to file
        try:
            os.makedirs(os.path.dirname(cls._log_file), exist_ok=True)
            with open(cls._log_file, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] [{level.upper()}] [{category.upper()}] {message}\n")
        except Exception:
            pass

    @classmethod
    def get_logs(cls, limit: int = 150) -> List[Dict[str, Any]]:
        # Đọc từ file log để đồng bộ giữa Web UI và các tiến trình chạy ngầm
        if os.path.exists(cls._log_file):
            try:
                with open(cls._log_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    file_logs = []
                    for line in lines[-limit:]:
                        line = line.strip()
                        if not line:
                            continue
                        m = re.match(r"^\[(.*?)\]\s+\[(.*?)\]\s+\[(.*?)\]\s+(.*)$", line)
                        if m:
                            file_logs.append({
                                "timestamp": m.group(1),
                                "level": m.group(2),
                                "category": m.group(3),
                                "message": m.group(4)
                            })
                        else:
                            file_logs.append({
                                "timestamp": "",
                                "level": "INFO",
                                "category": "SYSTEM",
                                "message": line
                            })
                    return list(reversed(file_logs))
            except Exception:
                pass
        with cls._lock:
            return list(reversed(cls._logs[-limit:]))

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._logs.clear()


class TaskQueue:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(TaskQueue, cls).__new__(cls)
                    cls._instance.tasks: Dict[str, Dict[str, Any]] = {}
                    cls._instance.queue: List[str] = []
                    cls._instance.is_running = False
                    cls._instance.worker_thread = None
        return cls._instance

    def add_task(self, platform: str, source_url: str, video_title: str = "", metadata: Dict[str, Any] = None) -> str:
        task_id = str(uuid.uuid4())[:8]
        task_data = {
            "id": task_id,
            "platform": platform,
            "source_url": source_url,
            "original_title": video_title or "Đang quét thông tin...",
            "new_title": "",
            "status": "QUEUED", # QUEUED, DOWNLOADING, PROCESSING, GENERATING_THUMB, UPLOADING, COMPLETED, FAILED
            "progress": 0,
            "stage_info": "Đang xếp hàng chờ xử lý...",
            "thumbnail_url": "",
            "output_video_path": "",
            "created_at": datetime.now().strftime("%H:%M:%S"),
            "completed_at": None,
            "error": None,
            "metadata": metadata or {}
        }
        with self._lock:
            self.tasks[task_id] = task_data
            self.queue.append(task_id)

        LogManager.log(f"Đã thêm nhiệm vụ mới: [{task_id}] {source_url} ({platform.upper()})", "INFO", platform)
        self.ensure_worker_running()
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self.tasks.get(task_id)

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            # Sort by creation time descending
            return list(reversed(list(self.tasks.values())[-limit:]))

    def update_task(self, task_id: str, **kwargs):
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].update(kwargs)

    def ensure_worker_running(self):
        if not self.is_running or self.worker_thread is None or not self.worker_thread.is_alive():
            self.is_running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()

    def _worker_loop(self):
        # Deferred import to prevent circular dependency
        from core.downloader import VideoDownloader
        from core.processor import VideoProcessor
        from core.ai_rewriter import AIRewriter
        from core.thumbnail import ThumbnailGenerator
        from core.uploader_yt import YouTubeUploader
        from core.uploader_fb import FacebookUploader
        from core.config import ConfigManager

        LogManager.log("Worker Queue đã khởi động, sẵn sàng xử lý...", "INFO", "WORKER")

        while self.is_running:
            task_id = None
            with self._lock:
                if self.queue:
                    task_id = self.queue.pop(0)

            if not task_id:
                time.sleep(2)
                continue

            task = self.get_task(task_id)
            if not task:
                continue

            platform = task["platform"]
            source_url = task["source_url"]
            cfg = ConfigManager.load()
            plat_cfg = cfg.get(platform, {})

            try:
                # GIAI ĐOẠN 1: TẢI VIDEO & METADATA (Lọc thời lượng 30 phút - 3 tiếng)
                self.update_task(task_id, status="DOWNLOADING", progress=15, stage_info="Đang tải video gốc và metadata...")
                LogManager.log(f"[{task_id}] Bắt đầu tải từ {source_url}", "INFO", platform)
                
                min_mins = plat_cfg.get("min_duration_minutes", cfg.get("general", {}).get("min_duration_minutes", 30))
                max_mins = plat_cfg.get("max_duration_minutes", cfg.get("general", {}).get("max_duration_minutes", 180))
                min_secs = int(min_mins * 60)
                max_secs = int(max_mins * 60)

                dl_result = VideoDownloader.download(
                    source_url,
                    task_id,
                    proxy=cfg["general"].get("proxy"),
                    min_duration_seconds=min_secs,
                    max_duration_seconds=max_secs
                )
                if not dl_result["success"]:
                    raise Exception(f"Lỗi tải video: {dl_result.get('error')}")

                raw_video_path = dl_result["video_path"]
                raw_thumb_path = dl_result.get("thumbnail_path")
                orig_title = dl_result.get("title", task["original_title"])
                self.update_task(task_id, original_title=orig_title, progress=35)

                # GIAI ĐOẠN 2: VIẾT LẠI TIÊU ĐỀ BẰNG AI
                self.update_task(task_id, stage_info="AI đang viết lại tiêu đề hấp dẫn & chống trùng lặp...")
                meta_rules = plat_cfg.get("metadata_rules", {})
                new_title = orig_title
                if meta_rules.get("rewrite_title", True):
                    new_title = AIRewriter.rewrite_title(
                        orig_title,
                        gemini_key=cfg["general"].get("gemini_api_key"),
                        openai_key=cfg["general"].get("openai_api_key")
                    )
                    prefix = meta_rules.get("title_prefix", "")
                    suffix = meta_rules.get("title_suffix", "")
                    new_title = f"{prefix}{new_title}{suffix}".strip()
                
                self.update_task(task_id, new_title=new_title, progress=45)
                LogManager.log(f"[{task_id}] Tiêu đề mới: {new_title}", "INFO", "AI")

                # GIAI ĐOẠN 3: TẠO THUMBNAIL MỚI
                thumb_out_path = None
                if meta_rules.get("generate_thumbnail", True):
                    self.update_task(task_id, stage_info="Đang tự động thiết kế thumbnail mới...")
                    style = meta_rules.get("thumbnail_style", "modern_yellow")
                    thumb_out_path = ThumbnailGenerator.create_thumbnail(
                        video_path=raw_video_path,
                        fallback_image_path=raw_thumb_path,
                        title_text=new_title,
                        task_id=task_id,
                        style=style
                    )
                    if thumb_out_path and os.path.exists(thumb_out_path):
                        # URL relative for web serving
                        rel_thumb = f"/storage/thumbnails/{os.path.basename(thumb_out_path)}"
                        self.update_task(task_id, thumbnail_url=rel_thumb)

                # GIAI ĐOẠN 4: RENDER BIẾN ĐỔI VIDEO TRÁNH BẢN QUYỀN (FFMPEG)
                self.update_task(task_id, status="PROCESSING", progress=55, stage_info="FFmpeg đang biến đổi hình ảnh và âm thanh...")
                LogManager.log(f"[{task_id}] FFmpeg bắt đầu transcode...", "INFO", "FFMPEG")
                
                bypass_rules = plat_cfg.get("bypass_rules", {})
                processed_video_path = VideoProcessor.process(
                    input_path=raw_video_path,
                    task_id=task_id,
                    rules=bypass_rules
                )
                self.update_task(task_id, output_video_path=processed_video_path, progress=80)

                # GIAI ĐOẠN 5: TỰ ĐỘNG UPLOAD LÊN KÊNH / FANPAGE ĐÍCH
                self.update_task(task_id, status="UPLOADING", progress=85, stage_info=f"Đang upload lên {platform.upper()}...")
                upload_res = {"success": True, "message": "Giả lập upload thành công"}

                if platform == "youtube":
                    clean_desc = (
                        f"{new_title}\n\n"
                        f"Chào mừng các bạn đã đến với kênh! Hãy bấm Like, Đăng Ký Kênh và Nhấn Chuông thông báo để không bỏ lỡ những video mới và hay nhất mỗi ngày nhé!\n\n"
                        f"Cảm ơn mọi người đã luôn đồng hành và ủng hộ kênh!\n\n"
                        f"#review #phimhay #reviewphim #shorts #viral #trending #phimmoi"
                    )
                    upload_res = YouTubeUploader.upload(
                        video_path=processed_video_path,
                        title=new_title,
                        description=clean_desc,
                        thumbnail_path=thumb_out_path,
                        config=plat_cfg.get("destination", {})
                    )
                elif platform == "facebook":
                    clean_fb_desc = (
                        f"{new_title}\n\n"
                        f"Mọi người xem video thấy hay nhớ bấm Like và Follow Fanpage để đón xem những tập tiếp theo nhé!\n\n"
                        f"#film #reviewphim #phimhay #reels #xuhuong #trending"
                    )
                    upload_res = FacebookUploader.upload(
                        video_path=processed_video_path,
                        title=new_title,
                        description=clean_fb_desc,
                        thumbnail_path=thumb_path,
                        config=plat_cfg.get("destination", {})
                    )

                if not upload_res.get("success"):
                    raise Exception(f"Lỗi khi upload lên {platform}: {upload_res.get('message')}")

                # Tự động comment lần đầu tăng tương tác
                vid_id = upload_res.get("video_id")
                if vid_id:
                    if platform == "youtube":
                        YouTubeUploader.add_comment(vid_id, "Chúc cả nhà xem phim vui vẻ! Mọi người thấy phim hôm nay thế nào? Để lại bình luận cho mình biết nhé! ❤️", plat_cfg.get("destination", {}))
                    elif platform == "facebook":
                        FacebookUploader.add_comment(vid_id, "Chúc cả nhà xem phim vui vẻ! Mọi người thấy phim hôm nay thế nào ạ? Để lại cmt cho mình biết nhé! ❤️", plat_cfg.get("destination", {}))

                # HOÀN THÀNH
                self.update_task(
                    task_id,
                    status="COMPLETED",
                    progress=100,
                    stage_info="Hoàn tất thành công!",
                    completed_at=datetime.now().strftime("%H:%M:%S")
                )
                LogManager.log(f"[{task_id}] Hoàn tất toàn bộ quy trình cho {source_url}", "SUCCESS", platform)

                # DỌN DẸP DUNG LƯỢNG CLOUD
                if cfg["general"].get("clean_temp_after_upload", True):
                    time.sleep(1)
                    if os.path.exists(raw_video_path):
                        try: os.remove(raw_video_path)
                        except Exception: pass
                    if raw_thumb_path and os.path.exists(raw_thumb_path):
                        try: os.remove(raw_thumb_path)
                        except Exception: pass

            except Exception as e:
                err_msg = str(e)
                stack = traceback.format_exc()
                self.update_task(
                    task_id,
                    status="FAILED",
                    progress=0,
                    stage_info=f"Thất bại: {err_msg}",
                    error=err_msg
                )
                LogManager.log(f"[{task_id}] Lỗi: {err_msg}\n{stack}", "ERROR", platform)

task_queue = TaskQueue()
