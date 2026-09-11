# -*- coding: utf-8 -*-
"""
Regras de administracao extraidas das bulas da ANVISA (segunda fonte).

POR QUE UMA SEGUNDA FONTE: a primeira (DrugBank) e texto em ingles lido por
expressao regular. A bula e fonte regulatoria brasileira, em portugues. Onde
as duas concordam, a regra fica muito mais forte; onde discordam, o conflito
e registrado em vez de resolvido em silencio.

PRECISAO: a busca e restrita a secao 'POSOLOGIA E MODO DE USAR'. Medi antes:
procurando '<n> horas' na bula inteira, so 1 de 12 trechos era regra de
separacao -- o resto era meia-vida e tempo de pico. Dentro da posologia a
frase e instrucao de uso, nao farmacocinetica.

Toda regra entra com metodo REGEX e status PENDENTE: a view marca como
'EXTRAIDA_AUTOMATICAMENTE' e o motor rebaixa o achado a POSSIVEL.

Uso: python pipeline/55_regras_bula.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (ACERVO, abrir_carga, conectar, fechar_carga,  # noqa: E402
                    id_fonte, registrar_evidencia, resumo)
from normalizacao import skeleton  # noqa: E402

PASTA = "fontes_novas/01_anvisa_bulario/texto"
FONTE = "ANVISA - Bulario eletronico"

# Delimita a secao de posologia: dali ate a proxima secao numerada da bula.
RE_POSOLOGIA = re.compile(
    r"(POSOLOGIA[^\n]{0,60}|COMO\s+DEVO\s+USAR[^\n]{0,60}|MODO\s+DE\s+USAR)"
    r"(.{0,6000}?)"
    r"(?=\n\s*\d+\.\s|REA[ÇC][ÕO]ES\s+ADVERSAS|O\s+QUE\s+DEVO\s+FAZER|$)",
    re.S | re.I)

# (tipo, padrao, orientacao em pt-BR)
DIRETIVAS = [
    ("JEJUM",
     r"\bem\s+jejum\b|est[oô]mago\s+vazio",
     "Tomar em jejum, com o estômago vazio."),
    ("COM_ALIMENTO",
     r"(?:junto\s+)?com\s+(?:as\s+)?refei[çc][õo]es|com\s+alimento|"
     r"durante\s+as\s+refei[çc][õo]es|com\s+as\s+refei[çc][õo]es",
     "Tomar junto com alimento."),
    ("APOS_ALIMENTO",
     r"ap[óo]s\s+(?:as\s+)?refei[çc][õo]es|logo\s+ap[óo]s\s+a\s+refei[çc][ãa]o",
     "Tomar logo após a refeição."),
    ("ANTES_ALIMENTO",
     r"antes\s+d(?:as|a)\s+refei[çc][õo]e?s?|antes\s+do\s+caf[ée]",
     "Tomar antes da refeição."),
    ("NAO_PARTIR_NAO_TRITURAR",
     r"n[ãa]o\s+(?:deve\s+ser\s+|devem\s+ser\s+|)"
     r"(?:partid|mastigad|triturad|amassad|dissolvid)",
     "Engolir inteiro: não partir, mastigar nem triturar."),
    ("COM_AGUA_ABUNDANTE",
     r"com\s+(?:um\s+)?copo\s+(?:cheio\s+)?de\s+[áa]gua|"
     r"com\s+bastante\s+[áa]gua|ingerir\s+bastante\s+l[íi]quido",
     "Tomar com um copo cheio de água."),
    ("SUBLINGUAL",
     r"\bsublingual\b|sob\s+a\s+l[íi]ngua",
     "Uso sublingual: dissolver sob a língua, não engolir."),
    ("PERMANECER_SENTADO",
     r"permanecer\s+(?:sentad|em\s+p[ée])|n[ãa]o\s+se\s+deitar",
     "Permanecer sentado ou em pé após tomar; não deitar."),
]

# Tipos que se excluem: um medicamento nao pode ser 'em jejum' e 'com
# alimento' ao mesmo tempo. Quando mais de um casa no MESMO texto, a bula e
# ambigua para o nosso padrao de leitura -- entao NENHUM e gravado e o caso
# vai para auditoria_conflito. Emitir instrucao contraditoria de posologia
# e pior do que nao emitir nada.
EXCLUSIVOS = {"JEJUM", "COM_ALIMENTO", "APOS_ALIMENTO",
              "ANTES_ALIMENTO", "INDIFERENTE_ALIMENTO"}

# Minutos em relacao a refeicao, quando a bula declara
RE_MIN = re.compile(
    r"(\d{1,3})\s*(?:a\s*\d{1,3}\s*)?minutos?\s+antes[^.]{0,40}"
    r"(?:refei[çc][ãa]o|refei[çc][õo]es|alimenta[çc][ãa]o|caf[ée])", re.I)
RE_H_REFEICAO = re.compile(
    r"(\d)\s*(?:a\s*\d\s*)?horas?\s+(?:antes|ap[óo]s)[^.]{0,40}"
    r"(?:refei[çc][ãa]o|refei[çc][õo]es|alimenta[çc][ãa]o)", re.I)


def esq(nome: str) -> str:
    if not nome:
        return ""
    s = skeleton(nome)
    return s if s and len(s) >= 3 else ""


def secao_posologia(texto: str) -> str:
    m = RE_POSOLOGIA.search(texto)
    return m.group(2) if m else ""


def intervalo_refeicao(trecho: str):
    m = RE_MIN.search(trecho)
    if m:
        v = int(m.group(1))
        return v if 5 <= v <= 720 else None
    m = RE_H_REFEICAO.search(trecho)
    if m:
        return int(m.group(1)) * 60
    return None


def main() -> int:
    con = conectar()
    fid = id_fonte(con, FONTE)
    carga = abrir_carga(con, FONTE, "55_regras_bula.py", PASTA)

    indice = {}
    for sid, chave in con.execute("SELECT id, chave_normalizada FROM substancia"):
        indice.setdefault(chave, sid)
    for sid, chave in con.execute(
            "SELECT substancia_id, chave_normalizada FROM substancia_sinonimo"):
        indice.setdefault(chave, sid)

    arquivos = sorted((ACERVO / PASTA).glob("*.txt"))
    lidos = len(arquivos)
    com_secao = casadas = n_regras = ambiguos = 0
    nao_br = 0
    tipos = Counter()
    exemplos = []

    for arq in arquivos:
        nome = arq.stem.replace("_", " ")
        sid = indice.get(esq(nome))
        if sid is None:
            nao_br += 1
            continue
        casadas += 1
        texto = arq.read_text(encoding="utf-8", errors="replace")
        trecho = secao_posologia(texto)
        if not trecho.strip():
            continue
        com_secao += 1
        minutos = intervalo_refeicao(trecho)

        casados = [(tipo, padrao, orientacao, re.search(padrao, trecho, re.I))
                   for tipo, padrao, orientacao in DIRETIVAS]
        casados = [c for c in casados if c[3]]
        exclusivos = [c for c in casados if c[0] in EXCLUSIVOS]
        if len(exclusivos) > 1:
            ambiguos += 1
            con.execute(
                "INSERT OR IGNORE INTO auditoria_conflito (tabela_alvo,id_alvo,descricao,"
                "fonte_a,valor_a,fonte_b,valor_b,decisao,justificativa) "
                "VALUES ('regra_administracao',?,?,?,?,?,?,'NAO_RESOLVIDO',?)",
                (sid,
                 "Bula de %s traz mais de uma regra de alimentacao no mesmo "
                 "trecho de posologia" % nome,
                 FONTE, exclusivos[0][0], FONTE, exclusivos[1][0],
                 "Nenhuma foi gravada: instrucao contraditoria de posologia "
                 "nao pode chegar ao farmaceutico. Requer leitura humana."))
            casados = [c for c in casados if c[0] not in EXCLUSIVOS]

        for tipo, padrao, orientacao, m in casados:
            ini = max(0, m.start() - 90)
            citacao = " ".join(trecho[ini:m.end() + 90].split())
            mins = minutos if tipo in ("JEJUM", "COM_ALIMENTO",
                                       "ANTES_ALIMENTO", "APOS_ALIMENTO") else None
            cur = con.execute(
                "INSERT OR IGNORE INTO regra_administracao (substancia_id,tipo,"
                "intervalo_refeicao_min,texto_orientacao,origem,fonte_id,"
                "status_revisao) VALUES (?,?,?,?,'BULA_ANVISA',?,'PENDENTE')",
                (sid, tipo, mins,
                 orientacao + (" Respeitar %d minutos em relação à refeição."
                               % mins if mins else ""), fid))
            if cur.rowcount:
                n_regras += 1
                tipos[tipo] += 1
                registrar_evidencia(con, "regra_administracao", cur.lastrowid,
                                    fid, carga, arq.name, "RESPALDADA",
                                    "REGEX", citacao[:400])
                if len(exemplos) < 5:
                    exemplos.append((nome, tipo, citacao[:110]))

    con.commit()
    fechar_carga(con, carga, lidos, n_regras, nao_br,
                 "ignorados = bulas de substancia sem produto ativo no Brasil")

    concordam = con.execute(
        "SELECT COUNT(*) FROM vw_regra_concordancia WHERE n_fontes > 1"
    ).fetchone()[0]

    resumo("REGRAS DE ADMINISTRACAO — BULAS ANVISA", [
        ("bulas lidas", lidos),
        ("  casaram com substancia brasileira", casadas),
        ("  com secao de posologia localizada", com_secao),
        ("  sem correspondencia (ignoradas)", nao_br),
        ("regras extraidas", n_regras),
        ("regras confirmadas por DUAS fontes", concordam),
        ("bulas com regra de alimentacao ambigua (nao gravada)", ambiguos),
    ])
    print("\n  por tipo:")
    for t, n in tipos.most_common():
        print("    %-30s %d" % (t, n))
    if exemplos:
        print("\n  amostra do trecho que gerou a regra:")
        for nome, tipo, cit in exemplos:
            print("    %-22s %-22s %s" % (nome[:22], tipo, cit))
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
