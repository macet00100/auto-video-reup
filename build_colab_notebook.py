import json
import os
import base64

def generate_notebook():
    files_to_pack = [
        'app.py',
        'core/__init__.py',
        'core/config.py',
        'core/task_queue.py',
        'core/downloader.py',
        'core/processor.py',
        'core/ai_rewriter.py',
        'core/thumbnail.py',
        'core/uploader_yt.py',
        'core/uploader_fb.py',
        'core/monitor.py',
        'templates/index.html',
        'static/css/style.css',
        'static/js/app.js'
    ]

    base_dir = os.path.abspath(os.path.dirname(__file__))
    packed_files = {}

    for rel_path in files_to_pack:
        full_path = os.path.join(base_dir, rel_path)
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                packed_files[rel_path.replace('\\', '/')] = f.read()

    # Convert packed files to a json string embedded in python
    packed_json = json.dumps(packed_files, ensure_ascii=False)
    packed_b64 = base64.b64encode(packed_json.encode('utf-8')).decode('utf-8')

    notebook = {
        "nbformat": 4,
        "nbformat_minor": 0,
        "metadata": {
            "colab": {
                "name": "Chay_Auto_Reup_Studio_Tren_Google_Colab.ipynb",
                "provenance": [],
                "toc_visible": True
            },
            "kernelspec": {
                "name": "python3",
                "display_name": "Python 3"
            },
            "language_info": {
                "name": "python"
            }
        },
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# 🎬 Auto Video Reup Studio (YouTube & Facebook Automation)\n",
                    "**Khởi chạy 1-Click trên Google Cloud (Google Colab Free)**\n",
                    "- Miễn phí 100%, không cần thẻ tín dụng, sử dụng chip và RAM mạnh mẽ từ máy chủ Google.\n",
                    "- Tách biệt hoàn toàn tab YouTube và Facebook.\n",
                    "- Tự động theo dõi kênh qua RSS, lách bản quyền FFmpeg, AI đổi tên video và sinh thumbnail mới."
                ]
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# @title 🚀 BƯỚC 1: Cài đặt môi trường & Khởi tạo dự án (Bấm nút Run/Play bên trái)\n",
                    "import os, sys, json, base64, subprocess, time, re\n",
                    "\n",
                    "print('⏳ [1/3] Đang cài đặt FFmpeg, bộ font Tiếng Việt và thư viện Python trên Google Cloud...')\n",
                    "os.system('apt-get update -qq && apt-get install -y -qq ffmpeg fonts-dejavu-core > /dev/null 2>&1')\n",
                    "os.system('pip install -q fastapi uvicorn yt-dlp pillow requests feedparser apscheduler python-multipart jinja2 google-genai openai > /dev/null 2>&1')\n",
                    "\n",
                    "print('⏳ [2/3] Đang tải công cụ tạo đường link công khai Cloudflare...')\n",
                    "if not os.path.exists('/usr/local/bin/cloudflared'):\n",
                    "    os.system('wget -q -nc https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/local/bin/cloudflared')\n",
                    "    os.system('chmod +x /usr/local/bin/cloudflared')\n",
                    "\n",
                    "print('⏳ [3/3] Đang giải nén mã nguồn Auto Reup Studio...')\n",
                    "app_dir = '/content/auto_reup'\n",
                    "os.makedirs(app_dir, exist_ok=True)\n",
                    "\n",
                    f"packed_b64 = '{packed_b64}'\n",
                    "raw_json = base64.b64decode(packed_b64.encode('utf-8')).decode('utf-8')\n",
                    "files_dict = json.loads(raw_json)\n",
                    "\n",
                    "for rel_path, content in files_dict.items():\n",
                    "    full_file_path = os.path.join(app_dir, rel_path)\n",
                    "    os.makedirs(os.path.dirname(full_file_path), exist_ok=True)\n",
                    "    with open(full_file_path, 'w', encoding='utf-8') as f:\n",
                    "        f.write(content)\n",
                    "\n",
                    "# Tạo các thư mục lưu trữ\n",
                    "for sub in ['storage/temp', 'storage/thumbnails', 'storage/audio', 'storage/logs', 'static/fonts']:\n",
                    "    os.makedirs(os.path.join(app_dir, sub), exist_ok=True)\n",
                    "\n",
                    "# Copy font hệ thống tiếng Việt nếu chưa có\n",
                    "font_target = os.path.join(app_dir, 'static/fonts/font.ttf')\n",
                    "if not os.path.exists(font_target):\n",
                    "    os.system(f'cp /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf {font_target} 2>/dev/null || true')\n",
                    "\n",
                    "print('✅ Cài đặt hoàn tất 100%! Bắt đầu khởi chạy máy chủ...')\n"
                ]
            },
            {
                "cell_type": "code",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": [
                    "# @title 🌐 BƯỚC 2: Khởi chạy Web & Lấy Link truy cập công khai\n",
                    "import subprocess, time, re, sys\n",
                    "\n",
                    "os.chdir('/content/auto_reup')\n",
                    "\n",
                    "# Khởi chạy Uvicorn Backend\n",
                    "server_proc = subprocess.Popen(\n",
                    "    ['uvicorn', 'app:app', '--host', '127.0.0.1', '--port', '7860'],\n",
                    "    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True\n",
                    ")\n",
                    "\n",
                    "# Khởi chạy Cloudflare Tunnel để tạo link công khai HTTPS\n",
                    "tunnel_proc = subprocess.Popen(\n",
                    "    ['/usr/local/bin/cloudflared', 'tunnel', '--url', 'http://127.0.0.1:7860'],\n",
                    "    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True\n",
                    ")\n",
                    "\n",
                    "public_url = None\n",
                    "print('Đang lấy link truy cập từ máy chủ Google Cloud...')\n",
                    "for _ in range(40):\n",
                    "    line = tunnel_proc.stdout.readline()\n",
                    "    match = re.search(r'https://[a-zA-Z0-9-]+\\.trycloudflare\\.com', line)\n",
                    "    if match:\n",
                    "        public_url = match.group(0)\n",
                    "        break\n",
                    "    time.sleep(0.5)\n",
                    "\n",
                    "if public_url:\n",
                    "    print('\\n' + '='*70)\n",
                    "    print('🎉 MÁY CHỦ AUTO REUP ĐÃ HOẠT ĐỘNG THÀNH CÔNG TRÊN GOOGLE CLOUD!')\n",
                    "    print('👉 BẤM VÀO ĐƯỜNG LINK DƯỚI ĐÂY ĐỂ MỞ WEB TRÊN ĐIỆN THOẠI/MÁY TÍNH:')\n",
                    "    print(f'   🔗 {public_url}')\n",
                    "    print('='*70 + '\\n')\n",
                    "    print('(Giữ nguyên tab Google Colab này mở để web hoạt động liên tục)\\n')\n",
                    "else:\n",
                    "    print('⚠️ Chưa lấy được URL tunnel, đang kết nối lại...')\n",
                    "\n",
                    "# Giữ tiến trình chạy để Colab không tắt\n",
                    "try:\n",
                    "    while True:\n",
                    "        time.sleep(10)\n",
                    "except KeyboardInterrupt:\n",
                    "    print('Dừng server.')\n",
                    "    server_proc.terminate()\n",
                    "    tunnel_proc.terminate()\n"
                ]
            }
        ]
    }

    out_file = os.path.join(base_dir, "Chay_Auto_Reup_Tren_Google_Colab.ipynb")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=2, ensure_ascii=False)

    print(f"Generated notebook successfully: {out_file}")

if __name__ == "__main__":
    generate_notebook()
