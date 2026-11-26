import glob
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler


_MIME_POR_EXT = {
    ".mp3": ("audio/mpeg", True),
    ".wav": ("audio/wav", True),
    ".pdf": ("application/pdf", True),
    ".png": ("image/png", True),
    ".svg": ("image/svg+xml", True),
    ".mid": ("audio/midi", False),
    ".midi": ("audio/midi", False),
    ".bzl": ("text/plain; charset=utf-8", False),
    ".ly": ("text/plain; charset=utf-8", False),
}

_SEMITONO_LILYPOND = {
    "c": ("C", "", 0),
    "cis": ("C", "#", 1),
    "des": ("D", "b", 1),
    "d": ("D", "", 2),
    "dis": ("D", "#", 3),
    "es": ("E", "b", 3),
    "ees": ("E", "b", 3),
    "e": ("E", "", 4),
    "f": ("F", "", 5),
    "fis": ("F", "#", 6),
    "ges": ("G", "b", 6),
    "g": ("G", "", 7),
    "gis": ("G", "#", 8),
    "as": ("A", "b", 8),
    "aes": ("A", "b", 8),
    "a": ("A", "", 9),
    "ais": ("A", "#", 10),
    "bes": ("B", "b", 10),
    "b": ("B", "", 11),
}

_RE_NOTA_LY = re.compile(r"^([a-g](?:is|es)?)([' ,]*)(4)$")
_RE_TEMPO_LY = re.compile(r"^\\tempo\s+4\s*=\s*(\d+)$")
_RE_INST_LY = re.compile(r'^\\set\s+Staff\.midiInstrument\s*=\s*#"([^"]+)"$')


def sanitizar_nombre(nombre):
    """Convierte el título ingresado en un nombre de archivo seguro."""
    crudo = (nombre or "").strip()
    if crudo.lower().endswith(".bzl"):
        crudo = crudo[:-4]
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", crudo)
        if unicodedata.category(c) != "Mn"
    )
    limpio = re.sub(r"[^A-Za-z0-9_-]+", "_", sin_acentos).strip("_-")
    return limpio or "MiCancion"


def extraer_notas_de_ly(contenido_ly):
    """Extrae la secuencia de notas, cambios de tempo e instrumento desde un .ly."""
    eventos = []
    tempo_actual = 120
    inst_actual = "acoustic grand"

    for linea in contenido_ly.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        m_tempo = _RE_TEMPO_LY.match(linea)
        if m_tempo:
            tempo_actual = int(m_tempo.group(1))
            continue
        m_inst = _RE_INST_LY.match(linea)
        if m_inst:
            inst_actual = m_inst.group(1)
            continue
        if linea.startswith("\\") or linea in ("{", "}"):
            continue

        for tok in linea.split():
            m_nota = _RE_NOTA_LY.match(tok)
            if not m_nota:
                continue
            base, marcas, _ = m_nota.groups()
            info = _SEMITONO_LILYPOND.get(base)
            if not info:
                continue
            letra, alt, semitono = info
            octava = 3 + marcas.count("'") - marcas.count(",")
            midi = 12 * (octava + 1) + semitono
            eventos.append({
                "nota": f"{letra}{alt}{octava}",
                "letra": letra,
                "alteracion": alt,
                "octava": octava,
                "lilypond": tok,
                "midi": midi,
                "tempo": tempo_actual,
                "instrumento": inst_actual,
            })

    return eventos


def _limpiar_artefactos_previos(base_path):
    """Evita que archivos de compilaciones anteriores oculten errores nuevos."""
    for ext in (".pdf", ".mp3", ".wav", ".midi", ".mid", ".ly"):
        ruta = base_path + ext
        if os.path.exists(ruta):
            os.remove(ruta)
    for png in glob.glob(glob.escape(base_path) + "_page*.png"):
        os.remove(png)


