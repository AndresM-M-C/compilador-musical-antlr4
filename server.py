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
                raw_ruta = query['ruta'][0]
                
                # Manejar posibles casos de doble codificación o rutas anidadas
                if 'ruta=' in raw_ruta:
                    try:
                        parsed_sub = urllib.parse.parse_qs(urllib.parse.urlparse(raw_ruta).query)
                        if 'ruta' in parsed_sub:
                            raw_ruta = parsed_sub['ruta'][0]
                    except Exception:
                        pass
                
                file_path = urllib.parse.unquote(raw_ruta).lstrip('/')
                if file_path.startswith('./'):
                    file_path = file_path[2:]
                
                if not os.path.exists(file_path) and os.path.exists(os.path.join(os.getcwd(), file_path)):
                    file_path = os.path.join(os.getcwd(), file_path)

                if os.path.exists(file_path):
                    self.send_response(200)
                    if file_path.endswith('.mp3'):
                        self.send_header('Content-Type', 'audio/mpeg')
                        self.send_header('Content-Disposition', f'inline; filename="{os.path.basename(file_path)}"')
                    elif file_path.endswith('.pdf'):
                        self.send_header('Content-Type', 'application/pdf')
                        self.send_header('Content-Disposition', f'inline; filename="{os.path.basename(file_path)}"')
                    else:
                        self.send_header('Content-Type', 'application/octet-stream')
                    self.end_headers()
                    with open(file_path, 'rb') as f:
                        self.wfile.write(f.read())
                    return
            self.send_error(404, "Archivo no encontrado.")
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

            dir_propio = os.path.join("programas", nombre_carpeta)
            os.makedirs(dir_propio, exist_ok=True)

            ruta_bzl = os.path.join(dir_propio, nombre_archivo)
            with open(ruta_bzl, "w", encoding="utf-8", newline="\n") as f:
                f.write(codigo_bzl)

            cmd = ["python3", "bazilio.py", ruta_bzl]
            res = subprocess.run(cmd, capture_output=True, text=True)

            base_path = os.path.splitext(ruta_bzl)[0]
            pdf_path = base_path + ".pdf"
            mp3_path = base_path + ".mp3"

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            salida_consola = (res.stdout + "\n" + res.stderr).strip()
            
            if os.path.exists(pdf_path) or os.path.exists(mp3_path):
                msg = f"¡Procesado correctamente!\n{salida_consola}"
            else:
                msg = f"Error al compilar (revisa la sintaxis o LilyPond):\n{salida_consola or 'No se generaron archivos de salida.'}"
            
            respuesta = {
                'resultado': msg,
                'ruta_mp3': f"/archivo?ruta={urllib.parse.quote(mp3_path)}" if os.path.exists(mp3_path) else None,
                'ruta_pdf': f"/archivo?ruta={urllib.parse.quote(pdf_path)}" if os.path.exists(pdf_path) else None
            }
            
            try:
                self.wfile.write(json.dumps(respuesta).encode('utf-8'))
            except (BrokenPipeError, ConnectionResetError):
                pass

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"Servidor Bazilio corriendo en el puerto {port}")
    HTTPServer(('0.0.0.0', port), Handler).serve_forever()
