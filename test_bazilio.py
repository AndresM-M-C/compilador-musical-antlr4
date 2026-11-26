import os
import struct
import subprocess
import sys
import tempfile
import unittest

from antlr4 import InputStream

import analizar
import bazilio


def _ejecutar(codigo, entrada=""):
    arbol = bazilio.parsear(InputStream(codigo))
    salidas = []
    interp = bazilio.Interprete(
        entrada=iter([]),
        salida=salidas.append,
    )
    if entrada:
        import io
        interp._entrada = io.StringIO(entrada)
    interp.cargar(arbol)
    interp.ejecutar()
    return interp, salidas


def _extraer_notas_midi(ruta_mid):
    """Extrae eventos Note On (vel > 0), Program Change y Tempo de un archivo MIDI."""
    with open(ruta_mid, "rb") as f:
        data = f.read()
    assert data[:4] == b"MThd"
    pos = 8 + int.from_bytes(data[4:8], "big")
    notas = []
    programas = []
    tempos = []

    def leer_vlq(buf, idx):
        val = 0
        while True:
            b = buf[idx]
            idx += 1
            val = (val << 7) | (b & 0x7F)
            if not (b & 0x80):
                return val, idx

    while pos < len(data):
        assert data[pos:pos + 4] == b"MTrk"
        ln = int.from_bytes(data[pos + 4:pos + 8], "big")
        trk = data[pos + 8:pos + 8 + ln]
        pos += 8 + ln
        i = 0
        running = None
        while i < len(trk):
            _, i = leer_vlq(trk, i)
            status = trk[i]
            if status == 0xFF:
                meta_type = trk[i + 1]
                meta_len, i = leer_vlq(trk, i + 2)
                payload = trk[i:i + meta_len]
                i += meta_len
                if meta_type == 0x51 and meta_len == 3:
                    us = int.from_bytes(payload, "big")
                    tempos.append(round(60_000_000 / us))
            elif status in (0xF0, 0xF7):
                syx_len, i = leer_vlq(trk, i + 1)
                i += syx_len
            else:
                if status & 0x80:
                    running = status
                    i += 1
                else:
                    status = running
                cmd = status & 0xF0
                if cmd in (0xC0, 0xD0):
                    d1 = trk[i]
                    i += 1
                    if cmd == 0xC0:
                        programas.append(d1)
                else:
                    d1, d2 = trk[i], trk[i + 1]
                    i += 2
                    if cmd == 0x90 and d2 > 0:
                        notas.append(d1)
    return notas, programas, tempos


class TestGramaticaYLexer(unittest.TestCase):
    def test_tokens_instrumento_tempo_y_notas(self):
        codigo = 'Main |:\n  instrumento "violin"\n  tempo 95\n  (:) { Bb C#4 }\n:|\n'
        tokens = analizar.listar_tokens(InputStream(codigo))
        tipos = [t for t, _ in tokens]
        textos = [tx for _, tx in tokens]
        self.assertIn("INSTRUMENTO", tipos)
        self.assertIn("TEMPO", tipos)
        self.assertEqual(textos.count("Bb") + textos.count("C#4"), 2)
        idx_bb = textos.index("Bb")
        self.assertEqual(tipos[idx_bb], "NOTA")
        idx_cs = textos.index("C#4")
        self.assertEqual(tipos[idx_cs], "NOTA")


