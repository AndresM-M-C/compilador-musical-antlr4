import os
import shutil
import struct
import subprocess
import sys
import threading
import unicodedata

from antlr4 import CommonTokenStream, FileStream
from antlr4.error.ErrorListener import ErrorListener

from BazilioLexer import BazilioLexer
from BazilioParser import BazilioParser
from BazilioVisitor import BazilioVisitor


class ErrorBazilio(Exception):
    """Error de sintaxis o de ejecución de un programa Bazilio."""


class _ListenerErrores(ErrorListener):
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        raise ErrorBazilio(
            f"Error de sintaxis en la línea {line}, columna {column}: {msg}")


def parsear(flujo):
    lexer = BazilioLexer(flujo)
    lexer.removeErrorListeners()
    lexer.addErrorListener(_ListenerErrores())
    parser = BazilioParser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(_ListenerErrores())
    return parser.programa()


def _div_c(a, b):
    """División entera con truncamiento hacia cero, como en C."""
    q = abs(a) // abs(b)
    return q if (a < 0) == (b < 0) else -q


NOTA_MIN, NOTA_MAX = 0, 51
TEMPO_MIN, TEMPO_MAX, TEMPO_DEFECTO = 20, 300, 120
INSTRUMENTO_DEFECTO = 0
_POSICION = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
_SEMITONOS_DIATONICOS = (0, 2, 4, 5, 7, 9, 11)
_BEMOL_LILYPOND = {
    "D": "des",
    "E": "es",
    "G": "ges",
    "A": "as",
    "B": "bes",
}

# Lista oficial de los 128 instrumentos General MIDI reconocidos por LilyPond (0..127).
INSTRUMENTOS_GM = (
    "acoustic grand", "bright acoustic", "electric grand", "honky-tonk",
    "electric piano 1", "electric piano 2", "harpsichord", "clav",
    "celesta", "glockenspiel", "music box", "vibraphone",
    "marimba", "xylophone", "tubular bells", "dulcimer",
    "drawbar organ", "percussive organ", "rock organ", "church organ",
    "reed organ", "accordion", "harmonica", "concertina",
    "acoustic guitar (nylon)", "acoustic guitar (steel)",
    "electric guitar (jazz)", "electric guitar (clean)",
    "electric guitar (muted)", "overdriven guitar",
    "distorted guitar", "guitar harmonics",
    "acoustic bass", "electric bass (finger)",
    "electric bass (pick)", "fretless bass",
    "slap bass 1", "slap bass 2", "synth bass 1", "synth bass 2",
    "violin", "viola", "cello", "contrabass",
    "tremolo strings", "pizzicato strings", "orchestral harp", "timpani",
    "string ensemble 1", "string ensemble 2",
    "synthstrings 1", "synthstrings 2",
    "choir aahs", "voice oohs", "synth voice", "orchestra hit",
    "trumpet", "trombone", "tuba", "muted trumpet",
    "french horn", "brass section", "synthbrass 1", "synthbrass 2",
    "soprano sax", "alto sax", "tenor sax", "baritone sax",
    "oboe", "english horn", "bassoon", "clarinet",
    "piccolo", "flute", "recorder", "pan flute",
    "blown bottle", "shakuhachi", "whistle", "ocarina",
    "lead 1 (square)", "lead 2 (sawtooth)", "lead 3 (calliope)", "lead 4 (chiff)",
    "lead 5 (charang)", "lead 6 (voice)", "lead 7 (fifths)", "lead 8 (bass+lead)",
    "pad 1 (new age)", "pad 2 (warm)", "pad 3 (polysynth)", "pad 4 (choir)",
    "pad 5 (bowed)", "pad 6 (metallic)", "pad 7 (halo)", "pad 8 (sweep)",
    "fx 1 (rain)", "fx 2 (soundtrack)", "fx 3 (crystal)", "fx 4 (atmosphere)",
    "fx 5 (brightness)", "fx 6 (goblins)", "fx 7 (echoes)", "fx 8 (sci-fi)",
    "sitar", "banjo", "shamisen", "koto",
    "kalimba", "bagpipe", "fiddle", "shanai",
    "tinkle bell", "agogo", "steel drums", "woodblock",
    "taiko drum", "melodic tom", "synth drum", "reverse cymbal",
    "guitar fret noise", "breath noise", "seashore", "bird tweet",
    "telephone ring", "helicopter", "applause", "gunshot",
)

