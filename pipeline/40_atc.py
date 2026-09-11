# -*- coding: utf-8 -*-
"""
Carga da classificacao ATC (WHO) e vinculo com as substancias.

O ATC sustenta tres coisas do motor: duplicidade terapeutica (mesmo codigo
de 5o nivel), alternativa por classe e agrupamento no relatorio.

TRADUCAO: os nomes de classe vem em ingles. Sao traduzidos por molde
(pipeline/traducao_atc.py) com regra tudo-ou-nada; o que nao e coberto fica
em ingles e marcado traduzido=0, para a interface poder dizer que aquele
nome nao foi traduzido em vez de exibir meia frase.

NIVEL 5 e a propria substancia: nesse caso o nome em portugues vem da DCB,
que ja e a nomenclatura oficial brasileira.

Uso: python pipeline/40_atc.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (abrir_carga, campo, conectar, fechar_carga,  # noqa: E402
                    id_fonte, ler_csv, registrar_evidencia, resumo)
from normalizacao import skeleton  # noqa: E402
from traducao_atc import traduzir  # noqa: E402

ARQ = "fontes_novas/05_atc_classes/WHO_ATC-DDD_2026-04-25.csv"

# comprimento do codigo -> nivel hierarquico
NIVEL = {1: 1, 3: 2, 4: 3, 5: 4, 7: 5}


def nivel_de(codigo: str) -> int:
    return NIVEL.get(len(codigo), 0)


def pai_de(codigo: str):
    return {2: codigo[:1], 3: codigo[:3], 4: codigo[:4],
            5: codigo[:5]}.get(nivel_de(codigo))


def main() -> int:
    con = conectar()
    fonte = "WHO - ATC/DDD"
    fid = id_fonte(con, fonte)
    carga = abrir_carga(con, fonte, "40_atc.py", ARQ, versao="2026-04-25")

    # indice esqueleto -> substancia (para o nivel 5 e para o vinculo)
    indice = {}
    for sid, chave in con.execute("SELECT id, chave_normalizada FROM substancia"):
        indice.setdefault(chave, sid)
    for sid, chave in con.execute(
            "SELECT substancia_id, chave_normalizada FROM substancia_sinonimo"):
        indice.setdefault(chave, sid)

    # 1a passada: coletar, para poder inserir na ordem hierarquica (FK do pai)
    registros = []
    lidos = 0
    for idx, l in ler_csv(ARQ):
        lidos += 1
        codigo = campo(idx, l, "atc_code")
        nome_en = campo(idx, l, "atc_name")
        if not codigo or not nome_en or nivel_de(codigo) == 0:
            continue
        registros.append((codigo, nome_en))

    por_nivel = Counter()
    traduzidos = Counter()
    inseridos = 0
    # ordena por nivel: o pai precisa existir antes do filho
    for codigo, nome_en in sorted(registros, key=lambda r: (nivel_de(r[0]), r[0])):
        n = nivel_de(codigo)
        por_nivel[n] += 1

        if n == 5:
            # nivel 5 e a substancia: nome em portugues vem da DCB
            sid = indice.get(skeleton(nome_en))
            if sid:
                nome_pt = con.execute(
                    "SELECT nome_dcb FROM substancia WHERE id=?", (sid,)
                ).fetchone()[0]
                ok = True
            else:
                nome_pt, ok = nome_en, False
        else:
            nome_pt, ok = traduzir(nome_en)
        if ok:
            traduzidos[n] += 1

        pai = pai_de(codigo)
        if pai and not con.execute(
                "SELECT 1 FROM classe_atc WHERE codigo=?", (pai,)).fetchone():
            pai = None      # a WHO nem sempre publica todos os niveis

        r = con.execute(
            "INSERT OR IGNORE INTO classe_atc (codigo,nome_pt,nome_en,nivel,"
            "codigo_pai) VALUES (?,?,?,?,?)", (codigo, nome_pt, nome_en, n, pai))
        if r.rowcount:
            inseridos += 1

    con.commit()

    # 2) vincular substancia -> codigo ATC de 5o nivel
    vinculadas = 0
    for codigo, nome_en, in con.execute(
            "SELECT codigo, nome_en FROM classe_atc WHERE nivel=5"):
        sid = indice.get(skeleton(nome_en))
        if not sid:
            continue
        r = con.execute(
            "UPDATE substancia SET atc_codigo=? WHERE id=? AND atc_codigo IS NULL",
            (codigo, sid))
        if r.rowcount:
            vinculadas += 1
            registrar_evidencia(con, "substancia", sid, fid, carga, ARQ,
                                "RESPALDADA", "CARGA_DIRETA")
    con.commit()
    fechar_carga(con, carga, lidos, inseridos, lidos - inseridos,
                 "ignorados = codigos repetidos ou fora dos 5 niveis")

    total_subst = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
    resumo("CLASSIFICACAO ATC", [
        ("linhas WHO lidas", lidos),
        ("classes inseridas", inseridos),
        ("substancias com codigo ATC", "%d de %d (%.1f%%)" %
         (vinculadas, total_subst, 100 * vinculadas / max(1, total_subst))),
    ])
    print("\n  nivel   classes   nome em português   cobertura")
    for n in range(1, 6):
        if por_nivel[n]:
            print("    %d %10d %14d %11.1f%%" %
                  (n, por_nivel[n], traduzidos[n],
                   100 * traduzidos[n] / por_nivel[n]))
    nao_trad = con.execute(
        "SELECT COUNT(*) FROM classe_atc WHERE nome_pt = nome_en").fetchone()[0]
    print("\n  %d classes ficaram em inglês (não cobertas pelo glossário)."
          % nao_trad)
    print("  Ficam declaradas como não traduzidas, nunca traduzidas pela metade.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
