# -*- coding: utf-8 -*-
"""
CARGA DE FARMACO x HABITO (tabagismo) — bulas ANVISA.

Alimenta o modulo 7 do plano de arquitetura (farmaco x habito). Depois da
Fase 3, `interacao_habito` tinha 196 linhas, **todas de alcool e cafeina** e
**zero de tabagismo**: o DrugBank descreve "avoid alcohol" em texto corrido,
mas nao descreve tabagismo.

Tabagismo, alcool e alimento sao justamente os tres modulos que o concorrente
hospitalar nacional nao tem. Deixar tabagismo em zero seria abrir mao de um
terco do diferencial por falta de fonte — quando existe fonte, em portugues,
no proprio acervo.

O QUE E EXTRAIDO, E COM QUE GUARDA
----------------------------------
Uma frase so entra quando tem, ao mesmo tempo:
  - termo de tabagismo (fumo, fumar, fumante, tabagismo, tabaco, cigarro), e
  - verbo de risco na MESMA frase (aumenta o risco, fator de risco,
    deve/devem nao fumar, deixar de fumar, contraindicado a fumantes).

Frase que so cita tabagismo em contexto epidemiologico ("a maior resposta ao
tratamento relacionou-se ao habito de nao fumar") nao afirma interacao com o
medicamento e fica de fora.

O QUE ESTE SCRIPT NUNCA FAZ
---------------------------
Nao gradua. `gravidade='NAO_DETERMINADA'` em todas as linhas: a bula descreve
o risco em texto e nao publica escala. Nao escreve `alerta_cessacao` por
conta propria — a reversao da inducao da CYP1A2 apos parar de fumar e fato
farmacologico conhecido, mas nao esta escrito nestas bulas, e o que nao esta
na fonte nao entra pela porta dos fundos.

Uso: python pipeline/65_habitos_bula.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (ACERVO, abrir_carga, chaves_candidatas, conectar,  # noqa: E402
                    fechar_carga, id_fonte, resumo)

FONTE = "ANVISA - Bulario eletronico"
PASTA = "fontes_novas/01_anvisa_bulario/secoes"
SECOES = ("interacoes", "advertencias", "contraindicacoes")

TABACO = re.compile(r"\b(fumo|fumar|fumantes?|tabagismo|tabaco|cigarros?|"
                    r"fuma[çc]a do tabaco)\b", re.IGNORECASE)

RISCO = re.compile(
    r"aumenta(?:m|r)? (?:substancialmente )?o risco|fator de risco|"
    r"n[ãa]o (?:fumar|fumarem)|deixe de fumar|deixar de fumar|"
    r"contraindicad\w* (?:a|para|em) fumantes|"
    r"devem utilizar outros m[ée]todos|aumenta(?:m)? a incid[êe]ncia",
    re.IGNORECASE)


def frases(texto):
    if not texto:
        return []
    t = re.sub(r"\s+", " ", texto)
    partes = re.split(r"(?<=[.;])\s+|\s*[•−–—]\s*", t)
    return [p.strip() for p in partes if p and len(p.strip()) > 20]


def indice(con):
    idx = defaultdict(set)
    for sid, chave in con.execute("SELECT id, chave_normalizada FROM substancia"):
        idx[chave].add(sid)
    for sid, chave in con.execute(
            "SELECT substancia_id, chave_normalizada FROM substancia_sinonimo"):
        idx[chave].add(sid)
    return idx


def main() -> int:
    con = conectar()
    ja = con.execute("SELECT COUNT(*) FROM interacao_habito WHERE "
                     "habito='TABAGISMO'").fetchone()[0]
    if ja:
        print("tabagismo ja carregado (%d linhas) — nada a fazer" % ja)
        con.close()
        return 0

    arquivos = sorted((ACERVO / PASTA).glob("*.json"))
    if not arquivos:
        print("ERRO: nenhuma secao de bula encontrada")
        con.close()
        return 1

    idx = indice(con)
    fonte_id = id_fonte(con, FONTE)
    carga_id = abrir_carga(con, FONTE, "pipeline/65_habitos_bula.py", PASTA,
                           "secoes de 150 bulas — habito tabagismo")

    lidos = inseridos = citou_sem_risco = sem_substancia = 0
    amostras = []

    for arq in arquivos:
        lidos += 1
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        secoes = d.get("secoes") or {}
        texto = " ".join(str(secoes.get(s) or "") for s in SECOES)
        if not TABACO.search(texto):
            continue

        cand = set()
        for k in chaves_candidatas((d.get("substancia") or "").strip()):
            cand |= idx.get(k, set())
        if len(cand) != 1:
            sem_substancia += 1
            continue
        sid = next(iter(cand))

        melhor = None
        for frase in frases(texto):
            if not TABACO.search(frase):
                continue
            if not RISCO.search(frase):
                citou_sem_risco += 1
                continue
            if melhor is None or len(frase) < len(melhor):
                melhor = frase          # a mais curta e a mais especifica
        if melhor is None:
            continue

        cur = con.execute(
            "INSERT OR IGNORE INTO interacao_habito (substancia_id, habito, "
            "mecanismo, efeito_esperado, gravidade, conduta, alerta_cessacao, "
            "origem, fonte_id, status_revisao) VALUES (?,'TABAGISMO',NULL,?,"
            "'NAO_DETERMINADA',NULL,NULL,'BULA_ANVISA',?,'PENDENTE')",
            (sid, melhor[:500], fonte_id))
        if not cur.rowcount:
            continue
        inseridos += 1
        con.execute(
            "INSERT OR IGNORE INTO evidencia (tabela_alvo,id_alvo,fonte_id,"
            "carga_id,documento,trecho,nivel_evidencia,metodo_extracao) "
            "VALUES ('interacao_habito',?,?,?,?,?,'RESPALDADA','REGEX')",
            (cur.lastrowid, fonte_id, carga_id, arq.name, melhor[:600]))
        amostras.append((d.get("substancia"), melhor[:120]))

    fechar_carga(con, carga_id, lidos, inseridos, citou_sem_risco,
                 "frases que citaram tabaco sem verbo de risco: %d; "
                 "substancia nao resolvida: %d" % (citou_sem_risco, sem_substancia))
    con.commit()

    total = con.execute("SELECT habito, COUNT(*) FROM interacao_habito "
                        "GROUP BY 1 ORDER BY 2 DESC").fetchall()
    resumo("FARMACO x HABITO — tabagismo (bulas)", [
        ("bulas lidas", lidos),
        ("linhas de tabagismo inseridas", inseridos),
        ("frases que citaram tabaco sem verbo de risco", citou_sem_risco),
        ("substância da bula não resolvida", sem_substancia),
        ("interacao_habito por hábito", dict(total)),
    ])
    for s, t in amostras:
        print("    %-30s %s" % ((s or "")[:30], t))
    print("\n  Todas PENDENTE de revisão. Gravidade NAO_DETERMINADA: a bula"
          "\n  descreve o risco em texto e não publica escala.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