_ALIAS_INSTRUMENTOS = {
    "piano": 0,
    "piano acustico": 0,
    "gran piano": 0,
    "piano brillante": 1,
    "piano electrico": 4,
    "clavecin": 6,
    "clavicordio": 7,
    "celesta": 8,
    "caja de musica": 10,
    "vibrafono": 11,
    "marimba": 12,
    "xilofono": 13,
    "campanas tubulares": 14,
    "organo": 19,
    "organo de iglesia": 19,
    "acordeon": 21,
    "armonica": 22,
    "guitarra": 24,
    "guitarra acustica": 24,
    "guitarra clasica": 24,
    "guitarra electrica": 27,
    "guitarra distorsionada": 30,
    "bajo": 32,
    "bajo acustico": 32,
    "bajo electrico": 33,
    "violin": 40,
    "viola": 41,
    "chelo": 42,
    "violonchelo": 42,
    "contrabajo": 43,
    "pizzicato": 45,
    "arpa": 46,
    "timbales": 47,
    "cuerdas": 48,
    "coro": 52,
    "trompeta": 56,
    "trombon": 57,
    "tuba": 58,
    "trompa": 60,
    "corno frances": 60,
    "metales": 61,
    "saxo": 65,
    "saxofon": 65,
    "saxofon alto": 65,
    "saxofon tenor": 66,
    "oboe": 68,
    "corno ingles": 69,
    "fagot": 70,
    "clarinete": 71,
    "flautin": 72,
    "flauta": 73,
    "flauta dulce": 74,
    "flauta de pan": 75,
    "silbato": 78,
    "ocarina": 79,
    "sitar": 104,
    "banjo": 105,
    "gaita": 109,
    "bateria": 118,
    "tambores": 118,
}

_MAPA_INSTRUMENTOS = {nombre: idx for idx, nombre in enumerate(INSTRUMENTOS_GM)}
_MAPA_INSTRUMENTOS.update(_ALIAS_INSTRUMENTOS)


def _normalizar_texto(texto):
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(sin_acentos.lower().split())


def resolver_instrumento(valor):
    """Convierte un nombre o entero 0..127 en su código de programa General MIDI."""
    if isinstance(valor, str):
        clave = _normalizar_texto(valor)
        if clave in _MAPA_INSTRUMENTOS:
            return _MAPA_INSTRUMENTOS[clave]
        raise ErrorBazilio("instrumento desconocido")
    if isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor <= 127:
        return valor
    raise ErrorBazilio("instrumento desconocido")


class NotaAlterada(float):
    """Representa una tecla negra (media tecla) preservando su grafía original."""

    def __new__(cls, valor, texto=""):
        obj = super().__new__(cls, valor)
        obj.texto = texto
        return obj


def _parsear_nota_texto(texto):
    letra = texto[0]
    resto = texto[1:]
    alteracion = ""
    if resto and resto[0] in ("#", "b"):
        alteracion = resto[0]
        resto = resto[1:]
    octava = int(resto) if resto else 4
    return letra, alteracion, octava


