import os
import subprocess
from typing import List, Tuple
import cv2
import numpy as np
from core.task_queue import LogManager

class LogoDetector:
    @staticmethod
    def detect_watermarks(video_path: str, num_samples: int = 5) -> List[Tuple[int, int, int, int]]:
        """
        Quét thông minh toàn màn hình video:
        - Lấy mẫu các frame tại nhiều thời điểm khác nhau (10%, 25%, 50%, 75%, 90% thời lượng).
        - So sánh viền tĩnh (static edges) và độ lệch chuẩn để tìm các vùng logo/watermark không đổi.
        - Trả về danh sách các vùng tọa độ (x, y, w, h) của mọi logo xuất hiện trên màn hình.
        """
        if not os.path.exists(video_path):
            return []

        try:
            # 1. Trích xuất kích thước và thời lượng video
            probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=s=x:p=0', video_path]
            parts = subprocess.run(probe_cmd, stdout=subprocess.PIPE, text=True, check=True).stdout.strip().split('x')
            w, h = int(parts[0]), int(parts[1])

            dur_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', video_path]
            dur_str = subprocess.run(dur_cmd, stdout=subprocess.PIPE, text=True).stdout.strip()
            dur = float(dur_str) if dur_str else 60.0

            # 2. Lấy mẫu nhanh 5-6 frames tại các phân đoạn thời gian khác nhau
            percentages = [0.10, 0.25, 0.50, 0.70, 0.88]
            sample_times = [dur * p for p in percentages]
            frames = []
            temp_dir = os.path.dirname(video_path)

            for i, t in enumerate(sample_times):
                out_f = os.path.join(temp_dir, f"_temp_detect_{i}.jpg")
                cmd = ['ffmpeg', '-y', '-ss', str(t), '-i', video_path, '-vframes', '1', out_f]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if os.path.exists(out_f):
                    img = cv2.imread(out_f)
                    if img is not None:
                        frames.append(img)
                    try:
                        os.remove(out_f)
                    except Exception:
                        pass

            if len(frames) < 3:
                return []

            # 3. Tính toán các đường nét cố định (Static Edges) xuyên suốt các cảnh phim
            gray_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
            edge_stack = np.stack([cv2.Canny(g, 60, 160) for g in gray_frames], axis=0)
            static_edges = np.min(edge_stack, axis=0)

            # 4. Loại bỏ vùng phụ đề trung tâm (30% dưới đáy ở giữa màn hình) để không xóa nhầm sub
            mask = np.ones_like(static_edges, dtype=np.uint8) * 255
            sub_y1, sub_y2 = int(h * 0.70), h
            sub_x1, sub_x2 = int(w * 0.18), int(w * 0.82)
            mask[sub_y1:sub_y2, sub_x1:sub_x2] = 0
            filtered = cv2.bitwise_and(static_edges, mask)

            # 5. Giãn nở vùng phát hiện (Dilation) để gom các khối chữ và icon logo
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (12, 12))
            dilated = cv2.dilate(filtered, kernel, iterations=2)
            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            detected_boxes = []
            for cnt in contours:
                x, y, bw, bh = cv2.boundingRect(cnt)
                ratio = bw / max(1, bh)
                area = bw * bh
                
                # Bộ lọc logo thông minh:
                # - Tỉ lệ khung hình nằm trong khoảng 0.5 đến 4.0 (loại bỏ các đường viền đen hẹp đứng)
                # - Kích thước logo hợp lý: chiều rộng từ 30px đến 45% màn hình, chiều cao từ 20px đến 30% màn hình
                # - Diện tích tối thiểu 800px
                if 0.5 <= ratio <= 4.0 and 30 <= bw <= w * 0.45 and 20 <= bh <= h * 0.30 and area >= 800:
                    # Mở rộng biên an toàn thêm 8 pixel để xóa trọn vẹn bóng mờ của logo
                    pad = 8
                    px = max(0, x - pad)
                    py = max(0, y - pad)
                    pw = min(w - px, bw + pad * 2)
                    ph = min(h - py, bh + pad * 2)
                    detected_boxes.append((px, py, pw, ph))
                    LogManager.log(f"Phát hiện vị trí logo tự động: x={px}, y={py}, w={pw}, h={ph}", "INFO", "DELOGO")

            return detected_boxes

        except Exception as e:
            LogManager.log(f"Lỗi khi quét logo tự động: {e}", "WARNING", "DELOGO")
            return []
