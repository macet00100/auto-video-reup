import os
import json
from typing import Dict, Any

CONFIG_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.json"))

def _load_dotenv_if_exists():
    """Tự động nạp biến môi trường từ file .env nếu có (dành cho môi trường máy cá nhân/Local)."""
    env_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k and not os.environ.get(k):
                            os.environ[k] = v
        except Exception:
            pass

DEFAULT_CONFIG: Dict[str, Any] = {
    "general": {
        "gemini_api_key": "",
        "openai_api_key": "",
        "scheduler_enabled": True,
        "scheduler_interval_minutes": 15,
        "max_concurrent_tasks": 1,
        "clean_temp_after_upload": True,
        "proxy": ""
    },
    "youtube": {
        "enabled": True,
        "sources": [
            {
                "id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "name": "Google Developers (Kênh mẫu)",
                "url": "https://www.youtube.com/channel/UC_x5XG1OV2P6uZZ5FSM9Ttw",
                "last_video_id": "",
                "enabled": False
            }
        ],
        "destination": {
            "auth_mode": "api",
            "privacy_status": "public",
            "category_id": "24",
            "access_token": "",
            "refresh_token": ""
        },
        "bypass_rules": {
            "hflip": False,
            "speed": 1.03,
            "pitch_shift": True,
            "crop_percent": 3,
            "blur_border": False,
            "color_boost": True,
            "change_fps": True,
            "target_resolution": "720p"
        },
        "metadata_rules": {
            "rewrite_title": True,
            "title_prefix": "",
            "title_suffix": " #viral #shorts",
            "generate_thumbnail": True,
            "thumbnail_style": "modern_yellow"
        }
    },
    "facebook": {
        "enabled": True,
        "sources": [
            {
                "id": "sample_page_123",
                "name": "Nguồn Facebook Video (Mẫu)",
                "url": "https://www.facebook.com/watch/sample",
                "last_video_id": "",
                "enabled": False
            }
        ],
        "destination": {
            "page_id": "",
            "access_token": "",
            "post_as_reel": True
        },
        "bypass_rules": {
            "hflip": False,
            "speed": 1.04,
            "pitch_shift": True,
            "crop_percent": 4,
            "blur_border": False,
            "color_boost": True,
            "change_fps": True,
            "target_resolution": "720p"
        },
        "metadata_rules": {
            "rewrite_title": True,
            "title_prefix": "",
            "title_suffix": " #xuhuong #fbviral #reels",
            "generate_thumbnail": True,
            "thumbnail_style": "gradient_blue"
        }
    }
}

class ConfigManager:
    @staticmethod
    def load() -> Dict[str, Any]:
        _load_dotenv_if_exists()
        if not os.path.exists(CONFIG_FILE):
            ConfigManager.save(DEFAULT_CONFIG)
            data = DEFAULT_CONFIG.copy()
        else:
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for section, vals in DEFAULT_CONFIG.items():
                        if section not in data:
                            data[section] = vals
                        elif isinstance(vals, dict):
                            for k, v in vals.items():
                                if k not in data[section]:
                                    data[section][k] = v
            except Exception:
                data = DEFAULT_CONFIG.copy()

        # Tự động nạp giá trị nhạy cảm từ GitHub Secrets hoặc .env nếu có
        env_mappings = [
            ("GEMINI_API_KEY", ("general", "gemini_api_key")),
            ("YT_CLIENT_ID", ("youtube", "destination", "client_id")),
            ("YT_CLIENT_SECRET", ("youtube", "destination", "client_secret")),
            ("YT_REFRESH_TOKEN", ("youtube", "destination", "refresh_token")),
            ("FB_PAGE_ID", ("facebook", "destination", "page_id")),
            ("FB_ACCESS_TOKEN", ("facebook", "destination", "access_token")),
        ]
        for env_var, path in env_mappings:
            val = os.getenv(env_var)
            if val:
                curr = data
                for p in path[:-1]:
                    if p not in curr or not isinstance(curr[p], dict):
                        curr[p] = {}
                    curr = curr[p]
                curr[path[-1]] = val

        return data

    @staticmethod
    def save(config: Dict[str, Any]) -> bool:
        try:
            # Tạo bản sao sạch: Tuyệt đối không lưu API Key và Access Token vào file config.json của Git
            clean_cfg = json.loads(json.dumps(config))
            if os.getenv("GEMINI_API_KEY") or True:
                # Nếu đã có Secrets / .env thì config.json công khai chỉ để trống
                if os.getenv("GEMINI_API_KEY"):
                    clean_cfg.get("general", {})["gemini_api_key"] = ""
                if os.getenv("YT_CLIENT_ID"):
                    clean_cfg.get("youtube", {}).setdefault("destination", {})["client_id"] = ""
                if os.getenv("YT_CLIENT_SECRET"):
                    clean_cfg.get("youtube", {}).setdefault("destination", {})["client_secret"] = ""
                if os.getenv("YT_REFRESH_TOKEN"):
                    clean_cfg.get("youtube", {}).setdefault("destination", {})["refresh_token"] = ""
                if os.getenv("FB_PAGE_ID"):
                    clean_cfg.get("facebook", {}).setdefault("destination", {})["page_id"] = ""
                if os.getenv("FB_ACCESS_TOKEN"):
                    clean_cfg.get("facebook", {}).setdefault("destination", {})["access_token"] = ""
                if "access_token" in clean_cfg.get("youtube", {}).get("destination", {}):
                    clean_cfg["youtube"]["destination"]["access_token"] = ""

            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(clean_cfg, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    @staticmethod
    def update_source_last_video(platform: str, source_id: str, last_video_id: str):
        cfg = ConfigManager.load()
        if platform in cfg and "sources" in cfg[platform]:
            for s in cfg[platform]["sources"]:
                if s.get("id") == source_id or s.get("url") == source_id:
                    s["last_video_id"] = last_video_id
                    break
            ConfigManager.save(cfg)
