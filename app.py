import os
import sys
import uvicorn

# Đảm bảo mã hóa UTF-8 cho console log
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from apscheduler.schedulers.background import BackgroundScheduler

from core.config import ConfigManager
from core.task_queue import TaskQueue, LogManager
from core.monitor import ChannelMonitor
from core.thumbnail import ThumbnailGenerator

scheduler = BackgroundScheduler()
task_queue = TaskQueue()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Khởi động scheduler quét định kỳ
    cfg = ConfigManager.load()
    interval = cfg.get("general", {}).get("scheduler_interval_minutes", 15)
    
    if cfg.get("general", {}).get("scheduler_enabled", True):
        scheduler.add_job(ChannelMonitor.scan_all, 'interval', minutes=interval, id='channel_scanner', replace_existing=True)
        scheduler.start()
        LogManager.log(f"Trình quét tự động (Scheduler) đã bật, chu kỳ {interval} phút.", "INFO", "SCHEDULER")
    else:
        LogManager.log("Trình quét tự động đang TẮT trong cấu hình.", "INFO", "SCHEDULER")

    # Đảm bảo worker queue chạy
    task_queue.ensure_worker_running()
    yield
    if scheduler.running:
        scheduler.shutdown()

app = FastAPI(title="Auto Video Reup Hub", lifespan=lifespan)

# Mount thư mục tĩnh
base_dir = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(base_dir, "static")), name="static")
app.mount("/storage/thumbnails", StaticFiles(directory=os.path.join(base_dir, "storage", "thumbnails")), name="thumbnails")
templates = Jinja2Templates(directory=os.path.join(base_dir, "templates"))

# --- MODELS ---
class TriggerTaskRequest(BaseModel):
    platform: str
    url: str
    custom_title: Optional[str] = ""

class AddSourceRequest(BaseModel):
    platform: str
    name: str
    url_or_id: str

class ToggleSourceRequest(BaseModel):
    platform: str
    source_id: str
    enabled: bool

class DeleteSourceRequest(BaseModel):
    platform: str
    source_id: str

class ThumbnailPreviewRequest(BaseModel):
    title: str
    style: str = "modern_yellow"

# --- WEB PAGE ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# --- API ROUTES ---
@app.get("/api/config")
async def get_config():
    return JSONResponse(ConfigManager.load())

@app.post("/api/config")
async def save_config(config_data: Dict[str, Any]):
    success = ConfigManager.save(config_data)
    if success:
        # Cập nhật scheduler nếu có thay đổi interval
        try:
            interval = config_data.get("general", {}).get("scheduler_interval_minutes", 15)
            enabled = config_data.get("general", {}).get("scheduler_enabled", True)
            if scheduler.running:
                if enabled:
                    scheduler.reschedule_job('channel_scanner', trigger='interval', minutes=interval)
                else:
                    scheduler.pause_job('channel_scanner')
        except Exception:
            pass
        return {"status": "success", "message": "Cấu hình đã được lưu thành công!"}
    raise HTTPException(status_code=500, detail="Không thể lưu cấu hình")

@app.get("/api/tasks")
async def get_tasks():
    return JSONResponse({
        "tasks": task_queue.list_tasks(limit=40),
        "queue_length": len(task_queue.queue),
        "is_running": task_queue.is_running
    })

@app.post("/api/tasks/trigger")
async def trigger_task(req: TriggerTaskRequest):
    if not req.url or not req.url.startswith("http"):
        raise HTTPException(status_code=400, detail="Vui lòng nhập link video hợp lệ (bắt đầu bằng http)")
    
    platform = req.platform.lower()
    if platform not in ["youtube", "facebook"]:
        raise HTTPException(status_code=400, detail="Nền tảng không hợp lệ")

    task_id = task_queue.add_task(
        platform=platform,
        source_url=req.url.strip(),
        video_title=req.custom_title.strip() if req.custom_title else "",
        metadata={"trigger_mode": "manual"}
    )
    return {"status": "success", "task_id": task_id, "message": f"Đã thêm video vào hàng đợi xử lý [{platform.upper()}]!"}

@app.post("/api/scan")
async def scan_now():
    results = ChannelMonitor.scan_all()
    return {"status": "success", "message": "Đã hoàn thành quét!", "found": results}

@app.post("/api/sources/add")
async def add_source(req: AddSourceRequest):
    cfg = ConfigManager.load()
    platform = req.platform.lower()
    if platform not in ["youtube", "facebook"]:
        raise HTTPException(status_code=400, detail="Nền tảng không hợp lệ")

    url_or_id = req.url_or_id.strip()
    extracted_id = ChannelMonitor.extract_youtube_channel_id(url_or_id) if platform == "youtube" else url_or_id
    
    new_source = {
        "id": extracted_id,
        "name": req.name.strip() or extracted_id,
        "url": url_or_id if url_or_id.startswith("http") else f"https://www.youtube.com/channel/{extracted_id}",
        "last_video_id": "",
        "enabled": True
    }

    if platform not in cfg:
        cfg[platform] = {}
    if "sources" not in cfg[platform]:
        cfg[platform]["sources"] = []

    cfg[platform]["sources"].append(new_source)
    ConfigManager.save(cfg)
    LogManager.log(f"Đã thêm kênh nguồn mới: {req.name} ({platform.upper()})", "INFO", platform)
    return {"status": "success", "message": f"Đã thêm kênh [{req.name}] thành công!"}

@app.delete("/api/sources/delete")
async def delete_source(req: DeleteSourceRequest):
    cfg = ConfigManager.load()
    platform = req.platform.lower()
    if platform in cfg and "sources" in cfg[platform]:
        cfg[platform]["sources"] = [s for s in cfg[platform]["sources"] if s.get("id") != req.source_id]
        ConfigManager.save(cfg)
        return {"status": "success", "message": "Đã xóa kênh nguồn"}
    raise HTTPException(status_code=404, detail="Không tìm thấy nguồn cần xóa")

@app.post("/api/sources/toggle")
async def toggle_source(req: ToggleSourceRequest):
    cfg = ConfigManager.load()
    platform = req.platform.lower()
    if platform in cfg and "sources" in cfg[platform]:
        for s in cfg[platform]["sources"]:
            if s.get("id") == req.source_id:
                s["enabled"] = req.enabled
                ConfigManager.save(cfg)
                return {"status": "success", "message": "Đã cập nhật trạng thái"}
    raise HTTPException(status_code=404, detail="Không tìm thấy nguồn")

@app.get("/api/logs")
async def get_logs():
    return JSONResponse({"logs": LogManager.get_logs(limit=100)})

@app.post("/api/preview/thumbnail")
async def preview_thumbnail(req: ThumbnailPreviewRequest):
    # Sinh thumbnail mẫu
    thumb_path = ThumbnailGenerator.create_thumbnail(
        video_path=None,
        fallback_image_path=None,
        title_text=req.title or "Tiêu Đề Video Mẫu Tuyệt Đỉnh",
        task_id="preview",
        style=req.style
    )
    return {"status": "success", "url": f"/storage/thumbnails/{os.path.basename(thumb_path)}"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860)) # 7860 là port mặc định của Hugging Face Spaces
    LogManager.log(f"Khởi chạy máy chủ tại http://0.0.0.0:{port}", "INFO", "SYSTEM")
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)
