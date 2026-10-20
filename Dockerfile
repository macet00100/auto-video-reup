FROM python:3.11-slim

# Cài đặt FFmpeg và bộ font Unicode tiếng Việt
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-dejavu-core \
    fonts-liberation \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependencies và cài đặt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ mã nguồn
COPY . .

# Tạo sẵn các thư mục storage
RUN mkdir -p storage/temp storage/thumbnails storage/audio storage/logs static/fonts

# Nếu chưa có font thì copy DejaVuSans làm font.ttf mặc định
RUN if [ ! -f static/fonts/font.ttf ]; then \
        cp /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf static/fonts/font.ttf || true; \
    fi

# Cổng mặc định của Hugging Face Spaces và PaaS (7860)
EXPOSE 7860
ENV PORT=7860

# Khởi chạy ứng dụng
CMD ["python", "app.py"]