class TestPianoCompleto(unittest.TestCase):
    def test_valores_teclas_blancas_y_negras(self):
        self.assertEqual(bazilio.valor_nota("A0"), 0)
        self.assertEqual(bazilio.valor_nota("A#0"), 0.5)
        self.assertEqual(bazilio.valor_nota("Bb0"), 0.5)
        self.assertEqual(bazilio.valor_nota("B0"), 1)
        self.assertEqual(bazilio.valor_nota("C4"), 23)
        self.assertEqual(bazilio.valor_nota("C"), 23)
        self.assertEqual(bazilio.valor_nota("C#4"), 23.5)
        self.assertEqual(bazilio.valor_nota("Db4"), 23.5)
        self.assertEqual(bazilio.valor_nota("F#4"), 26.5)
        self.assertEqual(bazilio.valor_nota("Bb3"), 21.5)
        self.assertEqual(bazilio.valor_nota("C8"), 51)

    def test_teclas_inexistentes_rechazadas(self):
        invalidas = ["E#", "E#4", "B#", "B#3", "Cb", "Cb4", "Fb", "Fb5", "C#8", "D8", "Ab0", "G0", "C0"]
        for nota in invalidas:
            with self.subTest(nota=nota):
                with self.assertRaises(bazilio.ErrorBazilio) as ctx:
                    bazilio.valor_nota(nota)
                self.assertIn("no existe en el piano", str(ctx.exception))

    def test_error_operar_con_nota_alterada(self):
        casos = [
            "Main |:\n  x <- C#4 + 1\n:|\n",
            "Main |:\n  x <- 1 + Bb3\n:|\n",
            "Main |:\n  x <- F#4 * 2\n:|\n",
            "Main |:\n  x <- Db4 < D4\n:|\n",
            "Main |:\n  l <- { C4 D4 }\n  x <- l[C#4]\n:|\n",
        ]
        for codigo in casos:
            with self.subTest(codigo=codigo):
                with self.assertRaises(bazilio.ErrorBazilio) as ctx:
                    _ejecutar(codigo)
                self.assertIn("no se puede operar con una nota alterada", str(ctx.exception))

    def test_igualdad_enarmonicos(self):
        _, salidas = _ejecutar("Main |:\n  <w> (C#4 = Db4)\n  <w> (Bb3 = A#3)\n:|\n")
        self.assertEqual(salidas, ["1", "1"])

    def test_instrumento_texto_y_numero(self):
        interp, _ = _ejecutar('Main |:\n  instrumento "violin"\n  (:) C4\n:|\n')
        self.assertEqual(interp.instrumento, 40)

        interp2, _ = _ejecutar("Main |:\n  instrumento 73\n  (:) C4\n:|\n")
        self.assertEqual(interp2.instrumento, 73)

        interp_def, _ = _ejecutar("Main |:\n  (:) C4\n:|\n")
        self.assertEqual(interp_def.instrumento, 0)

    def test_instrumento_desconocido(self):
        for codigo in [
            'Main |:\n  instrumento "vuvuzela"\n:|\n',
            "Main |:\n  instrumento 128\n:|\n",
            "Main |:\n  instrumento (0 - 1)\n:|\n",
        ]:
            with self.subTest(codigo=codigo):
                with self.assertRaises(bazilio.ErrorBazilio) as ctx:
                    _ejecutar(codigo)
                self.assertIn("instrumento desconocido", str(ctx.exception))

    def test_tempo_valido_y_fuera_de_rango(self):
        interp, _ = _ejecutar("Main |:\n  tempo 20\n  (:) C4\n  tempo 300\n  (:) D4\n:|\n")
        self.assertEqual(interp.tempo, 300)

        interp_def, _ = _ejecutar("Main |:\n  (:) C4\n:|\n")
        self.assertEqual(interp_def.tempo, 120)

        for bpm in ["19", "301", "0", "(0 - 5)"]:
            with self.subTest(bpm=bpm):
                with self.assertRaises(bazilio.ErrorBazilio) as ctx:
                    _ejecutar(f"Main |:\n  tempo {bpm}\n:|\n")
                self.assertIn("debe estar entre 20 y 300", str(ctx.exception))


