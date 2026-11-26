\version "2.24.4"
\score {
  {
    \set Staff.midiInstrument = #"violin"
    \tempo 4 = 108
    c'4 d'4 es'4 fis'4 g'4 as'4 bes'4 c''4
    \set Staff.midiInstrument = #"flute"
    \tempo 4 = 136
    cis''4 des''4 bes'4 gis'4 fis'4 es'4 cis'4 c'4
    ais,,,4 bes4 fis'4 cis'4
  }
  \layout { }
  \midi { }
}
