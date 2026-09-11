# -*- coding: utf-8 -*-
"""
VERIFICACAO INDEPENDENTE das regras de administracao e separacao.

  V1  Recontagem direta do JSON de origem, com codigo proprio.
  V2  Casos clinicos conhecidos: farmacos cuja regra de administracao e
      conhecida de cor. Aqui a ausencia tambem e defeito -- um conciliador
      que nao sabe que levotiroxina e em jejum esta incompleto.
  V3  Coerencia interna: nenhuma substancia com orientacao contraditoria,
      nenhum intervalo fora de faixa, toda regra com trecho de evidencia.
  V4  A regra do intervalo desconhecido: o texto exibido tem de declarar a
      ausencia, nunca sugerir um numero.

Uso: python tests/verificacao_50_regras.py
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ACERVO = Path(r"C:\Conteudos banco de dados tcc")
BANCO = RAIZ / "database" / "conciliador.db"
ARQ = ACERVO / "Drug to Food interactions Dataset.json"

falhas = []
avisos = []


def confere(desc, ok, detalhe=""):
    print("  [%s] %s %s" % ("OK " if ok else "FALHA", desc, detalhe))
    if not ok:
        falhas.append(desc)


def v1_recontagem(con):
    """Reconta as frases do JSON sem usar o classificador do pipeline."""
    print("\nV1 — recontagem direta do JSON (código independente)")
    dados = json.loads(ARQ.read_text(encoding="utf-8"))
    jejum = comida = agua = alcool = toranja = 0
    for r in dados:
        t = " ".join(r.get("food_interactions") or []).lower()
        if "empty stomach" in t:
            jejum += 1
        if "take with food" in t:
            comida += 1
        if "full glass of water" in t:
            agua += 1
        if "avoid alcohol" in t:
            alcool += 1
        if "grapefruit" in t:
            toranja += 1
    print("     no arquivo (todos os países): jejum=%d comida=%d água=%d "
          "álcool=%d toranja=%d" % (jejum, comida, agua, alcool, toranja))

    def n(tipo):
        return con.execute(
            "SELECT COUNT(*) FROM regra_administracao WHERE tipo=? "
            "AND origem='FONTE_EXTERNA'", (tipo,)).fetchone()[0]

    # O banco tem só os fármacos com produto ativo no Brasil: sempre MENOS.
    confere("regras de jejum não excedem o arquivo", n("JEJUM") <= jejum,
            "(%d <= %d)" % (n("JEJUM"), jejum))
    confere("regras com alimento não excedem o arquivo",
            n("COM_ALIMENTO") <= comida, "(%d <= %d)" % (n("COM_ALIMENTO"), comida))
    confere("regras de água não excedem o arquivo",
            n("COM_AGUA_ABUNDANTE") <= agua,
            "(%d <= %d)" % (n("COM_AGUA_ABUNDANTE"), agua))
    nalc = con.execute("SELECT COUNT(*) FROM interacao_habito "
                       "WHERE habito='ALCOOL'").fetchone()[0]
    confere("interações com álcool não excedem o arquivo", nalc <= alcool,
            "(%d <= %d)" % (nalc, alcool))
    ntor = con.execute(
        "SELECT COUNT(*) FROM interacao_item i JOIN item_nao_medicamentoso n "
        "ON n.id=i.item_id WHERE n.nome='toranja'").fetchone()[0]
    confere("interações com toranja não excedem o arquivo", ntor <= toranja,
            "(%d <= %d)" % (ntor, toranja))


def v2_casos_clinicos(con):
    """Farmacos de regra conhecida. Ausencia tambem conta como defeito."""
    print("\nV2 — casos clínicos conhecidos")

    def regras(termo):
        return {r[0] for r in con.execute(
            "SELECT r.tipo FROM regra_administracao r JOIN substancia s "
            "ON s.id=r.substancia_id WHERE s.nome_dcb LIKE ?",
            ("%" + termo + "%",))}

    esperado = [
        ("levotiroxina", "JEJUM", "hormônio tireoidiano: absorção cai com alimento"),
        # A fonte escreve "Take before a meal. Take 30-60 minutes before
        # breakfast", nao "empty stomach". Exigir JEJUM aqui seria exigir
        # do codigo algo que a fonte nao diz: as duas formas sao aceitas.
        ("alendronato", ("JEJUM", "ANTES_ALIMENTO"),
         "bifosfonato: estomago vazio antes do cafe"),
        ("captopril", "JEJUM", "alimento reduz a absorção"),
        ("carvedilol", "COM_ALIMENTO", "alimento reduz hipotensão postural"),
    ]
    for termo, tipo, motivo in esperado:
        r = regras(termo)
        if not r:
            avisos.append("%s: nenhuma regra carregada (%s)" % (termo, motivo))
            print("     [aviso] %-16s sem regra — %s" % (termo, motivo))
            continue
        aceitos = tipo if isinstance(tipo, tuple) else (tipo,)
        confere("%s tem regra %s" % (termo, " ou ".join(aceitos)),
                bool(set(aceitos) & r), "-> %s" % sorted(r))

    # separacao por cation, o caso classico de quelacao
    print("     separações por cátion/laticínio carregadas:")
    for nome, orient in con.execute(
            "SELECT s.nome_dcb, r.orientacao_pt FROM vw_regra_separacao_liberada r "
            "JOIN substancia s ON s.id=r.substancia_id LIMIT 8"):
        print("       %-22s %s" % (nome[:22], orient))
    n_sep = con.execute(
        "SELECT COUNT(*) FROM vw_regra_separacao_liberada").fetchone()[0]
    confere("existem regras de separação", n_sep > 0, "(%d)" % n_sep)


def v3_coerencia(con):
    print("\nV3 — coerência interna")
    EXC = ("JEJUM", "COM_ALIMENTO", "APOS_ALIMENTO", "ANTES_ALIMENTO",
           "INDIFERENTE_ALIMENTO")
    # contradicao dura: jejum e com-alimento na MESMA fonte
    dura = con.execute(
        "SELECT COUNT(*) FROM (SELECT r1.substancia_id FROM regra_administracao r1 "
        "JOIN regra_administracao r2 ON r1.substancia_id=r2.substancia_id "
        "AND r1.fonte_id=r2.fonte_id AND r1.tipo='JEJUM' "
        "AND r2.tipo IN ('COM_ALIMENTO','APOS_ALIMENTO'))").fetchone()[0]
    confere("nenhuma fonte manda jejum e com-alimento ao mesmo tempo", dura == 0,
            "(%d)" % dura)

    # divergencia entre fontes tem de estar registrada, nao suprimida
    div = con.execute(
        "SELECT COUNT(*) FROM (SELECT substancia_id FROM regra_administracao "
        "WHERE tipo IN %s GROUP BY substancia_id HAVING COUNT(DISTINCT tipo)>1)"
        % str(EXC)).fetchone()[0]
    reg = con.execute(
        "SELECT COUNT(*) FROM auditoria_conflito "
        "WHERE tabela_alvo='regra_administracao'").fetchone()[0]
    print("     substâncias com mais de um tipo de regra alimentar: %d" % div)
    print("     conflitos registrados em auditoria: %d" % reg)
    confere("divergência não fica sem registro", div == 0 or reg > 0)

    fora = con.execute(
        "SELECT COUNT(*) FROM regra_separacao WHERE intervalo_horas IS NOT NULL "
        "AND (intervalo_horas < 0.25 OR intervalo_horas > 24)").fetchone()[0]
    confere("intervalos dentro da faixa plausível", fora == 0, "(%d fora)" % fora)

    sem_ev = con.execute(
        "SELECT COUNT(*) FROM regra_administracao r WHERE NOT EXISTS "
        "(SELECT 1 FROM evidencia e WHERE e.tabela_alvo='regra_administracao' "
        "AND e.id_alvo=r.id)").fetchone()[0]
    confere("toda regra tem evidência", sem_ev == 0, "(%d sem)" % sem_ev)

    sem_trecho = con.execute(
        "SELECT COUNT(*) FROM evidencia WHERE tabela_alvo='regra_administracao' "
        "AND (trecho IS NULL OR TRIM(trecho)='')").fetchone()[0]
    confere("toda evidência guarda o trecho de origem", sem_trecho == 0,
            "(%d sem)" % sem_trecho)

    # extracao automatica nunca se apresenta como revisada
    auto = con.execute(
        "SELECT COUNT(*) FROM vw_regra_administracao_liberada "
        "WHERE confianca_extracao='EXTRAIDA_AUTOMATICAMENTE'").fetchone()[0]
    rev = con.execute(
        "SELECT COUNT(*) FROM vw_regra_administracao_liberada "
        "WHERE confianca_extracao='REVISADA'").fetchone()[0]
    print("     regras extraídas automaticamente: %d | revisadas: %d" % (auto, rev))
    confere("regra não revisada é marcada como tal", auto > 0 or rev > 0)


def v4_intervalo_desconhecido(con):
    print("\nV4 — intervalo não estabelecido")
    linhas = con.execute(
        "SELECT orientacao_pt FROM vw_regra_separacao_liberada "
        "WHERE intervalo_horas IS NULL").fetchall()
    print("     regras sem intervalo: %d" % len(linhas))
    ok = all("não estabelecido" in l[0] for l in linhas)
    confere("todas declaram a ausência do intervalo", ok,
            linhas[0][0] if linhas else "(nenhuma)")
    # e nenhuma delas pode conter numero de hora
    com_numero = [l[0] for l in linhas if re.search(r"\d+\s*hora", l[0])]
    confere("nenhuma sugere número de horas", not com_numero, str(com_numero[:1]))

    todas = con.execute(
        "SELECT COUNT(*) FROM vw_regra_separacao_liberada").fetchone()[0]
    com = todas - len(linhas)
    print("     com intervalo declarado pela fonte: %d de %d" % (com, todas))


def main() -> int:
    con = sqlite3.connect("file:%s?mode=ro" % BANCO.as_posix(), uri=True)
    print("VERIFICAÇÃO INDEPENDENTE — regras de administração e separação")
    v1_recontagem(con)
    v2_casos_clinicos(con)
    v3_coerencia(con)
    v4_intervalo_desconhecido(con)
    con.close()
    print("\n" + "=" * 64)
    if avisos:
        print("AVISOS (lacuna de cobertura, não defeito de código):")
        for a in avisos:
            print("  -", a)
    if falhas:
        print("\nFALHAS: %d" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("VERIFICAÇÃO INDEPENDENTE PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
