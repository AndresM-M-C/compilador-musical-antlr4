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
            with open(ruta_bzl, "w", encoding="utf-8") as f:
                f.write(codigo_bzl)

            # Ejecuta bazilio.py
            cmd = ["python3", "bazilio.py", ruta_bzl]
            res = subprocess.run(cmd, capture_output=True, text=True)

            base_path = os.path.splitext(ruta_bzl)[0]
            pdf_path = base_path + ".pdf"
            mp3_path = base_path + ".mp3"

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            # Capturamos la salida completa o el error
            salida_consola = (res.stdout + "\n" + res.stderr).strip()
            
            if os.path.exists(pdf_path) or os.path.exists(mp3_path):
                msg = f"¡Procesado correctamente!\n{salida_consola}"
            else:
                msg = f"Error al generar la música/PDF:\n{salida_consola or 'Revisa la sintaxis de las notas.'}"
            
            respuesta = {
                'resultado': msg,
                'ruta_mp3': f"/archivo?ruta={urllib.parse.quote(mp3_path)}" if os.path.exists(mp3_path) else None,
                'ruta_pdf': f"/archivo?ruta={urllib.parse.quote(pdf_path)}" if os.path.exists(pdf_path) else None
            }
            self.wfile.write(json.dumps(respuesta).encode('utf-8'))
