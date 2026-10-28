import os
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import urllib.parse

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/archivo?'):
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if 'ruta' in query:
                file_path = query['ruta'][0]
                if os.path.exists(file_path):
                    self.send_response(200)
                    if file_path.endswith('.mp3'):
                        self.send_header('Content-Type', 'audio/mpeg')
                    elif file_path.endswith('.pdf'):
                        self.send_header('Content-Type', 'application/pdf')
                    else:
                        self.send_header('Content-Type', 'application/octet-stream')
                    self.end_headers()
                    with open(file_path, 'rb') as f:
                        self.wfile.write(f.read())
                    return
            self.send_error(404, "Archivo no encontrado")
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == '/ejecutar':
            length = int(self.headers['Content-Length'])
            data = json.loads(self.rfile.read(length).decode('utf-8'))
            
            nombre_archivo = data['archivo'].strip()
            if not nombre_archivo.endswith('.bzl'):
                nombre_archivo += '.bzl'
                
            notas_simples = data['notas']

            if "Main |:" not in notas_simples:
                codigo_bzl = f"Main |:\n    (:) {{ {notas_simples} }}\n:|"
            else:
                codigo_bzl = notas_simples

            nombre_carpeta = os.path.splitext(nombre_archivo)[0]

            dir_elegido = ""
            try:
                proceso = subprocess.run(
                    ["zenity", "--file-selection", "--directory", "--title=Selecciona la carpeta de destino para Bazilio"],
                    capture_output=True, text=True
                )
                if proceso.returncode == 0:
                    dir_elegido = proceso.stdout.strip()
            except Exception as e:
                print(f"No se pudo abrir el selector nativo: {e}")

            if not dir_elegido:
                dir_propio = os.path.join("programas", nombre_carpeta)
            else:
                dir_propio = os.path.join(dir_elegido, nombre_carpeta)

            os.makedirs(dir_propio, exist_ok=True)

            ruta_bzl = os.path.join(dir_propio, nombre_archivo)
            with open(ruta_bzl, "w", encoding="utf-8") as f:
                f.write(codigo_bzl)

            cmd = ["python3", "bazilio.py", ruta_bzl]
            res = subprocess.run(cmd, capture_output=True, text=True)

            base_path = os.path.splitext(ruta_bzl)[0]
            pdf_path = base_path + ".pdf"
            mp3_path = base_path + ".mp3"

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            salida = res.stderr.strip() if res.stderr else res.stdout.strip()
            msg = f"Guardado y procesado en: {dir_propio}/\n\n{salida or 'Procesado correctamente.'}"
            
            respuesta = {
                'resultado': msg,
                'ruta_mp3': mp3_path if os.path.exists(mp3_path) else None,
                'ruta_pdf': pdf_path if os.path.exists(pdf_path) else None
            }
            self.wfile.write(json.dumps(respuesta).encode('utf-8'))

print("Servidor Bazilio corriendo en http://localhost:8000")
HTTPServer(('localhost', 8000), Handler).serve_forever()