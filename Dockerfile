FROM python:3.13-slim

WORKDIR /app

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    portaudio19-dev \
    curl \
    ca-certificates \
    gpg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Copy application files
COPY local_voice_chat.py .
COPY README.md .
COPY pyproject.toml .
COPY uv.lock .
COPY start.sh .

# Make the start script executable
RUN chmod +x start.sh

# Install dependencies using pip directly
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    fastrtc==0.0.19 \
    "fastrtc-moonshine-onnx>=20241016" \
    "onnxruntime>=1.21.0" \
    kokoro-onnx>=0.4.7 \
    loguru>=0.7.3 \
    ollama>=0.4.7 \
    pyaudio \
    pydub \
    numpy

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
ENV OLLAMA_HOST=localhost:11434

# Create log directory
RUN mkdir -p /app/logs && chmod 777 /app/logs

# Expose ports for the UI and Ollama
EXPOSE 8080 11434

# Run the startup script that will start both Ollama and the voice agent
CMD ["/app/start.sh"]