def _renderizar_paginas_png(pdf_path, base_path):
    """Convierte cada página del PDF de LilyPond en PNG de alta nitidez si pdftoppm está disponible."""
    if not os.path.exists(pdf_path) or shutil.which("pdftoppm") is None:
        return []
    prefijo = base_path + "_page"
    r = subprocess.run(
        ["pdftoppm", "-png", "-r", "200", pdf_path, prefijo],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return []
    paginas = sorted(glob.glob(glob.escape(prefijo) + "-*.png"))
    return paginas


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/archivo?"):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if "ruta" in query:
                raw_ruta = query["ruta"][0]

                # Manejar posibles casos de doble codificación o rutas anidadas
                if "ruta=" in raw_ruta:
                    try:
                        parsed_sub = urllib.parse.parse_qs(
                            urllib.parse.urlparse(raw_ruta).query
                        )
                        if "ruta" in parsed_sub:
                            raw_ruta = parsed_sub["ruta"][0]
                    except Exception:
                        pass

                file_path = urllib.parse.unquote(raw_ruta).lstrip("/")
                if file_path.startswith("./"):
                    file_path = file_path[2:]

                raiz = os.path.realpath(os.getcwd())
                candidato = os.path.realpath(os.path.join(raiz, file_path))
                if not (candidato == raiz or candidato.startswith(raiz + os.sep)):
                    self.send_error(403, "Ruta no permitida.")
                    return

                if os.path.isfile(candidato):
                    ext = os.path.splitext(candidato)[1].lower()
                    mime, inline_defecto = _MIME_POR_EXT.get(
                        ext, ("application/octet-stream", False)
                    )
                    forzar_descarga = query.get("download", ["0"])[0] == "1"
                    disposicion = (
                        "attachment"
                        if (forzar_descarga or not inline_defecto)
                        else "inline"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header(
                        "Content-Disposition",
                        f'{disposicion}; filename="{os.path.basename(candidato)}"',
                    )
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    with open(candidato, "rb") as f:
                        self.wfile.write(f.read())
                    return

            self.send_error(404, "Archivo no encontrado.")
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == "/ejecutar":
            length = int(self.headers.get("Content-Length", "0"))
            data = json.loads(self.rfile.read(length).decode("utf-8"))

            nombre_carpeta = sanitizar_nombre(data.get("archivo", "MiCancion"))
            nombre_archivo = nombre_carpeta + ".bzl"

            notas_simples = data.get("notas", "")
            if "|:" not in notas_simples:
                codigo_bzl = f"Main |:\n    (:) {{ {notas_simples} }}\n:|"
            else:
                codigo_bzl = notas_simples

            dir_propio = os.path.join("programas", nombre_carpeta)
            os.makedirs(dir_propio, exist_ok=True)

            ruta_bzl = os.path.join(dir_propio, nombre_archivo)
            base_path = os.path.splitext(ruta_bzl)[0]
            _limpiar_artefactos_previos(base_path)

            with open(ruta_bzl, "w", encoding="utf-8", newline="\n") as f:
                f.write(codigo_bzl)

            cmd = [sys.executable, "bazilio.py", ruta_bzl]
            res = subprocess.run(cmd, capture_output=True, text=True)

            pdf_path = base_path + ".pdf"
            mp3_path = base_path + ".mp3"
            wav_path = base_path + ".wav"
            mid_path = base_path + ".mid"
            midi_path = base_path + ".midi"
            ly_path = base_path + ".ly"

            salida_consola = "\n".join(
                parte for parte in (res.stdout.strip(), res.stderr.strip()) if parte
            ).strip()

            exito = res.returncode == 0
            paginas_png = _renderizar_paginas_png(pdf_path, base_path) if exito else []

            contenido_ly = ""
            notas_detalle = []
            if exito and os.path.exists(ly_path):
                with open(ly_path, encoding="utf-8") as f:
                    contenido_ly = f.read()
                notas_detalle = extraer_notas_de_ly(contenido_ly)

            if exito:
                if os.path.exists(pdf_path) or os.path.exists(mp3_path) or os.path.exists(ly_path):
                    msg = f"¡Procesado correctamente!\n{salida_consola}".strip()
                else:
                    msg = salida_consola or "Programa ejecutado correctamente (sin notas musicales)."
            else:
                msg = salida_consola or "Error al compilar el programa Bazilio."

            def url_si_existe(ruta):
                if exito and os.path.exists(ruta):
                    return f"/archivo?ruta={urllib.parse.quote(ruta)}"
                return None

            respuesta = {
                "exito": exito,
                "error": None if exito else msg,
                "resultado": msg,
                "archivo_bzl": nombre_archivo,
                "codigo_bzl": codigo_bzl,
                "ruta_bzl": f"/archivo?ruta={urllib.parse.quote(ruta_bzl)}",
                "ruta_ly": url_si_existe(ly_path),
                "ruta_mid": url_si_existe(mid_path),
                "ruta_midi": url_si_existe(midi_path),
                "ruta_wav": url_si_existe(wav_path),
                "ruta_mp3": url_si_existe(mp3_path),
                "ruta_pdf": url_si_existe(pdf_path),
                "paginas_png": [
                    f"/archivo?ruta={urllib.parse.quote(p)}" for p in paginas_png
                ],
                "contenido_ly": contenido_ly,
                "notas_detalle": notas_detalle,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            try:
                self.wfile.write(json.dumps(respuesta).encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError):
                pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Servidor Bazilio corriendo en el puerto {port}")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
