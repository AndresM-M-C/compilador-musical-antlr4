FROM python:3.10-slim

# Instala LilyPond, FluidSynth, FFmpeg y las fuentes de sonido MIDI
RUN apt-get update && apt-get install -y \
    lilypond \
    fluidsynth \
    fluid-soundfont-gm \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["python3", "server.py"]
