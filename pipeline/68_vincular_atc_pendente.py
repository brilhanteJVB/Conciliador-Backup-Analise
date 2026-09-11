# -*- coding: utf-8 -*-
"""
Segunda passada do vinculo substancia -> codigo ATC.

POR QUE ESTE PASSO EXISTE
-------------------------
`40_atc.py` casa a substancia com o codigo ATC de 5o nivel pelo esqueleto
fonetico do nome em ingles, usando um indice montado a partir de
`substancia.chave_normalizada` e de `substancia_sinonimo`. Acontece que os
sinonimos **INN** — os nomes em ingles que casaram 1:1 com uma substancia
brasileira — sao criados depois, por `60_interacoes_substancia.py`.

Consequencia: na PRIMEIRA passada do pipeline, 40 nao enxerga os INN e perde
alguns vinculos; numa segunda execucao ele os enxerga e vincula mais. O
resultado do pipeline dependia de quantas vezes ele tinha rodado — 1.153
substancias com ATC numa passada, 1.159 em duas. Defeito da mesma familia de
D-045, encontrado pela V1 da Fase 8 quando a AUC gravada de um modelo deixou
de bater com a recalculada.

O QUE ESTE PASSO NAO FAZ
------------------------
Nao reordena o pipeline. Mover `40_atc.py` para depois de `60` resolveria o
vinculo e quebraria outra coisa: o nivel 5 do ATC pega o nome em portugues da
DCB, e `60` ja usa classe ATC para nada — mas a traducao de classes e o
`nome_pt` dependem de 40 ter rodado antes. Uma segunda passada explicita,
numerada e idempotente e mais barata de entender do que uma reordenacao.

Nao inventa vinculo: usa exatamente o mesmo criterio de 40 (esqueleto do nome
em ingles do nivel 5), e so escreve onde `atc_codigo IS NULL`.

Uso: python pipeline/68_vincular_atc_pendente.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (abrir_carga, conectar, fechar_carga, id_fonte,  # noqa: E402
                    registrar_evidencia, resumo)
from normalizacao import skeleton  # noqa: E402

ARQ = "fontes_novas/05_atc_classes/WHO_ATC-DDD_2026-04-25.csv"
FONTE = "WHO - ATC/DDD"


def main() -> int:
    con = conectar()
    fid = id_fonte(con, FONTE)
    carga = abrir_carga(con, FONTE, "68_vincular_atc_pendente.py", ARQ,
                        versao="2026-04-25")

    antes = con.execute("SELECT COUNT(*) FROM substancia "
                        "WHERE atc_codigo IS NOT NULL").fetchone()[0]

    # O indice agora inclui os sinonimos INN criados por 60_*.
    indice = {}
    for sid, chave in con.execute("SELECT id, chave_normalizada FROM substancia"):
        indice.setdefault(chave, sid)
    n_inn = 0
    for sid, chave, tipo in con.execute(
            "SELECT substancia_id, chave_normalizada, tipo "
            "FROM substancia_sinonimo"):
        if tipo == "INN":
            n_inn += 1
        indice.setdefault(chave, sid)

    vinculadas = 0
    for codigo, nome_en in con.execute(
            "SELECT codigo, nome_en FROM classe_atc WHERE nivel=5"):
        sid = indice.get(skeleton(nome_en or ""))
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

    depois = con.execute("SELECT COUNT(*) FROM substancia "
                         "WHERE atc_codigo IS NOT NULL").fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
    fechar_carga(con, carga, n_inn, vinculadas, 0,
                 "segunda passada: vinculo ATC pelos sinonimos INN de 60_*")

    resumo("VINCULO ATC — SEGUNDA PASSADA", [
        ("sinonimos INN disponiveis", n_inn),
        ("substancias com ATC antes", antes),
        ("vinculadas agora (so as que estavam NULL)", vinculadas),
        ("substancias com ATC depois", "%d (%.1f%%)"
         % (depois, 100 * depois / max(1, total))),
        ("idempotente", "sim — so escreve onde atc_codigo IS NULL"),
    ])
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
