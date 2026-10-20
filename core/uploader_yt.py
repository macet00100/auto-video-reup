import os
import json
import base64
import requests
from typing import Dict, Any, Optional
from core.task_queue import LogManager

class YouTubeUploader:
    @staticmethod
    def get_valid_access_token(config: Dict[str, Any]) -> Optional[str]:
        """Tự động làm mới access token nếu có refresh_token."""
        refresh_token = config.get("refresh_token", "").strip()
        client_id = config.get("client_id", "").strip()
        client_secret = config.get("client_secret", "").strip()

        if refresh_token:
            # 1. Thử refresh qua OAuth token endpoint nếu có Client ID & Secret
            if client_id and client_secret:
                try:
                    res = requests.post("https://oauth2.googleapis.com/token", data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token"
                    }, timeout=15)
                    if res.status_code == 200:
                        new_acc = res.json().get("access_token")
                        if new_acc:
                            LogManager.log("Đã tự động gia hạn YouTube Access Token qua Google OAuth thành công!", "SUCCESS", "YOUTUBE")
                            return new_acc
                except Exception as e:
                    LogManager.log(f"Lỗi refresh Google OAuth: {e}", "WARNING", "YOUTUBE")

            # 2. Thử refresh qua Google Playground service
            try:
                res = requests.post("https://developers.google.com/oauthplayground/refreshAccessToken", json={
                    "refresh_token": refresh_token
                }, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    resp_body = data.get("Response", {}).get("message-body", "")
                    if resp_body:
                        try:
                            token_info = json.loads(resp_body)
                        except Exception:
                            token_info = json.loads(base64.b64decode(resp_body).decode('utf-8', errors='ignore'))
                        new_acc = token_info.get("access_token")
                        if new_acc:
                            LogManager.log("Đã tự động gia hạn YouTube Access Token từ Refresh Token thành công!", "SUCCESS", "YOUTUBE")
                            return new_acc
            except Exception as e:
                LogManager.log(f"Lỗi refresh token từ Playground: {e}", "WARNING", "YOUTUBE")

        # 3. Trả về access token hiện có
        return config.get("access_token", "").strip()

    @staticmethod
    def upload(
        video_path: str,
        title: str,
        description: str,
        thumbnail_path: Optional[str],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        access_token = YouTubeUploader.get_valid_access_token(config)
        privacy_status = config.get("privacy_status", "public")
        category_id = config.get("category_id", "24")

        # Kiểm tra nếu chưa cấu hình Token hoặc Client Secrets
        if not access_token:
            LogManager.log(
                "YouTube Token chưa được cấu hình. Hệ thống chạy ở chế độ TEST (Dry-Run): Video đã render và lưu trữ sẵn sàng.",
                "WARNING", "YOUTUBE"
            )
            return {
                "success": True,
                "simulated": True,
                "message": "Chế độ Test: Video đã render thành công sẵn sàng đăng (Chưa có token YouTube)."
            }

        try:
            # Nếu người dùng có access token Google API
            headers = {"Authorization": f"Bearer {access_token}"}
            
            # Khởi tạo resumable upload session
            init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
            metadata = {
                "snippet": {
                    "title": title[:100],
                    "description": description[:4500],
                    "categoryId": category_id
                },
                "status": {
                    "privacyStatus": privacy_status
                }
            }
            
            init_res = requests.post(init_url, json=metadata, headers=headers)
            if init_res.status_code != 200:
                raise Exception(f"Không thể khởi tạo upload YouTube: {init_res.text}")

            upload_url = init_res.headers.get("Location")
            if not upload_url:
                raise Exception("Không nhận được upload Location URL từ YouTube API")

            # Upload video file
            with open(video_path, "rb") as vf:
                up_res = requests.put(upload_url, data=vf, headers={"Content-Type": "video/mp4"})
            
            if up_res.status_code not in [200, 201]:
                raise Exception(f"Lỗi khi gửi video stream: {up_res.text}")

            video_data = up_res.json()
            new_video_id = video_data.get("id")
            LogManager.log(f"Upload YouTube thành công! Video ID: {new_video_id}", "SUCCESS", "YOUTUBE")

            # Nếu có thumbnail, upload thumbnail
            if thumbnail_path and os.path.exists(thumbnail_path) and new_video_id:
                try:
                    thumb_url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={new_video_id}"
                    with open(thumbnail_path, "rb") as tf:
                        thumb_res = requests.post(thumb_url, data=tf, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"}, timeout=30)
                    if thumb_res.status_code in [200, 201]:
                        LogManager.log(f"Đã cập nhật thumbnail thành công cho video ID: {new_video_id}", "SUCCESS", "YOUTUBE")
                    else:
                        LogManager.log(f"Lưu ý Thumbnail: Kênh cần xác minh SĐT (Intermediate Features) trong YouTube Studio để bật ảnh thu nhỏ tùy chỉnh: {thumb_res.text[:120]}", "WARNING", "YOUTUBE")
                except Exception as ex_thumb:
                    LogManager.log(f"Không thể tải thumbnail lên YouTube: {ex_thumb}", "WARNING", "YOUTUBE")

            return {
                "success": True,
                "video_id": new_video_id,
                "message": f"Upload thành công! Video ID: {new_video_id}"
            }

        except Exception as e:
            LogManager.log(f"Lỗi khi upload YouTube: {str(e)}", "ERROR", "YOUTUBE")
            return {
                "success": False,
                "error": str(e),
                "message": f"Lỗi upload: {str(e)}"
            }

    @staticmethod
    def add_comment(video_id: str, comment_text: str, config: Dict[str, Any]) -> bool:
        """Tự động đăng bình luận dưới video YouTube vừa xuất bản."""
        if not video_id or not comment_text:
            return False
        access_token = YouTubeUploader.get_valid_access_token(config)
        if not access_token:
            return False

        try:
            url = "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            payload = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
            res = requests.post(url, headers=headers, json=payload, timeout=20)
            if res.status_code in [200, 201]:
                LogManager.log(f"Đã tự động đăng bình luận lên YouTube: '{comment_text}'", "SUCCESS", "YOUTUBE")
                return True
            else:
                err = res.json().get("error", {}).get("message", res.text[:120])
                LogManager.log(f"Bình luận YouTube chưa hoàn tất (cần cấp thêm quyền youtube.force-ssl): {err}", "WARNING", "YOUTUBE")
                return False
        except Exception as e:
            LogManager.log(f"Lỗi khi gửi bình luận YouTube: {e}", "WARNING", "YOUTUBE")
            return False