class TestMidiYLilyPond(unittest.TestCase):
    def test_mapeo_midi_y_lilypond_teclas_negras(self):
        self.assertEqual(bazilio.nota_a_midi(bazilio.valor_nota("C#4")), 61)
        self.assertEqual(bazilio.nota_a_midi(bazilio.valor_nota("Db4")), 61)
        self.assertEqual(bazilio.nota_a_midi(bazilio.valor_nota("F#4")), 66)
        self.assertEqual(bazilio.nota_a_midi(bazilio.valor_nota("Bb3")), 58)
        self.assertEqual(bazilio.nota_a_midi(bazilio.valor_nota("A#0")), 22)

        self.assertEqual(bazilio.nota_a_lilypond(bazilio.valor_nota("C#4")), "cis'4")
        self.assertEqual(bazilio.nota_a_lilypond(bazilio.valor_nota("Db4")), "des'4")
        self.assertEqual(bazilio.nota_a_lilypond(bazilio.valor_nota("F#4")), "fis'4")
        self.assertEqual(bazilio.nota_a_lilypond(bazilio.valor_nota("Bb3")), "bes4")
        self.assertEqual(bazilio.nota_a_lilypond(bazilio.valor_nota("A#0")), "ais,,,4")

    def test_generacion_ly_y_mid_con_lilypond(self):
        codigo = (
            'Main |:\n'
            '  instrumento "violin"\n'
            '  tempo 96\n'
            '  (:) { C#4 Db4 F#4 Bb3 A#0 }\n'
            ':|\n'
        )
        interp, _ = _ejecutar(codigo)
        with tempfile.TemporaryDirectory() as tmpdir:
            base = os.path.join(tmpdir, "prueba")
            archivos = bazilio.generar_salida(
                interp.partitura,
                base,
                tempo=interp.tempo,
                instrumento=interp.instrumento,
                eventos=interp.eventos,
            )
            ruta_ly = base + ".ly"
            ruta_mid = base + ".mid"
            self.assertTrue(os.path.exists(ruta_ly))
            self.assertTrue(os.path.exists(ruta_mid))
            self.assertIn(ruta_mid, archivos)

            with open(ruta_ly, encoding="utf-8") as f:
                ly = f.read()
            self.assertIn("\\tempo 4 = 96", ly)
            self.assertIn('\\set Staff.midiInstrument = #"violin"', ly)
            self.assertIn("cis'4 des'4 fis'4 bes4 ais,,,4", ly)

            notas_midi, programas, tempos = _extraer_notas_midi(ruta_mid)
            self.assertEqual(notas_midi, [61, 61, 66, 58, 22])
            self.assertIn(40, programas)
            self.assertIn(96, tempos)

    def test_cli_error_operacion_nota_alterada(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ruta = os.path.join(tmpdir, "err.bzl")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("Main |:\n  x <- C#4 + 1\n:|\n")
            res = subprocess.run(
                [sys.executable, "bazilio.py", ruta],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Error: no se puede operar con una nota alterada", res.stderr)

    def test_generar_midi_puro_y_composicion_propia(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ruta_mid = os.path.join(tmpdir, "directo.mid")
            bazilio.generar_midi(
                [bazilio.valor_nota("C#4"), bazilio.valor_nota("F#4"),
                 bazilio.valor_nota("Bb3"), bazilio.valor_nota("A#0")],
                ruta_mid,
                tempo=88,
                instrumento=40,
            )
            notas, programas, tempos = _extraer_notas_midi(ruta_mid)
            self.assertEqual(notas, [61, 66, 58, 22])
            self.assertEqual(programas, [40])
            self.assertEqual(tempos, [88])

        comp_mid = os.path.join(os.path.dirname(os.path.abspath(__file__)), "programas", "composicion_piano1.mid")
        comp_ly = os.path.join(os.path.dirname(os.path.abspath(__file__)), "programas", "composicion_piano1.ly")
        self.assertTrue(os.path.exists(comp_mid))
        self.assertTrue(os.path.exists(comp_ly))
        notas, programas, tempos = _extraer_notas_midi(comp_mid)
        self.assertIn(40, programas)
        self.assertIn(73, programas)
        self.assertEqual(programas[-1], 73)
        self.assertEqual(tempos, [108, 136])
        self.assertEqual(notas[-4:], [22, 58, 66, 61])


if __name__ == "__main__":
    unittest.main()
