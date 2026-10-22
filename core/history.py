import os
import json
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional
from core.task_queue import LogManager

HISTORY_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "storage", "processed_history.json"))

class HistoryManager:
    @staticmethod
    def _load_raw() -> Dict[str, Any]:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        if not os.path.exists(HISTORY_FILE):
            default_history = {
                "processed_video_ids": [
                    "28iReVaAQN8",
                    "BBe_1Ff9ghU",
                    "XmafYrR-DIA",
                    "e93_3WKmFHg",
                    "PGkiRafUxdY",
                    "cr9zPocV2DA"
                ],
                "history": {
                    "e93_3WKmFHg": {
                        "title": "Nhà Chồng Coi Thường, Chê Cô Không Đủ Giàu...",
                        "youtube_uploaded": True,
                        "facebook_uploaded": True,
                        "processed_at": "2026-10-20T07:00:00"
                    },
                    "PGkiRafUxdY": {
                        "title": "P9 Xuyên Không Về Thời Loạn Lạc...",
                        "youtube_uploaded": True,
                        "facebook_uploaded": True,
                        "processed_at": "2026-10-20T07:00:00"
                    },
                    "cr9zPocV2DA": {
                        "title": "Xuyên Không Về Nhà Minh Sở Hữu Niệm Lực...",
                        "youtube_uploaded": True,
                        "facebook_uploaded": True,
                        "processed_at": "2026-10-20T07:00:00"
                    }
                }
            }
            HistoryManager._save_raw(default_history)
            return default_history

        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    data = {}
                if "processed_video_ids" not in data:
                    data["processed_video_ids"] = []
                if "history" not in data:
                    data["history"] = {}
                return data
        except Exception as e:
            LogManager.log(f"Lỗi khi đọc file lịch sử {HISTORY_FILE}: {e}", "WARNING", "HISTORY")
            return {"processed_video_ids": [], "history": {}}

    @staticmethod
    def _save_raw(data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        temp_file = HISTORY_FILE + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, HISTORY_FILE)
        except Exception as e:
            LogManager.log(f"Lỗi khi lưu file lịch sử: {e}", "ERROR", "HISTORY")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    @staticmethod
    def is_processed(video_id: str) -> bool:
        """Kiểm tra video ID đã từng được xử lý tải lên hay chưa."""
        if not video_id:
            return False
        data = HistoryManager._load_raw()
        processed_set = set(data.get("processed_video_ids", []))
        return video_id in processed_set

    @staticmethod
    def is_uploaded_to(video_id: str, platform: str) -> bool:
        """Kiểm tra video ID đã được upload lên platform cụ thể (youtube hoặc facebook) chưa."""
        if not video_id:
            return False
        data = HistoryManager._load_raw()
        record = data.get("history", {}).get(video_id, {})
        key = f"{platform.lower()}_uploaded"
        return bool(record.get(key, False))

    @staticmethod
    def record_processed(
        video_id: str,
        title: str,
        yt_uploaded: bool = False,
        fb_uploaded: bool = False,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """Lưu lại trạng thái video đã xử lý vào file persistent JSON."""
        if not video_id:
            return
        data = HistoryManager._load_raw()
        ids = data.get("processed_video_ids", [])
        if video_id not in ids:
            ids.append(video_id)
        data["processed_video_ids"] = ids

        existing_record = data.get("history", {}).get(video_id, {})
        data.setdefault("history", {})[video_id] = {
            "title": title or existing_record.get("title", ""),
            "youtube_uploaded": yt_uploaded or existing_record.get("youtube_uploaded", False),
            "facebook_uploaded": fb_uploaded or existing_record.get("facebook_uploaded", False),
            "processed_at": datetime.now().isoformat(),
            "extra": extra or existing_record.get("extra", {})
        }

        HistoryManager._save_raw(data)
        LogManager.log(f"Đã lưu video ID [{video_id}] vào lịch sử chống trùng lặp vĩnh viễn.", "SUCCESS", "HISTORY")

    @staticmethod
    def merge_with_remote() -> None:
        """Hòa nhập lịch sử local với lịch sử mới nhất trên origin/main để chống conflict tuyệt đối."""
        try:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            # 1. Merge processed_history.json
            show_res = subprocess.run(
                ["git", "show", "origin/main:storage/processed_history.json"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            if show_res.returncode == 0 and show_res.stdout.strip():
                remote_data = json.loads(show_res.stdout)
                local_data = HistoryManager._load_raw()

                combined_ids = list(dict.fromkeys(remote_data.get("processed_video_ids", []) + local_data.get("processed_video_ids", [])))
                combined_history = {**remote_data.get("history", {}), **local_data.get("history", {})}

                merged_data = {
                    "processed_video_ids": combined_ids,
                    "history": combined_history
                }
                HistoryManager._save_raw(merged_data)

            # 2. Merge replied_comments.json nếu có
            rep_res = subprocess.run(
                ["git", "show", "origin/main:storage/replied_comments.json"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                encoding="utf-8"
            )
            if rep_res.returncode == 0 and rep_res.stdout.strip():
                try:
                    from core.auto_reply import AutoReplyBot, REPLIED_FILE
                    remote_rep = json.loads(rep_res.stdout)
                    local_rep = AutoReplyBot._load_replied_ids()
                    merged_rep = {
                        "youtube": list(dict.fromkeys(remote_rep.get("youtube", []) + local_rep.get("youtube", []))),
                        "facebook": list(dict.fromkeys(remote_rep.get("facebook", []) + local_rep.get("facebook", [])))
                    }
                    with open(REPLIED_FILE, "w", encoding="utf-8") as rf:
                        json.dump(merged_rep, rf, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        except Exception as e:
            LogManager.log(f"Lỗi khi hòa nhập lịch sử với remote: {e}", "WARNING", "HISTORY")

    @staticmethod
    def sync_to_git(commit_msg: str = "chore: update processed history [skip ci]") -> bool:
        """Tự động đồng bộ file lịch sử và config lên Git repository an toàn tuyệt đối (chống conflict 100%)."""
        try:
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            if not os.path.exists(os.path.join(repo_root, ".git")):
                return False

            subprocess.run(["git", "config", "user.name", "AutoReup Bot"], cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "bot@autoreup.local"], cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # 1. Fetch remote origin/main mới nhất
            subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_root, capture_output=True, text=True)

            # 2. Hòa nhập file lịch sử local với remote
            HistoryManager.merge_with_remote()

            # 3. Reset HEAD về origin/main mà vẫn giữ nguyên file working tree (Fast-Forward an toàn)
            subprocess.run(["git", "reset", "origin/main"], cwd=repo_root, capture_output=True, text=True)

            # 4. Stage các file dữ liệu (chỉ đồng bộ dữ liệu lịch sử và comment đã trả lời, không clobber config)
            candidate_files = [
                "storage/processed_history.json",
                "storage/replied_comments.json"
            ]
            files_to_add = []
            for rel in candidate_files:
                fpath = os.path.join(repo_root, rel)
                if not os.path.exists(fpath):
                    try:
                        os.makedirs(os.path.dirname(fpath), exist_ok=True)
                        with open(fpath, "w", encoding="utf-8") as f:
                            f.write("{}\n")
                    except Exception:
                        pass
                if os.path.exists(fpath):
                    files_to_add.append(rel)

            if files_to_add:
                add_res = subprocess.run(["git", "add"] + files_to_add, cwd=repo_root, capture_output=True, text=True)
                if add_res.returncode != 0:
                    LogManager.log(f"Git add cảnh báo: {add_res.stderr.strip()}", "WARNING", "GIT")

            # 5. Kiểm tra xem có thay đổi thực sự hay không
            diff_res = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo_root)
            if diff_res.returncode == 0:
                LogManager.log("Không có thay đổi mới cần commit lên Git.", "INFO", "GIT")
                return True

            cmd_commit = ["git", "commit", "-m", commit_msg]
            commit_res = subprocess.run(cmd_commit, cwd=repo_root, capture_output=True, text=True)
            if commit_res.returncode != 0:
                LogManager.log(f"Git commit không thành công: {commit_res.stderr.strip()}", "WARNING", "GIT")
                return False

            cmd_push = ["git", "push", "origin", "HEAD:main"]
            res = subprocess.run(cmd_push, cwd=repo_root, capture_output=True, text=True)

            if res.returncode == 0:
                LogManager.log(f"Đã đồng bộ lịch sử video lên Git thành công! ({commit_msg})", "SUCCESS", "GIT")
                return True
            else:
                LogManager.log(f"Không thể push Git: {res.stderr.strip()}", "WARNING", "GIT")
                return False
        except Exception as e:
            LogManager.log(f"Lỗi khi đồng bộ Git: {e}", "WARNING", "GIT")
            return False
