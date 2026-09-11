# -*- coding: utf-8 -*-
"""
VERIFICACAO INDEPENDENTE da carga de produtos, apresentacoes e EAN.

  V1  Recontagem direta da CMED com codigo proprio.
  V2  Comparacao com o banco do sistema anterior (outro codigo, mesma fonte).
  V3  Casos conhecidos: leitura por codigo de barras e TARJA de farmacos
      cuja classificacao sabemos de cor -- e onde o sistema anterior errou.
  V4  Integridade e rastreabilidade.

Uso: python tests/verificacao_30_produtos.py
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ACERVO = Path(r"C:\Conteudos banco de dados tcc")
BANCO = RAIZ / "database" / "conciliador.db"
BANCO_ANTIGO = ACERVO / "banco" / "conciliador.db"
ARQ = ACERVO / "fontes_novas/02_cmed_precos_drogaria/TA_PRECO_MEDICAMENTO.csv"

csv.field_size_limit(10 * 1024 * 1024)
falhas = []


def confere(desc, ok, detalhe=""):
    print("  [%s] %s %s" % ("OK " if ok else "FALHA", desc, detalhe))
    if not ok:
        falhas.append(desc)


def v1_recontagem(con):
    """Le a CMED de novo, com codigo proprio, e compara os totais."""
    print("\nV1 — recontagem direta da CMED (código independente)")
    ggrem, eans, produtos_reg = set(), set(), set()
    linhas = 0
    with open(ARQ, encoding="utf-8-sig", newline="") as fh:
        leitor = csv.reader(fh, delimiter=";")
        for _ in range(41):
            next(leitor)
        cab = next(leitor)
        idx = {c.strip(): i for i, c in enumerate(cab)}
        for l in leitor:
            if not l or not any(l):
                continue
            linhas += 1
            g = l[idx["CÓDIGO GGREM"]].strip()
            if g:
                ggrem.add(g)
            r = re.sub(r"\D", "", l[idx["REGISTRO"]] or "")[:9]
            nome = l[idx["PRODUTO"]].strip()
            if nome:
                produtos_reg.add((r, nome))
            for c in ("EAN 1", "EAN 2", "EAN 3"):
                v = l[idx[c]].strip()
                if v and v != "-" and v.isdigit():
                    eans.add((g, v))

    n_apres = con.execute("SELECT COUNT(*) FROM apresentacao").fetchone()[0]
    n_prod = con.execute("SELECT COUNT(*) FROM produto").fetchone()[0]
    n_ean = con.execute("SELECT COUNT(*) FROM apresentacao_ean").fetchone()[0]
    print("     linhas CMED ................ %d" % linhas)
    confere("apresentações = GGREM distintos", n_apres == len(ggrem),
            "(%d vs %d)" % (n_apres, len(ggrem)))
    confere("produtos = (registro9, nome) distintos", n_prod == len(produtos_reg),
            "(%d vs %d)" % (n_prod, len(produtos_reg)))
    confere("códigos de barras conferem", n_ean == len(eans),
            "(%d vs %d)" % (n_ean, len(eans)))
    confere("mais apresentações do que produtos", n_apres > n_prod,
            "(%.1f apresentações por produto)" % (n_apres / max(1, n_prod)))


def v2_sistema_antigo(con):
    print("\nV2 — comparação com o sistema anterior (código diferente)")
    if not BANCO_ANTIGO.exists():
        print("     banco anterior ausente; pulado")
        return
    ant = sqlite3.connect("file:%s?mode=ro" % BANCO_ANTIGO.as_posix(), uri=True)
    ean_ant = {r[0] for r in ant.execute(
        "SELECT ean FROM apresentacao WHERE ean IS NOT NULL AND TRIM(ean)<>''")}
    ant.close()
    ean_novo = {r[0] for r in con.execute("SELECT ean FROM apresentacao_ean")}
    inter = ean_ant & ean_novo
    cob = 100 * len(inter) / max(1, len(ean_ant))
    print("     EAN — anterior: %d | novo: %d | em comum: %d"
          % (len(ean_ant), len(ean_novo), len(inter)))
    confere("cobertura de EAN do sistema anterior acima de 90%", cob >= 90.0,
            "(%.1f%%)" % cob)
    confere("o novo não perdeu volume de EAN", len(ean_novo) >= len(ean_ant) * 0.95,
            "(%d vs %d)" % (len(ean_novo), len(ean_ant)))


def v3_casos_conhecidos(con):
    """Leitura por codigo de barras e tarja de farmacos conhecidos."""
    print("\nV3 — casos conhecidos")

    # leitura por EAN: pega um EAN real e verifica que chega ao produto certo
    amostra = con.execute(
        "SELECT e.ean, p.nome_comercial, a.descricao FROM apresentacao_ean e "
        "JOIN apresentacao a ON a.id=e.apresentacao_id "
        "JOIN produto p ON p.id=a.produto_id LIMIT 3").fetchall()
    confere("leitura por código de barras devolve produto e apresentação",
            len(amostra) == 3 and all(x[1] and x[2] for x in amostra))
    for ean, nome, desc in amostra:
        print("       %s -> %s | %s" % (ean, nome[:26], desc[:40]))

    # TARJA: o sistema anterior mapeou o codigo numerico da ANVISA ao
    # contrario e chegou a afirmar que tramadol era venda livre. Aqui a
    # fonte e o rotulo por extenso da CMED, entao estes casos tem de bater.
    esperado = {
        "dipirona": "MIP",
        "clonazepam": "TARJA_PRETA",
        "tramadol": ("TARJA_VERMELHA", "TARJA_VERMELHA_RETENCAO"),
        "amoxicilina": ("TARJA_VERMELHA", "TARJA_VERMELHA_RETENCAO"),
        "paracetamol": "MIP",
    }
    for termo, alvo in esperado.items():
        r = con.execute(
            "SELECT nome_dcb, canal_dispensacao FROM substancia "
            "WHERE nome_dcb LIKE ? AND canal_dispensacao IS NOT NULL LIMIT 1",
            ("%" + termo + "%",)).fetchone()
        if r is None:
            confere("tarja de %s" % termo, False, "(substância sem canal)")
            continue
        alvos = alvo if isinstance(alvo, tuple) else (alvo,)
        confere("tarja de %s" % termo, r[1] in alvos,
                "-> %s (%s)" % (r[1], r[0][:30]))

    # Concentracao so quando ha UMA na apresentacao. '+' sozinho nao serve
    # como sinal: '250 MG PO LIOF ... + SER DESCARTAVEL' e um ativo so, com
    # seringa. O que invalida e uma SEGUNDA concentracao apos o '+'.
    re2 = re.compile(r"\+\s*\d+(?:[.,]\d+)?\s*(?:MG|MCG|G|ML|UI|%)", re.I)
    indevidas = [d for v, d in con.execute(
        "SELECT concentracao_valor, descricao FROM apresentacao "
        "WHERE concentracao_valor IS NOT NULL") if re2.search(d)]
    confere("associação em dose fixa ficou sem concentração única",
            not indevidas, "(%d indevidas: %s)" %
            (len(indevidas), indevidas[:1]) if indevidas else "")
    com_mais = con.execute(
        "SELECT COUNT(*) FROM apresentacao WHERE concentracao_valor IS NOT NULL "
        "AND descricao LIKE '%+%'").fetchone()[0]
    print("     (%d com '+' mantiveram concentração: dispositivo, não 2º ativo)"
          % com_mais)

    # EAN: so digito, comprimento GS1
    ruim = con.execute(
        "SELECT COUNT(*) FROM apresentacao_ean "
        "WHERE ean GLOB '*[^0-9]*' OR length(ean) NOT IN (8,12,13,14)").fetchone()[0]
    confere("todo EAN tem formato GS1", ruim == 0, "(%d fora)" % ruim)


def v4_integridade(con):
    print("\nV4 — integridade e rastreabilidade")
    fk = con.execute("PRAGMA foreign_key_check").fetchall()
    confere("integridade referencial", not fk, str(fk[:3]))
    orfas = con.execute(
        "SELECT COUNT(*) FROM apresentacao a WHERE NOT EXISTS "
        "(SELECT 1 FROM produto p WHERE p.id=a.produto_id)").fetchone()[0]
    confere("nenhuma apresentação órfã", orfas == 0)
    sem_ev = con.execute(
        "SELECT COUNT(*) FROM apresentacao a WHERE NOT EXISTS "
        "(SELECT 1 FROM evidencia e WHERE e.tabela_alvo='apresentacao' "
        "AND e.id_alvo=a.id)").fetchone()[0]
    confere("toda apresentação tem evidência de origem", sem_ev == 0,
            "(%d sem)" % sem_ev)
    vinc = con.execute("SELECT COUNT(*) FROM apresentacao_substancia").fetchone()[0]
    sem_vinc = con.execute(
        "SELECT COUNT(*) FROM apresentacao a WHERE NOT EXISTS "
        "(SELECT 1 FROM apresentacao_substancia s WHERE s.apresentacao_id=a.id)"
    ).fetchone()[0]
    print("     vínculos apresentação-substância: %d" % vinc)
    print("     apresentações sem substância reconhecida: %d (%.1f%%)"
          % (sem_vinc, 100 * sem_vinc / max(1, con.execute(
              "SELECT COUNT(*) FROM apresentacao").fetchone()[0])))
    confere("menos de 5% das apresentações sem substância",
            sem_vinc < 0.05 * con.execute(
                "SELECT COUNT(*) FROM apresentacao").fetchone()[0])
    ic = con.execute("SELECT * FROM pragma_integrity_check").fetchone()
    confere("integrity_check do SQLite", ic[0] == "ok", ic[0])


def main() -> int:
    con = sqlite3.connect("file:%s?mode=ro" % BANCO.as_posix(), uri=True)
    print("VERIFICAÇÃO INDEPENDENTE — produtos, apresentações e EAN")
    v1_recontagem(con)
    v2_sistema_antigo(con)
    v3_casos_conhecidos(con)
    v4_integridade(con)
    con.close()
    print("\n" + "=" * 62)
    if falhas:
        print("FALHAS: %d" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("VERIFICAÇÃO INDEPENDENTE PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
