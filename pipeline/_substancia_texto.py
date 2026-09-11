# -*- coding: utf-8 -*-
"""
Divisao do campo SUBSTANCIAS_MEDICAMENTOS da ANVISA em componentes.

O campo mistura tres coisas e nao pode ser dividido ingenuamente:

  'cloreto de potassio, cloreto de sodio + associacoes, glicose'
      -> tres substancias; '+ associacoes' e ruido de excipiente

  'crodabase cr2 (alc. cetoestearilico+alc cetoest etoxilado+oleo mineral)'
      -> UMA substancia; o '+' esta dentro do parenteses e nao separa nada

  'lamivudina, lamivudina +zidovudina'
      -> duas substancias, com repeticao

Separador real medido no acervo: virgula (7.175 registros), depois
'/' (48), ' e ' (36) e '+' (36). Ver docs/auditoria_acervo.md.

Autoteste: python pipeline/_substancia_texto.py
"""
from __future__ import annotations

import re

# '+ associacoes' / 'e associacoes' marcam excipiente, nao principio ativo
_RUIDO = re.compile(
    r"\s*[+e]?\s*associa[cç][oõ]es\s*", re.I)
# conteudo entre parenteses e detalhamento de composicao: nao divide
_PARENTESES = re.compile(r"\([^)]*\)")
_SEPARADOR = re.compile(r"\s*(?:,|\+|/|\s+e\s+)\s*")
# sobras que nao sao substancia
_DESCARTAR = {"", "-", "associacoes", "associações", "outros", "diversos",
              "excipientes", "veiculo", "veículo", "q.s.p.", "qsp"}


def dividir(texto: str) -> list[str]:
    """Devolve a lista de componentes, na ordem, sem repetir."""
    if not texto:
        return []
    t = _PARENTESES.sub(" ", texto)     # remove antes de dividir
    t = _RUIDO.sub(" ", t)
    partes, vistos = [], set()
    for p in _SEPARADOR.split(t):
        p = re.sub(r"\s+", " ", p).strip(" .;-")
        if not p or p.lower() in _DESCARTAR or len(p) < 3:
            continue
        if p.lower() not in vistos:
            vistos.add(p.lower())
            partes.append(p)
    return partes


def _autoteste() -> int:
    casos = [
        ("cloreto de potássio, cloreto de sódio + associações, glicose",
         ["cloreto de potássio", "cloreto de sódio", "glicose"]),
        ("lamivudina, lamivudina +zidovudina",
         ["lamivudina", "zidovudina"]),
        ("cynara scolymus + associações",
         ["cynara scolymus"]),
        ("crodabase cr2 (álc. cetoestearílico+álc cetoest etoxilado+óleo mineral)",
         ["crodabase cr2"]),
        ("paracetamol", ["paracetamol"]),
        ("", []),
        ("associações", []),
        ("amoxicilina e clavulanato de potássio",
         ["amoxicilina", "clavulanato de potássio"]),
        ("sulfametoxazol / trimetoprima",
         ["sulfametoxazol", "trimetoprima"]),
    ]
    falhas = 0
    for entrada, esperado in casos:
        obtido = dividir(entrada)
        ok = obtido == esperado
        if not ok:
            falhas += 1
        print("  [%s] %-58s -> %s" % ("OK " if ok else "FALHA",
                                      (entrada[:56] or "(vazio)"), obtido))
        if not ok:
            print("        esperado: %s" % esperado)
    print("\nfalhas: %d" % falhas)
    return 1 if falhas else 0


if __name__ == "__main__":
    import sys
    print("AUTOTESTE — divisão do campo de substâncias da ANVISA")
    sys.exit(_autoteste())
