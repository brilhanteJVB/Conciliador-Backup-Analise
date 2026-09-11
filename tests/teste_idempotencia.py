# -*- coding: utf-8 -*-
"""
IDEMPOTENCIA DA CARGA — rodar o pipeline de novo nao pode mudar nada.

POR QUE ESTE TESTE EXISTE
-------------------------
O modo incremental (`pipeline/executar_tudo.py` sem `--recriar`) nunca
funcionou: `20_substancias.py` abortava na primeira substancia ja existente, e
por isso o defeito ficou invisivel. Quando ele foi corrigido, apareceram
outros tres que so se manifestam na SEGUNDA execucao — duplicacao de
`regra_separacao`, de `auditoria_conflito` e de `carga`. Nenhum teste os
pegaria, porque nenhum rodava a carga duas vezes.

DUAS PARTES
-----------
1. UNITARIA, numa COPIA do banco: `abrir_carga`, `fechar_carga` e
   `inserir_unico` fazem o que prometem, inclusive recusar origem alterada.
2. INTEGRACAO, no banco de verdade: tira uma fotografia de todas as tabelas,
   roda os ETLs de novo e compara. Se alguma linha mudar, o teste falha e diz
   qual tabela — e a recuperacao e `pipeline/executar_tudo.py --recriar`.

A parte 2 leva ~20 s e NAO entra em `executar_tudo.py`: seria recursao, e o
lugar dela e a bateria deliberada. As garantias baratas que dela derivam ficam
travadas em `tests/teste_regressao.py`, que roda sempre.

Uso: python tests/teste_idempotencia.py [--rapido]
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "pipeline"))

BANCO = RAIZ / "database" / "conciliador.db"

ETAPAS = ["10_fontes.py", "20_substancias.py", "30_produtos.py", "40_atc.py",
          "50_regras_administracao.py", "55_regras_bula.py",
          "58_conflitos_administracao.py", "60_interacoes_substancia.py",
          "62_papel_farmacocinetico.py", "64_contraindicacoes_bula.py",
          "65_habitos_bula.py"]

falhas = []


def ok(desc, cond, detalhe=""):
    print("  [%s] %-56s %s" % ("OK " if cond else "FALHA", desc, detalhe))
    if not cond:
        falhas.append(desc)


def tabelas(con):
    return [n for (n,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def fotografia(con) -> dict:
    """Contagem e hash do conteudo de cada tabela."""
    foto = {}
    for t in tabelas(con):
        h = hashlib.sha256()
        n = 0
        for linha in con.execute("SELECT * FROM %s ORDER BY rowid" % t):
            h.update(repr(linha).encode("utf-8"))
            n += 1
        foto[t] = (n, h.hexdigest()[:16])
    return foto


# ------------------------------------------------------------ 1. unitaria

def unitario() -> None:
    print("\n1. UNITARIO — carga e insercao, numa copia do banco")
    tmp = Path(tempfile.mkdtemp()) / "copia.db"
    shutil.copy(BANCO, tmp)
    import _comum
    original = _comum.BANCO
    _comum.BANCO = tmp
    try:
        con = sqlite3.connect(tmp)
        con.execute("PRAGMA foreign_keys = ON")
        antes = con.execute("SELECT COUNT(*) FROM carga").fetchone()[0]

        # abrir_carga: reaproveita o lote quando nada mudou
        c1 = _comum.abrir_carga(con, "ANVISA - Medicamentos registrados",
                                "20_substancias.py",
                                "TA_CONSULTA_MEDICAMENTOS.CSV")
        c2 = _comum.abrir_carga(con, "ANVISA - Medicamentos registrados",
                                "20_substancias.py",
                                "TA_CONSULTA_MEDICAMENTOS.CSV")
        depois = con.execute("SELECT COUNT(*) FROM carga").fetchone()[0]
        ok("abrir_carga devolve o MESMO lote na segunda chamada", c1 == c2,
           "id %d" % c1)
        ok("abrir_carga nao cria linha nova", antes == depois,
           "%d -> %d" % (antes, depois))

        # fechar_carga nao reescreve lote ja fechado
        lidos_antes = con.execute(
            "SELECT registros_lidos, registros_inseridos FROM carga WHERE id=?",
            (c1,)).fetchone()
        _comum.fechar_carga(con, c1, 0, 0, 0, "reexecucao que nao inseriu nada")
        lidos_depois = con.execute(
            "SELECT registros_lidos, registros_inseridos FROM carga WHERE id=?",
            (c1,)).fetchone()
        ok("fechar_carga nao apaga os numeros do lote original",
           lidos_antes == lidos_depois, str(lidos_antes))

        # origem alterada e recusada, com mensagem que diz o que fazer
        con.execute("UPDATE carga SET hash_arquivo='OUTRO' WHERE id=?", (c1,))
        try:
            _comum.abrir_carga(con, "ANVISA - Medicamentos registrados",
                               "20_substancias.py",
                               "TA_CONSULTA_MEDICAMENTOS.CSV")
            ok("abrir_carga recusa origem alterada", False, "aceitou")
        except _comum.OrigemAlterada as e:
            ok("abrir_carga recusa origem alterada", True)
            ok("a mensagem manda usar --recriar", "--recriar" in str(e))
        con.execute("UPDATE carga SET hash_arquivo=NULL WHERE id=?", (c1,))

        # inserir_unico: insere uma vez, recupera na segunda
        sid, novo1 = _comum.inserir_unico(
            con, "item_nao_medicamentoso",
            dict(nome="__teste_idempotencia__",
                 chave_normalizada="__teste__", tipo="ALIMENTO"),
            "nome = ?", ("__teste_idempotencia__",))
        sid2, novo2 = _comum.inserir_unico(
            con, "item_nao_medicamentoso",
            dict(nome="__teste_idempotencia__",
                 chave_normalizada="__teste__", tipo="ALIMENTO"),
            "nome = ?", ("__teste_idempotencia__",))
        ok("inserir_unico insere na primeira vez", novo1 is True)
        ok("inserir_unico NAO insere na segunda", novo2 is False)
        ok("inserir_unico devolve o mesmo id", sid == sid2, "id %s" % sid)
        n = con.execute("SELECT COUNT(*) FROM item_nao_medicamentoso "
                        "WHERE nome='__teste_idempotencia__'").fetchone()[0]
        ok("uma linha, nao duas", n == 1)

        # clausula de recuperacao errada tem de gritar, nao devolver id errado
        try:
            _comum.inserir_unico(
                con, "item_nao_medicamentoso",
                dict(nome="__teste_idempotencia__",
                     chave_normalizada="__teste__", tipo="ALIMENTO"),
                "nome = ?", ("nao_existe_de_jeito_nenhum",))
            ok("inserir_unico grita se a clausula nao acha a linha", False,
               "devolveu id em silencio")
        except RuntimeError:
            ok("inserir_unico grita se a clausula nao acha a linha", True)
        con.close()
    finally:
        _comum.BANCO = original
        shutil.rmtree(tmp.parent, ignore_errors=True)


# --------------------------------------------------------- 2. integracao

def integracao() -> None:
    print("\n2. INTEGRACAO — rodar os 11 ETLs de novo nao muda uma linha")
    con = sqlite3.connect(BANCO)
    antes = fotografia(con)
    con.close()
    print("     fotografia de %d tabelas, %d linhas no total"
          % (len(antes), sum(n for n, _ in antes.values())))

    for etapa in ETAPAS:
        r = subprocess.run([sys.executable, str(RAIZ / "pipeline" / etapa)],
                           cwd=str(RAIZ), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode != 0:
            ok("reexecucao de %s termina sem erro" % etapa, False,
               (r.stderr or "").strip().splitlines()[-1:] or "")
            return
    ok("os 11 ETLs rodam de novo sem erro", True)

    con = sqlite3.connect(BANCO)
    depois = fotografia(con)
    con.close()

    mudou = [t for t in antes
             if antes[t] != depois.get(t)]
    for t in mudou:
        a, d = antes[t], depois.get(t, (0, ""))
        print("       %-26s %d -> %d linhas   hash %s -> %s"
              % (t, a[0], d[0], a[1], d[1]))
    ok("nenhuma tabela mudou de conteudo", not mudou,
       "%d tabela(s) mudaram" % len(mudou) if mudou
       else "%d tabelas identicas" % len(antes))
    if mudou:
        print("\n     RECUPERACAO: rode `pipeline/executar_tudo.py --recriar`.")


def main() -> int:
    print("=" * 74)
    print("IDEMPOTENCIA DA CARGA")
    print("=" * 74)
    if not BANCO.exists():
        print("banco nao existe — rode pipeline/executar_tudo.py --recriar")
        return 1
    unitario()
    if "--rapido" not in sys.argv:
        integracao()
    else:
        print("\n2. INTEGRACAO — pulada por --rapido")
    print("\n" + "=" * 74)
    if falhas:
        print("IDEMPOTENCIA FALHOU em %d verificacao(oes):" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("CARGA IDEMPOTENTE — reexecutar o pipeline nao muda nada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
