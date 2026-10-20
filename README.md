# 🎬 Auto Video Reup Studio (YouTube & Facebook Automation)

Hệ thống tự động hóa theo dõi kênh gốc, xử lý video & âm thanh lách bản quyền, tự động viết lại tiêu đề bằng AI, thiết kế ảnh bìa (thumbnail) mới và đăng tải đa nền tảng (YouTube & Facebook Fanpage/Reels), được tối ưu hóa đặc biệt để **chạy 24/7 trên các nền tảng Cloud Miễn Phí (Free Cloud)**.

---

## 🌟 Tính Năng Nổi Bật

1. **Giao Diện Web Trực Quan & Tách Biệt Hoàn Toàn**:
   - Tab **🔴 YouTube Hub** và Tab **🔵 Facebook Hub** được tách riêng biệt để không gây nhầm lẫn cấu hình và kênh đích.
   - Bảng điều khiển giám sát tiến trình thời gian thực (Real-time Task Queue) và cửa sổ xem log trực tiếp (Terminal Logs).
   - Công cụ **Test Reup Nhanh**: Cho phép dán bất kỳ link video nào để kiểm tra ngay toàn bộ quy trình.

2. **Tự Động Theo Dõi Kênh Gốc (Không Tốn Quota API)**:
   - Theo dõi nhiều kênh YouTube gốc cùng lúc thông qua luồng **RSS Feed XML** (tốc độ cập nhật tức thì, không tiêu tốn hạn mức Google API).
   - Theo dõi các nguồn video/reels Facebook.

3. **Bộ Lọc Lách Bản Quyền Đa Tầng (FFmpeg Engine)**:
   - **Hình ảnh**: Lật gương (`hflip`), co dãn crop mép 2-5%, can thiệp độ tương phản/bão hòa màu, thay đổi chu kỳ FPS (30fps), đổi tốc độ (1.03x - 1.05x).
   - **Âm thanh**: Dịch chuyển cao độ (Pitch Shift qua `asetrate`), bù trừ tempo giữ âm tự nhiên, tăng âm lượng, hỗ trợ chèn nhạc nền nhẹ phá vỡ Content ID.

4. **Tự Động Đổi Tên & Sinh Thumbnail Mới**:
   - **AI Title Rewriter**: Tích hợp Google Gemini API (miễn phí) và OpenAI để viết lại tiêu đề chuẩn SEO, giật tít tiếng Việt. Tự động chuyển sang *Bộ quy tắc ngôn ngữ Offline* nếu chưa có API key.
   - **Thumbnail Studio (Pillow)**: Tự động trích xuất frame đẹp nhất từ video, phủ dải gradient tối, đóng dấu badge "🔥 CỰC HOT" và vẽ chữ tiếng Việt nghệ thuật nổi bật.

5. **Tối Ưu Tuyệt Đối Cho Cloud Free**:
   - Sử dụng cơ chế hàng đợi xử lý tuần tự (Sequential Worker Queue), giới hạn CPU threads và transcode preset `veryfast` giúp RAM không bao giờ vượt quá 1.5GB (hoàn toàn an toàn trên Cloud Free có RAM 16GB hoặc 24GB).
   - Tự động xóa file video tạm ngay sau khi hoàn thành để không bị đầy ổ cứng miễn phí.

---

## 🚀 Hướng Dẫn Triển Khai Chạy Miễn Phí Trên Cloud (Không Chạy Local)

### 🥇 Cách 1: Triển khai lên Hugging Face Spaces (Khuyên dùng nhất - 16GB RAM Free)
Hugging Face Spaces cung cấp môi trường Docker miễn phí với **2 vCPU và 16GB RAM**, không bắt buộc nhập thẻ tín dụng:

1. Đăng ký tài khoản tại [HuggingFace.co](https://huggingface.co).
2. Nhấn vào ảnh đại diện góc phải -> Chọn **New Space**.
3. Điền thông tin:
   - **Space name**: `auto-video-reup`
   - **License**: `mit`
   - **Select the Space SDK**: Chọn **Docker** -> Chọn template **Blank**.
   - **Space Hardware**: Chọn **Free (2 vCPU - 16GB RAM)**.
4. Đẩy toàn bộ mã nguồn của dự án này lên Git của Space (hoặc upload trực tiếp các file lên giao diện web của Space, gồm `app.py`, `Dockerfile`, `requirements.txt`, các thư mục `core`, `static`, `templates`).
5. Hugging Face sẽ tự động build container trong 1-2 phút và cung cấp cho bạn một đường link web công khai để sử dụng 24/7!

---

### 🥈 Cách 2: Triển khai lên Oracle Cloud Always Free (VPS 24GB RAM 4 Core Miễn Phí Vĩnh Viễn)
Oracle Cloud cung cấp miễn phí vĩnh viễn máy ảo Ubuntu ARM với 4 OCPU và 24GB RAM:

1. Đăng nhập vào VPS Oracle Cloud qua SSH.
2. Cài đặt Docker & Docker Compose:
   ```bash
   sudo apt update && sudo apt install -y docker.io docker-compose
   ```
3. Clone mã nguồn hoặc tải thư mục dự án lên VPS.
4. Chạy ứng dụng ngầm:
   ```bash
   docker-compose up -d --build
   ```
5. Mở port `7860` trên Security List của Oracle Cloud để truy cập vào IP của VPS: `http://<IP-VPS>:7860`.

---

## 💻 Hướng Dẫn Chạy & Thử Nghiệm Tại Máy (Local)

Nếu bạn muốn chạy thử nghiệm ngay trên máy tính của mình trước khi đẩy lên Cloud:

1. Cài đặt thư viện:
   ```bash
   pip install -r requirements.txt
   ```
2. Khởi chạy server:
   ```bash
   python app.py
   ```
3. Mở trình duyệt truy cập: `http://localhost:7860`.

---

## 🔑 Hướng Dẫn Cấu Hình API (Tùy Chọn)

- **Gemini API Key (Miễn phí)**: Truy cập [Google AI Studio](https://aistudio.google.com/) để lấy API key miễn phí (15 yêu cầu/phút), dán vào tab *AI & Thumbnail Studio*.
- **YouTube Upload**: Để upload tự động qua API, tạo OAuth 2.0 Client ID trên Google Cloud Console (YouTube Data API v3). Nếu chưa có token, hệ thống sẽ chạy ở **chế độ Dry-Run/Test** (vẫn tải, lách bản quyền, sinh ảnh bìa và lưu video hoàn chỉnh vào máy/cloud).
- **Facebook Fanpage**: Lấy Page Access Token tại [Meta for Developers](https://developers.facebook.com/tools/explorer/) với quyền `pages_manage_posts` và `pages_read_engagement`.
