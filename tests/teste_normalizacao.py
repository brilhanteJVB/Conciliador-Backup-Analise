# -*- coding: utf-8 -*-
"""
Teste do normalizador (pipeline/normalizacao.py).

Todo join PT<->EN do sistema depende dele: se ele mudar de comportamento,
substancias deixam de casar em silencio e alertas somem sem erro nenhum.
Por isso os casos abaixo sao fixados aqui, e nao apenas conferidos a mao.

Uso: python tests/teste_normalizacao.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
from normalizacao import skeleton  # noqa: E402

falhas = []

# (entrada, esqueleto esperado, por que este caso importa)
CASOS = [
    # ponte PT <-> EN: o motivo de existir do normalizador
    ("dipirona monoidratada", "metamisol", "PT com sal <-> INN"),
    ("Metamizole sodium", "metamisol", "INN com sal <-> PT"),
    ("cloridrato de fluoxetina", "fluoksetin", "sal PT"),
    ("Fluoxetine hydrochloride", "fluoksetin", "sal EN"),
    ("varfarina sódica", "varfarin", "anticoagulante, alto risco"),
    ("Warfarin", "varfarin", ""),
    ("omeprazol", "omeprasol", ""),
    ("Omeprazole", "omeprasol", ""),
    ("levotiroxina sódica", "levotiroksin", "faixa terapeutica estreita"),
    ("Levothyroxine", "levotiroksin", ""),

    # 'acido' faz parte do nome e NAO pode ser removido
    ("ácido acetilsalicílico", "aspirin", "acido inicia o nome"),
    ("Acetylsalicylic acid", "aspirin", ""),
    ("ácido fólico", "akid folik", "acido inicia o nome"),

    # 'acido' qualificando sal ja removido DEVE sair (corrigido em 09/09/2026)
    ("maleato ácido de timolol", "timolol", "acido apos sal"),
    ("timolol", "timolol", ""),

    # hidratos superiores (corrigido em 09/09/2026)
    ("sulfato de morfina", "morfin", "opioide"),
    ("sulfato de morfina pentaidratado", "morfin", "hidrato superior"),

    # entradas degeneradas nao podem explodir
    ("", "", "vazio"),
    ("   ", "", "so espaco"),
]


def main() -> int:
    print("NORMALIZADOR — casos fixados")
    for entrada, esperado, nota in CASOS:
        obtido = skeleton(entrada)
        ok = obtido == esperado
        if not ok:
            falhas.append((entrada, esperado, obtido))
        print("  [%s] %-36s -> %-14s %s" %
              ("OK " if ok else "FALHA", repr(entrada)[:36], obtido, nota))

    print("\nSIMETRIA — PT e EN da mesma molécula têm de coincidir")
    pares = [("dipirona", "Metamizole"), ("varfarina", "Warfarin"),
             ("omeprazol", "Omeprazole"), ("sinvastatina", "Simvastatin"),
             ("amoxicilina", "Amoxicillin"), ("metformina", "Metformin"),
             ("ibuprofeno", "Ibuprofen"), ("paracetamol", "Paracetamol"),
             ("sertralina", "Sertraline"), ("clonazepam", "Clonazepam")]
    for pt, en in pares:
        a, b = skeleton(pt), skeleton(en)
        ok = a == b and a != ""
        if not ok:
            falhas.append((pt + " / " + en, a, b))
        print("  [%s] %-16s / %-16s -> %s / %s" %
              ("OK " if ok else "FALHA", pt, en, a, b))

    print("\nSEPARAÇÃO — moléculas diferentes não podem colidir")
    distintos = [("varfarina", "vareniclina"), ("clonazepam", "clobazam"),
                 ("losartana", "valsartana"), ("morfina", "codeína")]
    for a, b in distintos:
        ea, eb = skeleton(a), skeleton(b)
        ok = ea != eb
        if not ok:
            falhas.append((a + " vs " + b, "diferentes", ea))
        print("  [%s] %-14s vs %-14s -> %s / %s" %
              ("OK " if ok else "FALHA", a, b, ea, eb))

    print("\n" + "=" * 62)
    if falhas:
        print("FALHAS: %d" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("NORMALIZADOR OK — %d casos" % (len(CASOS) + 14))
    return 0


if __name__ == "__main__":
    sys.exit(main())
