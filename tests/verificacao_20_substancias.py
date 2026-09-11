# -*- coding: utf-8 -*-
"""
VERIFICACAO INDEPENDENTE da carga de substancias.

Nao repete o pipeline: usa tres mecanismos diferentes para procurar erro.

  V1  Recontagem direta do arquivo bruto, sem importar o codigo da carga.
  V2  Comparacao com o banco do sistema anterior, construido por outro
      codigo a partir da mesma fonte -- convergencia e evidencia externa,
      divergencia e pista de defeito.
  V3  Casos conhecidos: substancias de balcao que TEM de estar la, com a
      grafia certa, e propriedades que sabemos verificar.

Uso: python tests/verificacao_20_substancias.py
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ACERVO = Path(r"C:\Conteudos banco de dados tcc")
BANCO = RAIZ / "database" / "conciliador.db"
BANCO_ANTIGO = ACERVO / "banco" / "conciliador.db"

csv.field_size_limit(10 * 1024 * 1024)
falhas = []


def confere(desc, ok, detalhe=""):
    print("  [%s] %s %s" % ("OK " if ok else "FALHA", desc, detalhe))
    if not ok:
        falhas.append(desc)


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "")
                   if unicodedata.category(c) != "Mn").lower().strip()


# --------------------------------------------------------------------- V1
def v1_recontagem(con):
    """Reconta produtos ativos direto do CSV, com codigo proprio."""
    print("\nV1 — recontagem direta do arquivo bruto (codigo independente)")
    ativos_linhas = 0
    substancias_texto = set()
    with open(ACERVO / "TA_CONSULTA_MEDICAMENTOS.CSV", encoding="iso-8859-1",
              newline="") as fh:
        leitor = csv.DictReader(fh, delimiter=";")
        for r in leitor:
            if (r.get("VALIDADE_SITUACAO") or "").strip() == "Ativo":
                ativos_linhas += 1
                s = (r.get("SUBSTANCIAS_MEDICAMENTOS") or "").strip()
                if s:
                    substancias_texto.add(s.lower())

    # divisao ingenua, so por virgula, sem esqueleto: da um teto grosseiro
    cruas = set()
    for s in substancias_texto:
        s = re.sub(r"\([^)]*\)", " ", s)
        for p in re.split(r"[,+/]| e ", s):
            p = re.sub(r"\s+", " ", p).strip(" .;-")
            p = re.sub(r"\s*associa[cç][oõ]es\s*", "", p)
            if len(p) >= 3:
                cruas.add(p)

    n_banco = con.execute("SELECT COUNT(*) FROM substancia").fetchone()[0]
    print("     linhas ativas no CSV ............ %d" % ativos_linhas)
    print("     strings brutas distintas ....... %d" % len(cruas))
    print("     substancias no banco ........... %d" % n_banco)
    # o esqueleto agrupa sais e grafias: o banco tem de ser MENOR que o cru
    confere("agrupamento reduziu as grafias cruas",
            n_banco < len(cruas),
            "(%d < %d, reducao de %.1f%%)" %
            (n_banco, len(cruas), 100 * (1 - n_banco / max(1, len(cruas)))))
    confere("nenhuma substancia sem produto ativo entrou",
            con.execute("SELECT COUNT(*) FROM substancia "
                        "WHERE n_produtos_ativos < 1").fetchone()[0] == 0)
    return n_banco


# --------------------------------------------------------------------- V2
def v2_comparar_sistema_antigo(con):
    """Compara com o banco anterior: outro codigo, mesma fonte."""
    print("\nV2 — comparacao com o sistema anterior (codigo diferente)")
    if not BANCO_ANTIGO.exists():
        print("     banco anterior ausente; verificacao pulada")
        return
    ant = sqlite3.connect("file:%s?mode=ro" % BANCO_ANTIGO.as_posix(), uri=True)
    nomes_ant = {sem_acento(r[0]) for r in
                 ant.execute("SELECT dcb_nome FROM substancia")}
    chaves_ant = {r[0] for r in
                  ant.execute("SELECT chave_normalizada FROM substancia")
                  if r[0]}
    ant.close()

    nomes_novo = {sem_acento(r[0]) for r in
                  con.execute("SELECT nome_dcb FROM substancia")}
    chaves_novo = {r[0] for r in
                   con.execute("SELECT chave_normalizada FROM substancia")}

    print("     substancias — anterior: %d | novo: %d" %
          (len(nomes_ant), len(nomes_novo)))
    inter = chaves_ant & chaves_novo
    so_ant = chaves_ant - chaves_novo
    so_novo = chaves_novo - chaves_ant
    cob = 100 * len(inter) / max(1, len(chaves_ant))
    print("     esqueletos em comum ............ %d (%.1f%% do anterior)"
          % (len(inter), cob))
    print("     so no anterior ................. %d" % len(so_ant))
    print("     so no novo ..................... %d" % len(so_novo))
    if so_ant:
        print("       exemplos so no anterior: %s" % sorted(so_ant)[:5])
    if so_novo:
        print("       exemplos so no novo: %s" % sorted(so_novo)[:5])
    # dois codigos independentes sobre a mesma fonte tem de convergir muito
    confere("convergencia com o sistema anterior acima de 95%", cob >= 95.0,
            "(%.1f%%)" % cob)


# --------------------------------------------------------------------- V3
def v3_casos_conhecidos(con):
    """Substancias de balcao que precisam existir, com o que sabemos delas."""
    print("\nV3 — casos conhecidos de balcao")
    esperados = ["dipirona", "paracetamol", "ibuprofeno", "omeprazol",
                 "varfarina", "sinvastatina", "metformina", "losartana",
                 "amoxicilina", "levotiroxina", "clonazepam", "tramadol",
                 "acido acetilsalicilico", "captopril", "sertralina"]
    ausentes = []
    for termo in esperados:
        r = con.execute(
            "SELECT s.nome_dcb, s.n_produtos_ativos FROM substancia s "
            "WHERE s.nome_dcb LIKE ? OR EXISTS (SELECT 1 FROM substancia_sinonimo n "
            "WHERE n.substancia_id = s.id AND n.nome LIKE ?) LIMIT 1",
            ("%" + termo.split()[-1][:8] + "%", "%" + termo.split()[-1][:8] + "%")
        ).fetchone()
        if r is None:
            ausentes.append(termo)
    confere("substancias de balcao presentes", not ausentes,
            "ausentes: %s" % ausentes if ausentes else "(15/15)")

    # CAS e formato conhecido: NNNNNN-NN-N
    ruins = con.execute(
        "SELECT COUNT(*) FROM substancia WHERE cas IS NOT NULL "
        "AND cas NOT GLOB '*[0-9]-[0-9][0-9]-[0-9]'").fetchone()[0]
    total_cas = con.execute(
        "SELECT COUNT(*) FROM substancia WHERE cas IS NOT NULL").fetchone()[0]
    confere("CAS no formato oficial", ruins == 0,
            "(%d fora do padrao em %d)" % (ruins, total_cas))

    # Residuo de divisao e '+' ou 'associacoes'. Parenteses NAO entra:
    # em nome botanico a citacao de autoridade e parte do nome oficial da DCB
    # ('Ananas comosus (L.) Merr.'), e exigir sua ausencia era falso positivo.
    lixo = con.execute(
        "SELECT nome_dcb FROM substancia WHERE nome_dcb LIKE '%+%' "
        "OR nome_dcb LIKE '%associa%' LIMIT 5").fetchall()
    confere("nenhum nome com residuo de divisao", not lixo, str(lixo))
    bot = con.execute(
        "SELECT COUNT(*) FROM substancia WHERE nome_dcb LIKE '%(%'").fetchone()[0]
    print("     (%d nomes com parenteses: citacao de autoridade botanica)" % bot)

    # chave normalizada unica por substancia (o agrupamento e por esqueleto)
    dup = con.execute(
        "SELECT chave_normalizada, COUNT(*) c FROM substancia "
        "GROUP BY chave_normalizada HAVING c > 1 LIMIT 5").fetchall()
    confere("um esqueleto = uma substancia", not dup, str(dup))

    # ambiguidade registrada, nao resolvida sozinha
    amb = con.execute("SELECT COUNT(*) FROM substancia "
                      "WHERE status_resolucao='AMBIGUA'").fetchone()[0]
    reg = con.execute("SELECT COUNT(*) FROM resolucao_ambigua").fetchone()[0]
    confere("toda ambiguidade tem registro para curadoria", amb <= reg,
            "(%d marcadas, %d registradas)" % (amb, reg))


def v4_rastreabilidade(con):
    print("\nV4 — rastreabilidade")
    sem_ev = con.execute(
        "SELECT COUNT(*) FROM substancia s WHERE NOT EXISTS "
        "(SELECT 1 FROM evidencia e WHERE e.tabela_alvo='substancia' "
        "AND e.id_alvo=s.id)").fetchone()[0]
    confere("toda substancia tem evidencia de origem", sem_ev == 0,
            "(%d sem)" % sem_ev)
    r = con.execute(
        "SELECT fonte, documento_origem, data_importacao FROM vw_rastreabilidade "
        "WHERE tabela_alvo='substancia' LIMIT 1").fetchone()
    confere("rastro chega a fonte, arquivo e data", bool(r), str(r))
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    confere("integridade referencial", not fk, str(fk[:3]))


def main() -> int:
    con = sqlite3.connect("file:%s?mode=ro" % BANCO.as_posix(), uri=True)
    print("VERIFICACAO INDEPENDENTE — carga de substancias")
    v1_recontagem(con)
    v2_comparar_sistema_antigo(con)
    v3_casos_conhecidos(con)
    v4_rastreabilidade(con)
    con.close()
    print("\n" + "=" * 62)
    if falhas:
        print("FALHAS: %d" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("VERIFICACAO INDEPENDENTE PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
