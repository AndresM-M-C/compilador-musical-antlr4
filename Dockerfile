FROM python:3.10-slim

# Instala únicamente las dependencias de audio/partituras necesarias (sin Java)
RUN apt-get update && apt-get install -y \
    lilypond \
    fluidsynth \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["python3", "server.py"]
