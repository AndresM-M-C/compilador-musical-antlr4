FROM python:3.10-slim

# Instala LilyPond, FluidSynth, FFmpeg y Java (necesario para ANTLR4)
RUN apt-get update && apt-get install -y \
    lilypond \
    fluidsynth \
    ffmpeg \
    default-jre \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# Usamos Gunicorn para levantar el servidor Flask/HTTP de forma robusta en el puerto 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "server:app"]
