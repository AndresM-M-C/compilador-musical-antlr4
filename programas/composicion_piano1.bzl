### Composición de prueba para la Actividad 1: El piano completo ###
### Incluye teclas negras (# y b), instrumento distinto al piano y cambio de tempo ###

Main |:
    ~~~ Inicio con violín y tempo moderado ~~~
    instrumento "violin"
    tempo 108

    melodia <- { C4 D4 Eb4 F#4 G4 Ab4 Bb4 C5 }
    (:) melodia

    ~~~ Segundo motivo con flauta, teclas negras en otra octava y tempo más rápido ~~~
    instrumento "flauta"
    tempo 136

    (:) { C#5 Db5 Bb4 G#4 F#4 Eb4 C#4 C4 }
    (:) { A#0 Bb3 F#4 C#4 }
:|
