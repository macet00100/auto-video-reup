import os
import requests
from typing import Dict, Any, Optional
from core.task_queue import LogManager

class FacebookUploader:
    @staticmethod
    def upload(
        video_path: str,
        title: str,
        description: str,
        thumbnail_path: Optional[str] = None,
        config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        if config is None:
            config = {}
        page_id = config.get("page_id", "").strip()
        access_token = config.get("access_token", "").strip()

        if not page_id or not access_token:
            LogManager.log(
                "Facebook Page ID hoặc Access Token chưa được nhập. Hệ thống chạy ở chế độ TEST (Dry-Run): Video đã render và lưu trữ thành công.",
                "WARNING", "FACEBOOK"
            )
            return {
                "success": True,
                "simulated": True,
                "message": "Chế độ Test: Video đã render thành công (Chưa có Facebook Page Token)."
            }

        if not os.path.exists(video_path):
            return {"success": False, "error": f"Không tìm thấy file video: {video_path}"}

        # Tự động lấy Page Access Token nếu token là User Token
        try:
            pt_res = requests.get(
                f"https://graph.facebook.com/v19.0/{page_id}?fields=access_token&access_token={access_token}",
                timeout=15
            )
            pt_data = pt_res.json()
            if pt_data.get("access_token"):
                access_token = pt_data["access_token"]
        except Exception:
            pass

        file_size = os.path.getsize(video_path)
        file_size_mb = round(file_size / (1024 * 1024), 1)

        try:
            LogManager.log(f"Bắt đầu tải video lên Facebook Fanpage ID: {page_id} (Dung lượng: {file_size_mb} MB)...", "INFO", "FACEBOOK")

            # BƯỚC 1: KHỞI TẠO PHIÊN UPLOAD (START PHASE)
            api_url = f"https://graph-video.facebook.com/v19.0/{page_id}/videos"
            start_res = requests.post(
                api_url,
                data={
                    'upload_phase': 'start',
                    'file_size': file_size,
                    'access_token': access_token
                },
                timeout=60
            )
            start_data = start_res.json()
            if "upload_session_id" not in start_data:
                err_msg = start_data.get("error", {}).get("message", start_res.text)
                raise Exception(f"Không thể khởi tạo phiên upload: {err_msg}")

            session_id = start_data["upload_session_id"]
            video_id = start_data.get("video_id")
            start_offset = int(start_data.get("start_offset", 0))
            end_offset = int(start_data.get("end_offset", file_size))

            # BƯỚC 2: CHUYỂN DỮ LIỆU TỪNG PHẦN (TRANSFER PHASE)
            chunk_size = 10 * 1024 * 1024  # 10MB mỗi chunk
            with open(video_path, 'rb') as f:
                while start_offset < file_size:
                    f.seek(start_offset)
                    bytes_to_read = min(end_offset - start_offset, chunk_size)
                    chunk_data = f.read(bytes_to_read)

                    progress = round((start_offset / file_size) * 100, 1)
                    uploaded_mb = round(start_offset / (1024 * 1024), 1)
                    LogManager.log(f"Đang tải lên Facebook: {progress}% ({uploaded_mb}MB / {file_size_mb}MB)...", "INFO", "FACEBOOK")

                    transfer_res = requests.post(
                        api_url,
                        data={
                            'upload_phase': 'transfer',
                            'upload_session_id': session_id,
                            'start_offset': start_offset,
                            'access_token': access_token
                        },
                        files={'video_file_chunk': chunk_data},
                        timeout=300
                    )
                    transfer_data = transfer_res.json()
                    if "start_offset" not in transfer_data:
                        err_msg = transfer_data.get("error", {}).get("message", transfer_res.text)
                        raise Exception(f"Lỗi tải dữ liệu tại vị trí {uploaded_mb}MB: {err_msg}")

                    new_start = int(transfer_data["start_offset"])
                    new_end = int(transfer_data.get("end_offset", min(new_start + chunk_size, file_size)))
                    if new_start == start_offset:
                        break
                    start_offset = new_start
                    end_offset = new_end

            # BƯỚC 3: HOÀN TẤT & ĐĂNG BÀI (FINISH PHASE)
            LogManager.log("Đã tải xong toàn bộ file video! Đang xuất bản bài đăng Facebook...", "INFO", "FACEBOOK")
            finish_res = requests.post(
                api_url,
                data={
                    'upload_phase': 'finish',
                    'upload_session_id': session_id,
                    'title': title[:100],
                    'description': description,
                    'access_token': access_token,
                    'published': True
                },
                timeout=120
            )
            finish_data = finish_res.json()
            if finish_data.get("success", False):
                final_video_id = video_id or session_id
                fb_url = f"https://www.facebook.com/watch/?v={final_video_id}"
                LogManager.log(f"Đăng tải video lên Facebook thành công! Link: {fb_url}", "SUCCESS", "FACEBOOK")

                # BƯỚC 4: TỰ ĐỘNG THIẾT LẬP ẢNH BÌA (THUMBNAIL) NẾU CÓ
                if thumbnail_path and os.path.exists(thumbnail_path):
                    FacebookUploader.set_thumbnail(final_video_id, thumbnail_path, config)

                return {
                    "success": True,
                    "video_id": final_video_id,
                    "url": fb_url,
                    "message": f"Upload Facebook thành công! Link: {fb_url}"
                }
            else:
                err_msg = finish_data.get("error", {}).get("message", finish_res.text)
                raise Exception(f"Facebook từ chối xuất bản bài viết: {err_msg}")

        except Exception as e:
            LogManager.log(f"Lỗi khi upload Facebook: {str(e)}", "ERROR", "FACEBOOK")
            return {
                "success": False,
                "error": str(e),
                "message": f"Lỗi upload FB: {str(e)}"
            }

    @staticmethod
    def set_thumbnail(video_id: str, thumbnail_path: str, config: Dict[str, Any]) -> bool:
        """Cài đặt ảnh bìa / thumbnail chính cho video Facebook (chuẩn tỉ lệ, is_preferred=True)."""
        if not video_id or not thumbnail_path or not os.path.exists(thumbnail_path):
            return False
        page_id = config.get("page_id", "").strip()
        access_token = config.get("access_token", "").strip()
        if not access_token:
            return False

        page_token = access_token
        try:
            pt_res = requests.get(
                f"https://graph.facebook.com/v19.0/{page_id}?fields=access_token&access_token={access_token}",
                timeout=15
            )
            pt_data = pt_res.json()
            if pt_data.get("access_token"):
                page_token = pt_data["access_token"]
        except Exception:
            pass

        try:
            LogManager.log(f"Đang tải ảnh bìa (thumbnail) lên Facebook cho video {video_id}...", "INFO", "FACEBOOK")
            with open(thumbnail_path, "rb") as tf:
                files = {"source": ("thumbnail.jpg", tf, "image/jpeg")}
                data = {"is_preferred": "true", "access_token": page_token}
                res = requests.post(
                    f"https://graph.facebook.com/v19.0/{video_id}/thumbnails",
                    files=files,
                    data=data,
                    timeout=60
                )
                res_data = res.json()
                if res.status_code in [200, 201] and res_data.get("success", False):
                    LogManager.log(f"Đã cập nhật ảnh bìa (thumbnail) thành công cho video Facebook: {video_id}", "SUCCESS", "FACEBOOK")
                    return True
                else:
                    LogManager.log(f"Không thể cập nhật ảnh bìa Facebook: {res.text}", "WARNING", "FACEBOOK")
                    return False
        except Exception as e:
            LogManager.log(f"Lỗi khi gửi ảnh bìa Facebook: {e}", "WARNING", "FACEBOOK")
            return False

    @staticmethod
    def add_comment(video_id: str, comment_text: str, config: Dict[str, Any]) -> bool:
        """Tự động đăng bình luận dưới video Facebook vừa xuất bản."""
        if not video_id or not comment_text:
            return False
        page_id = config.get("page_id", "").strip()
        access_token = config.get("access_token", "").strip()
        if not access_token:
            return False

        page_token = access_token
        try:
            pt_res = requests.get(
                f"https://graph.facebook.com/v19.0/{page_id}?fields=access_token&access_token={access_token}",
                timeout=15
            )
            pt_data = pt_res.json()
            if pt_data.get("access_token"):
                page_token = pt_data["access_token"]
        except Exception:
            pass

        # Thử bình luận qua endpoint /{video_id}/comments hoặc /{page_id}_{video_id}/comments
        for target_id in [video_id, f"{page_id}_{video_id}"]:
            try:
                url = f"https://graph.facebook.com/v19.0/{target_id}/comments"
                res = requests.post(
                    url,
                    data={"message": comment_text, "access_token": page_token},
                    timeout=20
                )
                if res.status_code in [200, 201]:
                    LogManager.log(f"Đã tự động đăng bình luận lên Facebook: '{comment_text}'", "SUCCESS", "FACEBOOK")
                    return True
            except Exception:
                pass

        LogManager.log("Bình luận Facebook chưa hoàn tất (Page Token cần cấp thêm quyền pages_manage_engagement).", "WARNING", "FACEBOOK")
        return False
