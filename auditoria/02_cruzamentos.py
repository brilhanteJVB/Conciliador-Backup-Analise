# -*- coding: utf-8 -*-
"""
FASE 3 - MAPA DO ACERVO: cruzamento medido entre as fontes
==========================================================
Responde, com numero e nao com suposicao, a pergunta que decide o que entra
no banco: **quanto de cada fonte internacional chega a uma substancia que
existe no Brasil?**

Ancora: as substancias de medicamentos ATIVOS na ANVISA
(TA_CONSULTA_MEDICAMENTOS), reduzidas ao esqueleto fonetico de lib_norm.

Le a origem em modo SOMENTE LEITURA. Nada e gravado fora de
'Sistema Conciliador projeto'.

Saida: auditoria/saida/cruzamentos.json
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ORIGEM = Path(r"C:\Conteudos banco de dados tcc")
SAIDA = Path(r"C:\Sistema Conciliador projeto") / "auditoria" / "saida"
SAIDA.mkdir(parents=True, exist_ok=True)

# lib_norm vive no acervo e e importada sem ser copiada nem alterada
sys.path.insert(0, str(ORIGEM / "analise_dados" / "scripts"))
from lib_norm import skeleton  # noqa: E402

csv.field_size_limit(10 * 1024 * 1024)


def esq(nome: str) -> str:
    """Esqueleto canonico de um nome de farmaco; '' quando nao aproveitavel."""
    if not nome:
        return ""
    s = skeleton(str(nome))
    return s if s and len(s) >= 3 else ""


def ler(caminho: Path, delim: str, enc: str, pular: int = 0):
    with open(caminho, "r", encoding=enc, errors="replace", newline="") as fh:
        leitor = csv.reader(fh, delimiter=delim)
        for _ in range(pular):
            next(leitor, None)
        cab = next(leitor, None)
        if cab is None:
            return
        idx = {c.strip(): i for i, c in enumerate(cab)}
        for linha in leitor:
            if linha:
                yield idx, linha


def coluna(idx, linha, nome, padrao=""):
    i = idx.get(nome)
    if i is None or i >= len(linha):
        return padrao
    return (linha[i] or "").strip()


# ------------------------------------------------------- 1) ancora brasileira

def ancora_br():
    """Substancias de produtos ATIVOS na ANVISA, por esqueleto."""
    ativos, todos = set(), set()
    nomes_por_esq = {}
    for idx, linha in ler(ORIGEM / "TA_CONSULTA_MEDICAMENTOS.CSV", ";", "iso-8859-1"):
        subs = coluna(idx, linha, "SUBSTANCIAS_MEDICAMENTOS")
        situacao = coluna(idx, linha, "VALIDADE_SITUACAO")
        if not subs:
            continue
        # associacoes vem separadas por '+' ou ';'
        for parte in re.split(r"[;+]", subs):
            e = esq(parte)
            if not e:
                continue
            todos.add(e)
            nomes_por_esq.setdefault(e, parte.strip().lower())
            if situacao == "Ativo":
                ativos.add(e)
    return ativos, todos, nomes_por_esq


# --------------------------------------------------- 2) fontes internacionais

def nomes_de(caminho: Path, colunas, delim=",", enc="utf-8-sig", pular=0):
    """Conta esqueletos distintos nas colunas de nome de uma fonte."""
    vistos = Counter()
    brutos = 0
    for idx, linha in ler(caminho, delim, enc, pular):
        for c in colunas:
            v = coluna(idx, linha, c)
            if v:
                brutos += 1
                e = esq(v)
                if e:
                    vistos[e] += 1
    return vistos, brutos


def pares_de(caminho: Path, col_a, col_b, delim=",", enc="utf-8-sig", pular=0):
    """Pares (esqueleto_a, esqueleto_b) normalizados e sem ordem."""
    pares = set()
    total = 0
    for idx, linha in ler(caminho, delim, enc, pular):
        a, b = coluna(idx, linha, col_a), coluna(idx, linha, col_b)
        if not a or not b:
            continue
        total += 1
        ea, eb = esq(a), esq(b)
        if ea and eb and ea != eb:
            pares.add((ea, eb) if ea < eb else (eb, ea))
    return pares, total


def cobertura(vistos, ancora):
    """Quantos esqueletos da fonte existem no Brasil, e quanto do BR e coberto."""
    presentes = set(vistos) & ancora
    return {
        "substancias_distintas_na_fonte": len(vistos),
        "substancias_que_existem_no_BR": len(presentes),
        "pct_da_fonte_aproveitavel": pct(len(presentes), len(vistos)),
        "substancias_BR_cobertas": len(presentes),
        "pct_do_BR_coberto": pct(len(presentes), len(ancora)),
    }


def pct(a, b):
    return round(100 * a / b, 1) if b else 0.0


def main() -> int:
    print("Lendo ancora ANVISA...", flush=True)
    ativos, todos, nomes = ancora_br()
    print(f"  substancias BR ativas: {len(ativos)} (todas as situacoes: {len(todos)})")

    r = {"ancora": {"substancias_br_ativas": len(ativos),
                    "substancias_br_todas_situacoes": len(todos)},
         "fontes": {}, "pares": {}}

    fontes = [
        ("db_drug_interactions.csv", ["Drug 1", "Drug 2"], ",", "utf-8-sig", 0),
        ("Drug-disease/drugsInfo.csv", ["DrugName"], ",", "utf-8-sig", 0),
        ("Drug to Food interactions Dataset.json", None, None, None, None),
        ("Drug finder db w_o brands - deepseek_csv_20250915_dff2b8.csv",
         ["Generic Name"], ",", "utf-8-sig", 0),
        ("medicine_dataset.csv", ["name"], ",", "utf-8-sig", 0),
        ("fontes_novas/05_atc_classes/WHO_ATC-DDD_2026-04-25.csv", ["atc_name"], ",", "utf-8-sig", 0),
        ("fontes_novas/08_iuphar_gtopdb/ligands.csv", ["Name"], ",", "utf-8-sig", 1),
    ]
    for rel, cols, delim, enc, pular in fontes:
        caminho = ORIGEM / rel
        print(f"Lendo {rel}...", flush=True)
        if rel.endswith(".json"):
            dados = json.loads(caminho.read_text(encoding="utf-8"))
            vistos = Counter()
            for reg in dados:
                e = esq(reg.get("name", ""))
                if e:
                    vistos[e] += 1
        else:
            vistos, _ = nomes_de(caminho, cols, delim, enc, pular)
        r["fontes"][rel] = cobertura(vistos, ativos)
        print("   ", json.dumps(r["fontes"][rel], ensure_ascii=False))

    # DDInter: os 8 arquivos formam uma fonte so
    print("Lendo DDInter (8 arquivos)...", flush=True)
    vistos_dd = Counter()
    pares_dd = set()
    niveis = Counter()
    for letra in "ABDHLPRV":
        caminho = ORIGEM / "DDInter" / f"ddinter_downloads_code_{letra}.csv"
        v, _ = nomes_de(caminho, ["Drug_A", "Drug_B"], ",", "utf-8-sig", 0)
        vistos_dd.update(v)
        p, _ = pares_de(caminho, "Drug_A", "Drug_B", ",", "utf-8-sig", 0)
        pares_dd |= p
        for idx, linha in ler(caminho, ",", "utf-8-sig"):
            niveis[coluna(idx, linha, "Level")] += 1
    r["fontes"]["DDInter/ (8 arquivos)"] = cobertura(vistos_dd, ativos)
    r["fontes"]["DDInter/ (8 arquivos)"]["niveis_de_gravidade"] = dict(niveis)
    print("   ", json.dumps(r["fontes"]["DDInter/ (8 arquivos)"], ensure_ascii=False))

    # ------------------------------------------------- pares de interacao
    print("Cruzando pares de interacao...", flush=True)
    pares_db, total_db = pares_de(ORIGEM / "db_drug_interactions.csv",
                                  "Drug 1", "Drug 2", ",", "utf-8-sig", 0)
    br_db = {p for p in pares_db if p[0] in ativos and p[1] in ativos}
    br_dd = {p for p in pares_dd if p[0] in ativos and p[1] in ativos}

    r["pares"] = {
        "db_drug_interactions": {
            "registros": total_db,
            "pares_unicos_apos_normalizar": len(pares_db),
            "pares_BRxBR": len(br_db),
            "pct_BRxBR": pct(len(br_db), len(pares_db)),
            "gradua_gravidade": False,
        },
        "DDInter": {
            "pares_unicos_apos_normalizar": len(pares_dd),
            "pares_BRxBR": len(br_dd),
            "pct_BRxBR": pct(len(br_dd), len(pares_dd)),
            "gradua_gravidade": True,
        },
        "sobreposicao": {
            "pares_em_ambas": len(pares_db & pares_dd),
            "so_em_db_drug_interactions": len(pares_db - pares_dd),
            "so_em_DDInter": len(pares_dd - pares_db),
            "uniao_BRxBR": len(br_db | br_dd),
        },
    }
    print("   ", json.dumps(r["pares"], ensure_ascii=False, indent=1))

    destino = SAIDA / "cruzamentos.json"
    destino.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nOK -> {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