def valor_nota(texto):
    """'C4' -> 23, 'C#4'/'Db4' -> 23.5, 'C' -> 23, 'A0' -> 0, 'C8' -> 51."""
    letra, alteracion, octava = _parsear_nota_texto(texto)

    if (letra in ("E", "B") and alteracion == "#") or (
        letra in ("C", "F") and alteracion == "b"
    ):
        raise ErrorBazilio(f"la nota {texto} no existe en el piano.")

    if octava == 0:
        if letra not in ("A", "B") or (letra == "A" and alteracion == "b"):
            raise ErrorBazilio(f"la nota {texto} no existe en el piano.")
        base = 0 if letra == "A" else 1
    else:
        base = 2 + 7 * (octava - 1) + _POSICION[letra]

    delta = 0.5 if alteracion == "#" else (-0.5 if alteracion == "b" else 0)
    valor = base + delta

    if not NOTA_MIN <= valor <= NOTA_MAX:
        raise ErrorBazilio(f"la nota {texto} no existe en el piano.")

    if isinstance(valor, float):
        return NotaAlterada(valor, texto)
    return valor


class Interprete(BazilioVisitor):
    def __init__(self, entrada=None, salida=None):
        self.procedimientos = {}      # nombre -> (parámetros, bloque)
        self.marcos = []              # pila de variables
        self.partitura = []           # valores de notas tocadas
        self.instrumento = INSTRUMENTO_DEFECTO
        self.tempo = TEMPO_DEFECTO
        self.eventos = []             # secuencia de ("tempo"|"instrumento"|"nota", valor)
        self._entrada = entrada if entrada is not None else sys.stdin
        self._tokens_entrada = []
        self._salida = salida if salida is not None else print

    @property
    def _vars(self):
        return self.marcos[-1]

    def cargar(self, arbol):
        for proc in arbol.procedimiento():
            nombre = proc.PROC_ID().getText()
            params = [v.getText() for v in proc.VAR()]
            if nombre in self.procedimientos:
                raise ErrorBazilio(
                    f"El procedimiento {nombre} está definido más de una vez.")
            if len(set(params)) != len(params):
                raise ErrorBazilio(
                    f"El procedimiento {nombre} repite nombres de parámetros formales.")
            self.procedimientos[nombre] = (params, proc.bloque())

    def ejecutar(self, inicio="Main"):
        self._llamar(inicio, [])

    def _llamar(self, nombre, valores):
        if nombre not in self.procedimientos:
            raise ErrorBazilio(
                f"Se llamó al procedimiento {nombre}, que no está definido.")
        params, bloque = self.procedimientos[nombre]
        if len(params) != len(valores):
            raise ErrorBazilio(
                f"{nombre} espera {len(params)} parámetro(s) y recibió {len(valores)}.")
        self.marcos.append(dict(zip(params, valores)))
        try:
            self.visit(bloque)
        finally:
            self.marcos.pop()

    def visitBloque(self, ctx):
        for instruccion in ctx.instruccion():
            self.visit(instruccion)

    def visitAsignacion(self, ctx):
        valor = self.visit(ctx.expr())
        if isinstance(valor, list):
            valor = list(valor)            # copia la lista
        self._vars[ctx.VAR().getText()] = valor

    def visitLectura(self, ctx):
        self._vars[ctx.VAR().getText()] = self._leer_entero()

    def visitEscritura(self, ctx):
        partes = []
        for hijo in list(ctx.getChildren())[1:]:
            if hasattr(hijo, "symbol"):
                partes.append(hijo.getText()[1:-1])
            else:
                partes.append(self._formatear(self.visit(hijo)))
        self._salida(" ".join(partes))

    def visitReproduccion(self, ctx):
        valor = self.visit(ctx.expr())
        for nota in (valor if isinstance(valor, list) else [valor]):
            nota_a_lilypond(nota)
            self.partitura.append(nota)
            self.eventos.append(("nota", nota))

    def visitInstrumento(self, ctx):
        if ctx.TEXTO() is not None:
            arg = ctx.TEXTO().getText()[1:-1]
        else:
            arg = self._entero(self.visit(ctx.expr()))
        prog = resolver_instrumento(arg)
        self.instrumento = prog
        self.eventos.append(("instrumento", prog))

    def visitTempo(self, ctx):
        bpm = self._entero(self.visit(ctx.expr()))
        if not TEMPO_MIN <= bpm <= TEMPO_MAX:
            raise ErrorBazilio("debe estar entre 20 y 300")
        self.tempo = bpm
        self.eventos.append(("tempo", bpm))

    def visitInvocacion(self, ctx):
        valores = [self.visit(e) for e in ctx.expr()]
        self._llamar(ctx.PROC_ID().getText(), valores)

    def visitCondicional(self, ctx):
        bloques = ctx.bloque()
        if self._verdadero(self.visit(ctx.expr())):
            self.visit(bloques[0])
        elif len(bloques) > 1:
            self.visit(bloques[1])

    def visitIteracion(self, ctx):
        while self._verdadero(self.visit(ctx.expr())):
            self.visit(ctx.bloque())

    def visitEntero(self, ctx):
        return int(ctx.getText())

    def visitNota(self, ctx):
        return valor_nota(ctx.getText())

    def visitVariable(self, ctx):
        return self._vars.get(ctx.getText(), 0)

    def visitParentesis(self, ctx):
        return self.visit(ctx.expr())

    def visitLista(self, ctx):
        elementos = [self.visit(e) for e in ctx.expr()]
        if any(isinstance(e, list) for e in elementos):
            raise ErrorBazilio(
                "Las listas solo pueden contener enteros o notas.")
        return elementos

    def visitLongitud(self, ctx):
        valor = self.visit(ctx.expr())
        if not isinstance(valor, list):
            raise ErrorBazilio(
                "El operador # solo se puede aplicar a una lista.")
        return len(valor)

    def visitIndice(self, ctx):
        base = self.visit(ctx.expr(0))
        if not isinstance(base, list):
            raise ErrorBazilio(
                "Solo se puede consultar un índice en una lista.")
        i = self._entero(self.visit(ctx.expr(1)))
        self._comprobar_indice(ctx.expr(0).getText(), base, i)
        return base[i - 1]

    def visitAgregado(self, ctx):
        nombre = ctx.VAR().getText()
        lista = self._vars.get(nombre, 0)
        if not isinstance(lista, list):
            raise ErrorBazilio(
                f"{nombre} no es una lista: no se puede usar << con ella.")
        valor = self.visit(ctx.expr())
        if isinstance(valor, list):
            raise ErrorBazilio(
                "Las listas solo pueden contener enteros o notas.")
        lista.append(valor)

    def visitCorta(self, ctx):
        nombre = ctx.VAR().getText()
        lista = self._vars.get(nombre, 0)
        if not isinstance(lista, list):
            raise ErrorBazilio(
                f"{nombre} no es una lista: no se puede usar 8< con ella.")
        i = self._entero(self.visit(ctx.expr()))
        self._comprobar_indice(nombre, lista, i)
        del lista[i - 1]

    def visitMulDiv(self, ctx):
        a, b = self._operandos(ctx)
        op = ctx.op.text
        if op == "*":
            return a * b
        if b == 0:
            raise ErrorBazilio("División por cero.")
        q = _div_c(a, b)
        return q if op == "/" else a - b * q

    def visitSumaResta(self, ctx):
        a, b = self._operandos(ctx)
        return a + b if ctx.op.text == "+" else a - b

    def visitRelacional(self, ctx):
        a, b = self._operandos(ctx)
        return int({"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[ctx.op.text])

    def visitIgualdad(self, ctx):
        a, b = self.visit(ctx.expr(0)), self.visit(ctx.expr(1))
        return int((a == b) if ctx.op.text == "=" else (a != b))

    @staticmethod
    def _entero(valor):
        if isinstance(valor, list):
            raise ErrorBazilio(
                "Se esperaba un entero y se encontró una lista.")
        if isinstance(valor, float):
            raise ErrorBazilio("no se puede operar con una nota alterada")
        return valor

    def _operandos(self, ctx):
        izquierda = self._entero(self.visit(ctx.expr(0)))
        derecha = self._entero(self.visit(ctx.expr(1)))
        return izquierda, derecha

    @staticmethod
    def _verdadero(valor):
        if isinstance(valor, list):
            raise ErrorBazilio(
                "Una condición debe ser un entero (0 es falso, otro valor es verdadero).")
        if isinstance(valor, float):
            raise ErrorBazilio("no se puede operar con una nota alterada")
        return valor != 0

    @staticmethod
    def _formatear(valor):
        if isinstance(valor, list):
            return "[" + " ".join(str(x) for x in valor) + "]"
        return str(valor)

    @staticmethod
    def _comprobar_indice(nombre, lista, i):
        n = len(lista)
        if not 1 <= i <= n:
            raise ErrorBazilio(
                f"Índice {i} inexistente en {nombre} (la lista tiene {n} elemento(s); los índices van de 1 a {n}).")

    def _leer_entero(self):
        while not self._tokens_entrada:
            linea = self._entrada.readline()
            if linea == "":
                raise ErrorBazilio(
                    "Se esperaba un entero en la entrada, pero ya no hay más datos.")
            self._tokens_entrada = linea.split()
        token = self._tokens_entrada.pop(0)
        try:
            return int(token)
        except ValueError:
            raise ErrorBazilio(
                f"Se esperaba un entero en la entrada y se leyó «{token}».")


def _octava_marcas(octava):
    return "'" * (octava - 3) if octava > 3 else "," * (3 - octava)


def _descomponer_nota(valor):
    """Valida y devuelve (octava, paso_diatonico, semitono_extra, nombre_lilypond)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorBazilio(
            f"Se intentó tocar el valor {valor}, que no es una nota válida.")
    if not NOTA_MIN <= valor <= NOTA_MAX:
        raise ErrorBazilio(
            f"Se intentó tocar el valor {valor}, fuera del rango del piano (0 a 51).")

    if isinstance(valor, NotaAlterada) and valor.texto:
        letra, alteracion, octava = _parsear_nota_texto(valor.texto)
        paso = _POSICION[letra]
        extra = 1 if alteracion == "#" else -1
        nombre = (
            f"{letra.lower()}is"
            if alteracion == "#"
            else _BEMOL_LILYPOND[letra]
        )
        return octava, paso, extra, nombre

    doble = round(valor * 2)
    if abs(valor * 2 - doble) > 1e-9:
        raise ErrorBazilio(
            f"Se intentó tocar el valor {valor}, que no corresponde a ninguna tecla del piano.")

    if doble % 2 == 0:
        ent = doble // 2
        if ent < 2:
            return 0, 5 + ent, 0, ("a", "b")[ent]
        k = ent - 2
        octava, paso = 1 + k // 7, k % 7
        return octava, paso, 0, "cdefgab"[paso]

    base_int = (doble - 1) // 2
    if base_int == 0:
        return 0, 5, 1, "ais"
    if base_int == 1:
        raise ErrorBazilio(
            f"la nota con valor {valor} no existe en el piano.")
    k = base_int - 2
    octava, paso = 1 + k // 7, k % 7
    alteradas = {0: "cis", 1: "dis", 3: "fis", 4: "gis", 5: "bes"}
    if paso not in alteradas:
        raise ErrorBazilio(
            f"la nota con valor {valor} no existe en el piano.")
    return octava, paso, 1, alteradas[paso]


def nota_a_lilypond(valor):
    octava, _, _, nombre = _descomponer_nota(valor)
    return f"{nombre}{_octava_marcas(octava)}4"


def nota_a_midi(valor):
    octava, paso, extra, _ = _descomponer_nota(valor)
    return 12 * (octava + 1) + _SEMITONOS_DIATONICOS[paso] + extra


def _vlq(n):
    """Codifica un entero no negativo en Variable Length Quantity para MIDI."""
    bytes_out = [n & 0x7F]
    n >>= 7
    while n:
        bytes_out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(bytes_out))


def _eventos_efectivos(partitura, tempo=TEMPO_DEFECTO, instrumento=INSTRUMENTO_DEFECTO, eventos=None):
    if eventos is not None:
        return eventos
    return [("tempo", tempo), ("instrumento", instrumento)] + [
        ("nota", v) for v in partitura
    ]


def generar_midi(partitura, ruta_mid, tempo=TEMPO_DEFECTO, instrumento=INSTRUMENTO_DEFECTO, eventos=None):
    """Genera un archivo MIDI estándar (.mid) con las notas, tempo e instrumento."""
    tpqn = 480
    lista_eventos = _eventos_efectivos(partitura, tempo, instrumento, eventos)
    pista = bytearray()
    tiene_tempo = False
    tiene_inst = False

    # Si no hay configuración explícita antes de la primera nota, usa los valores indicados.
    for tipo, _ in lista_eventos:
        if tipo == "tempo":
            tiene_tempo = True
        elif tipo == "instrumento":
            tiene_inst = True
        elif tipo == "nota":
            break

    if not tiene_tempo:
        us_per_beat = round(60_000_000 / tempo)
        pista += b"\x00\xFF\x51\x03" + us_per_beat.to_bytes(3, "big")
    if not tiene_inst:
        pista += b"\x00\xC0" + bytes([instrumento])

    for tipo, val in lista_eventos:
        if tipo == "tempo":
            us_per_beat = round(60_000_000 / val)
            pista += b"\x00\xFF\x51\x03" + us_per_beat.to_bytes(3, "big")
        elif tipo == "instrumento":
            pista += b"\x00\xC0" + bytes([val])
        elif tipo == "nota":
            midi_note = nota_a_midi(val)
            pista += b"\x00\x90" + bytes([midi_note, 96])
            pista += _vlq(tpqn) + b"\x80" + bytes([midi_note, 0])

    pista += b"\x00\xFF\x2F\x00"
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, tpqn)
    track_hdr = b"MTrk" + struct.pack(">I", len(pista))

    with open(ruta_mid, "wb") as f:
        f.write(header + track_hdr + pista)
    return ruta_mid


def texto_lilypond(partitura, tempo=TEMPO_DEFECTO, instrumento=INSTRUMENTO_DEFECTO, eventos=None):
    lista_eventos = _eventos_efectivos(partitura, tempo, instrumento, eventos)
    lineas_cuerpo = []
    notas_linea = []
    tempo_inicial_emitido = False
    inst_inicial_emitido = False
    primera_nota_vista = False

    def vaciar_notas():
        if notas_linea:
            for i in range(0, len(notas_linea), 8):
                lineas_cuerpo.append("    " + " ".join(notas_linea[i:i + 8]))
            notas_linea.clear()

    for tipo, val in lista_eventos:
        if tipo == "tempo":
            vaciar_notas()
            lineas_cuerpo.append(f"    \\tempo 4 = {val}")
            if not primera_nota_vista:
                tempo_inicial_emitido = True
        elif tipo == "instrumento":
            vaciar_notas()
            nombre_gm = INSTRUMENTOS_GM[val]
            lineas_cuerpo.append(f'    \\set Staff.midiInstrument = #"{nombre_gm}"')
            if not primera_nota_vista:
                inst_inicial_emitido = True
        elif tipo == "nota":
            if not primera_nota_vista:
                primera_nota_vista = True
                cabecera = []
                if not tempo_inicial_emitido:
                    cabecera.append(f"    \\tempo 4 = {tempo}")
                if not inst_inicial_emitido:
                    nombre_gm = INSTRUMENTOS_GM[instrumento]
                    cabecera.append(f'    \\set Staff.midiInstrument = #"{nombre_gm}"')
                if cabecera:
                    lineas_cuerpo = cabecera + lineas_cuerpo
            notas_linea.append(nota_a_lilypond(val))

    vaciar_notas()
    cuerpo = "\n".join(lineas_cuerpo)
    return (
        '\\version "2.24.4"\n'
        "\\score {\n"
        "  {\n"
        f"{cuerpo}\n"
        "  }\n"
        "  \\layout { }\n"
        "  \\midi { }\n"
        "}\n"
    )


def generar_salida(partitura, base, solo_ly=False, aviso=print,
                   tempo=TEMPO_DEFECTO, instrumento=INSTRUMENTO_DEFECTO, eventos=None):
    ruta_ly = base + ".ly"
    contenido_ly = texto_lilypond(
        partitura, tempo=tempo, instrumento=instrumento, eventos=eventos
    )

    with open(ruta_ly, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenido_ly)
        f.flush()
        os.fsync(f.fileno())

    generados = [ruta_ly]
    if solo_ly:
        return generados

    dir_trabajo = os.path.dirname(ruta_ly) or "."
    nombre_ly = os.path.basename(ruta_ly)
    nombre_base = os.path.splitext(nombre_ly)[0]

    def correr(cmd, descripcion, cwd=None):
        if shutil.which(cmd[0]) is None:
            aviso(f"Aviso: no se encontró «{cmd[0]}», no se generó {descripcion}.")
            return False
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        if r.returncode != 0:
            detalle = r.stderr.strip()
            aviso(f"Aviso: falló {cmd[0]} al generar {descripcion}:\n{detalle}")
            return False
        return True

    sf2_candidatos = [
        "/usr/share/sounds/sf2/FluidR3_GM.sf2",
        "/usr/share/soundfonts/FluidR3_GM.sf2",
    ]
    sf2_path = next((p for p in sf2_candidatos if os.path.exists(p)), sf2_candidatos[0])

    wav_file = nombre_base + ".wav"
    midi_file = nombre_base + ".midi"
    mid_file = nombre_base + ".mid"
    mp3_file = nombre_base + ".mp3"

    ruta_mid = os.path.join(dir_trabajo, mid_file)
    ruta_midi = os.path.join(dir_trabajo, midi_file)

    if correr(["lilypond", "-o", nombre_base, nombre_ly], "el PDF y el MIDI", cwd=dir_trabajo):
        generados += [
            os.path.join(dir_trabajo, nombre_base + ".pdf"),
            ruta_midi,
        ]
        if os.path.exists(ruta_midi):
            shutil.copyfile(ruta_midi, ruta_mid)
            generados.append(ruta_mid)
        if correr(["fluidsynth", "-ni", "-F", wav_file, sf2_path, midi_file], "el WAV", cwd=dir_trabajo):
            generados.append(os.path.join(dir_trabajo, wav_file))
            if correr(["ffmpeg", "-y", "-loglevel", "error", "-i", wav_file, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_file], "el MP3", cwd=dir_trabajo):
                generados.append(os.path.join(dir_trabajo, mp3_file))
    else:
        generar_midi(partitura, ruta_mid, tempo=tempo, instrumento=instrumento, eventos=eventos)
        generados.append(ruta_mid)

    return generados


def principal(argv):
    solo_ly = "--solo-ly" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    if not args:
        print(
            "Uso: python3 bazilio.py programa.bzl [Procedimiento] [--solo-ly]")
        return 2
    ruta = args[0]
    inicio = args[1] if len(args) > 1 else "Main"
    try:
        arbol = parsear(FileStream(ruta, encoding="utf-8"))
        interprete = Interprete()
        interprete.cargar(arbol)
        interprete.ejecutar(inicio)
        if interprete.partitura:
            base = os.path.splitext(ruta)[0]
            archivos = generar_salida(
                interprete.partitura,
                base,
                solo_ly=solo_ly,
                tempo=interprete.tempo,
                instrumento=interprete.instrumento,
                eventos=interprete.eventos,
            )
            nombres = ", ".join(os.path.basename(a) for a in archivos)
            print("Archivos generados: " + nombres, file=sys.stderr)
    except ErrorBazilio as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    sys.setrecursionlimit(200000)
    threading.stack_size(512 * 1024 * 1024)
    resultado = []
    hilo = threading.Thread(
        target=lambda: resultado.append(principal(sys.argv)))
    hilo.start()
    hilo.join()
    sys.exit(resultado[0] if resultado else 1)
