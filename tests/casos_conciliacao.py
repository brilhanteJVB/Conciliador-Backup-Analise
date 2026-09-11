# -*- coding: utf-8 -*-
"""
Fixtures de caso clinico para o motor de conciliacao.

REGRA, herdada de tests/casos_clinicos.py: nenhuma evidencia farmacologica e
inventada aqui. Os casos usam substancias reais do banco e as afirmacoes que
as fontes de fato carregaram. O que e sintetico e o PACIENTE — nome, rotina,
horarios, condicoes declaradas. Nunca a farmacologia.

Toda montagem acontece dentro de uma transacao desfeita no final
(`banco_temporario`), entao nada disto chega ao banco de producao.

As funcoes `achar_*` procuram no banco um exemplo REAL do que o teste precisa
e devolvem None quando nao existe. Um teste que nao acha o seu insumo se
declara PULADO em vez de passar por engano — teste que passa por ausencia de
dado e pior que teste que falha.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from casos_clinicos import (ROTINA_PADRAO, banco_temporario,  # noqa: E402,F401
                            criar_atendimento, substancia_por_nome)


# =====================================================================
# MONTAGEM DO ATENDIMENTO
# =====================================================================
def adicionar(con, atendimento_id, substancia_id, nome, *, lista="RELATADA",
              dose=1.0, unidade="comprimido", vezes=1, intervalo=None,
              horarios=(), continuo=1, prn=0, condicao=None, via="oral",
              origem="PRESCRITO", com_posologia=True, data_fim=None,
              reconhecimento=None):
    """Um item de farmacoterapia, com a LISTA a que pertence.

    `lista` e o que torna a conciliacao possivel: o mesmo farmaco na
    prescricao e no relato sao DUAS linhas, e parear as duas e o ato de
    conciliar.
    """
    cur = con.execute(
        "INSERT INTO atendimento_medicamento (atendimento_id, substancia_id, "
        "nome_relatado, origem, lista, reconhecimento, confianca_reconhecimento) "
        "VALUES (?,?,?,?,?,?,?)",
        (atendimento_id, substancia_id, nome, origem, lista,
         reconhecimento or ("NOME_EXATO" if substancia_id else "NAO_RECONHECIDO"),
         "ALTA" if substancia_id else None))
    am = cur.lastrowid
    if not com_posologia:
        return am
    cur = con.execute(
        "INSERT INTO posologia (atendimento_medicamento_id, dose_valor, "
        "dose_unidade, vezes_por_dia, intervalo_horas, via_administracao, "
        "uso_continuo, se_necessario, condicao_uso, data_fim_prevista) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (am, dose, unidade, vezes, intervalo, via,
         0 if data_fim else continuo, prn, condicao, data_fim))
    pid = cur.lastrowid
    for h in horarios:
        con.execute("INSERT INTO horario_administracao (posologia_id, hora, "
                    "definido_por) VALUES (?,?,'PACIENTE')", (pid, h))
    return am


def adicionar_condicao(con, atendimento_id, doenca_id=None, livre=None):
    pid = con.execute("SELECT paciente_id FROM atendimento WHERE id=?",
                      (atendimento_id,)).fetchone()[0]
    con.execute("INSERT INTO paciente_condicao (paciente_id, doenca_id, "
                "descricao_livre) VALUES (?,?,?)", (pid, doenca_id, livre))


def adicionar_alergia(con, atendimento_id, substancia_id=None, livre=None,
                      reacao=None, gravidade="NAO_INFORMADA"):
    pid = con.execute("SELECT paciente_id FROM atendimento WHERE id=?",
                      (atendimento_id,)).fetchone()[0]
    con.execute("INSERT INTO paciente_alergia (paciente_id, substancia_id, "
                "descricao_livre, reacao, gravidade) VALUES (?,?,?,?,?)",
                (pid, substancia_id, livre, reacao, gravidade))


def adicionar_habito(con, atendimento_id, habito, situacao="ATUAL",
                     quantidade=None, frequencia=None):
    pid = con.execute("SELECT paciente_id FROM atendimento WHERE id=?",
                      (atendimento_id,)).fetchone()[0]
    con.execute("INSERT OR REPLACE INTO paciente_habito (paciente_id, habito, "
                "situacao, quantidade, frequencia) VALUES (?,?,?,?,?)",
                (pid, habito, situacao, quantidade, frequencia))


def adicionar_item(con, atendimento_id, item_id, nome_relatado,
                   frequencia="DIARIO", horario=None):
    con.execute(
        "INSERT INTO atendimento_item (atendimento_id, item_id, nome_relatado, "
        "frequencia, horario_habitual) VALUES (?,?,?,?,?)",
        (atendimento_id, item_id, nome_relatado, frequencia, horario))


# =====================================================================
# BUSCA DE INSUMO REAL NO BANCO
# =====================================================================
def achar_par_interacao(con, gravidade="MAIOR", n_fontes=1, min_produtos=20):
    """(id_a, nome_a, id_b, nome_b) de um par que a fonte de fato afirma."""
    if n_fontes > 1:
        linha = con.execute(
            "SELECT i.substancia_a_id, sa.nome_dcb, i.substancia_b_id, sb.nome_dcb "
            "FROM interacao_substancia i "
            "JOIN substancia sa ON sa.id=i.substancia_a_id "
            "JOIN substancia sb ON sb.id=i.substancia_b_id "
            "GROUP BY 1,3 HAVING COUNT(DISTINCT i.fonte_id)>1 LIMIT 1").fetchone()
        return linha
    return con.execute(
        "SELECT i.substancia_a_id, sa.nome_dcb, i.substancia_b_id, sb.nome_dcb "
        "FROM interacao_substancia i "
        "JOIN substancia sa ON sa.id=i.substancia_a_id "
        "JOIN substancia sb ON sb.id=i.substancia_b_id "
        "WHERE i.gravidade=? AND sa.n_produtos_ativos>=? AND sb.n_produtos_ativos>=? "
        "ORDER BY sa.n_produtos_ativos+sb.n_produtos_ativos DESC LIMIT 1",
        (gravidade, min_produtos, min_produtos)).fetchone()


def achar_par_sem_gravidade(con):
    """Par que NENHUMA fonte graduou.

    O filtro tem de ser sobre o par inteiro, nao sobre a linha: filtrar
    `gravidade='NAO_DETERMINADA'` antes de agrupar devolve pares em que uma
    fonte se calou e a outra graduou — que e o caso oposto do que se quer
    testar. Foi assim que a primeira versao deste fixture reprovou o motor
    por um erro do proprio teste.
    """
    return con.execute(
        "SELECT i.substancia_a_id, sa.nome_dcb, i.substancia_b_id, sb.nome_dcb "
        "FROM interacao_substancia i "
        "JOIN substancia sa ON sa.id=i.substancia_a_id "
        "JOIN substancia sb ON sb.id=i.substancia_b_id "
        "WHERE i.gravidade='NAO_DETERMINADA' "
        "AND NOT EXISTS (SELECT 1 FROM interacao_substancia j "
        "  WHERE j.substancia_a_id=i.substancia_a_id "
        "    AND j.substancia_b_id=i.substancia_b_id "
        "    AND j.gravidade<>'NAO_DETERMINADA') "
        "ORDER BY sa.n_produtos_ativos DESC LIMIT 1").fetchone()


def achar_contraindicacao(con, relacao="CONTRAINDICADO", excluir_gestacao=True):
    """(substancia_id, nome, doenca_id, doenca) de uma contraindicacao real."""
    extra = ("AND d.nome NOT IN ('gravidez','lactação')" if excluir_gestacao else "")
    return con.execute(
        "SELECT i.substancia_id, s.nome_dcb, i.doenca_id, d.nome "
        "FROM interacao_doenca i JOIN substancia s ON s.id=i.substancia_id "
        "JOIN doenca d ON d.id=i.doenca_id "
        "WHERE i.relacao=? %s ORDER BY s.n_produtos_ativos DESC LIMIT 1" % extra,
        (relacao,)).fetchone()


def achar_interacao_item(con, tipo=None):
    """(substancia_id, nome, item_id, item, tipo, gravidade)."""
    filtro = "AND i.tipo=?" if tipo else ""
    args = (tipo,) if tipo else ()
    return con.execute(
        "SELECT ii.substancia_id, s.nome_dcb, ii.item_id, i.nome, i.tipo, "
        "ii.gravidade FROM interacao_item ii "
        "JOIN substancia s ON s.id=ii.substancia_id "
        "JOIN item_nao_medicamentoso i ON i.id=ii.item_id "
        "WHERE 1=1 %s ORDER BY s.n_produtos_ativos DESC LIMIT 1" % filtro,
        args).fetchone()


def achar_interacao_habito(con, habito="ALCOOL"):
    return con.execute(
        "SELECT h.substancia_id, s.nome_dcb, h.habito, h.gravidade "
        "FROM interacao_habito h JOIN substancia s ON s.id=h.substancia_id "
        "WHERE h.habito=? ORDER BY s.n_produtos_ativos DESC LIMIT 1",
        (habito,)).fetchone()


def achar_par_cyp(con, potencia="FORTE"):
    """(id_inibidor, nome, id_substrato, nome, sistema, papel)."""
    return con.execute(
        "SELECT a.substancia_id, sa.nome_dcb, b.substancia_id, sb.nome_dcb, "
        "a.sistema, a.papel FROM papel_farmacocinetico a "
        "JOIN papel_farmacocinetico b ON b.sistema=a.sistema AND b.papel='SUBSTRATO' "
        "JOIN substancia sa ON sa.id=a.substancia_id "
        "JOIN substancia sb ON sb.id=b.substancia_id "
        "WHERE a.papel IN ('INIBIDOR','INDUTOR') AND a.potencia=? "
        "AND a.substancia_id <> b.substancia_id LIMIT 1", (potencia,)).fetchone()


def achar_par_cyp_tambem_documentado(con):
    """O caso E da especificacao: o MESMO par achado por dois mecanismos.

    Um par que e simultaneamente (a) interacao documentada em fonte e (b)
    dedutivel pelo cruzamento inibidor x substrato da tabela da FDA.
    """
    return con.execute(
        "SELECT a.substancia_id, sa.nome_dcb, b.substancia_id, sb.nome_dcb, "
        "a.sistema FROM papel_farmacocinetico a "
        "JOIN papel_farmacocinetico b ON b.sistema=a.sistema AND b.papel='SUBSTRATO' "
        "JOIN substancia sa ON sa.id=a.substancia_id "
        "JOIN substancia sb ON sb.id=b.substancia_id "
        "WHERE a.papel IN ('INIBIDOR','INDUTOR') AND a.substancia_id<>b.substancia_id "
        "AND EXISTS (SELECT 1 FROM interacao_substancia i "
        "            WHERE i.substancia_a_id=MIN(a.substancia_id,b.substancia_id) "
        "              AND i.substancia_b_id=MAX(a.substancia_id,b.substancia_id)) "
        "LIMIT 1").fetchone()


def achar_duplicidade_atc(con, min_produtos=25):
    """(codigo_atc4, [(id, nome), (id, nome)]) de duas substancias do mesmo
    4o nivel ATC — duplicidade terapeutica real."""
    linha = con.execute(
        "SELECT SUBSTR(atc_codigo,1,5) c FROM substancia "
        "WHERE LENGTH(atc_codigo)>=5 AND n_produtos_ativos>? "
        "GROUP BY 1 HAVING COUNT(*)>1 LIMIT 1", (min_produtos,)).fetchone()
    if not linha:
        return None
    subs = con.execute(
        "SELECT id, nome_dcb FROM substancia WHERE SUBSTR(atc_codigo,1,5)=? "
        "AND n_produtos_ativos>? LIMIT 2", (linha[0], min_produtos)).fetchall()
    return linha[0], subs


def achar_alergia_cruzada(con, min_produtos=30):
    """Duas substancias distintas do mesmo 4o nivel ATC, para o teste de
    reatividade cruzada por classe."""
    return con.execute(
        "SELECT a.id, a.nome_dcb, b.id, b.nome_dcb, SUBSTR(a.atc_codigo,1,5) "
        "FROM substancia a JOIN substancia b "
        "  ON SUBSTR(a.atc_codigo,1,5)=SUBSTR(b.atc_codigo,1,5) AND a.id<b.id "
        "WHERE a.n_produtos_ativos>? AND b.n_produtos_ativos>? "
        "AND LENGTH(a.atc_codigo)>=5 LIMIT 1",
        (min_produtos, min_produtos)).fetchone()


def achar_substancia_sem_interacao(con):
    """Substancia com produto ativo e ZERO interacoes: o caso de cobertura."""
    return con.execute(
        "SELECT s.id, s.nome_dcb FROM substancia s WHERE s.n_produtos_ativos>10 "
        "AND NOT EXISTS (SELECT 1 FROM interacao_substancia i "
        "  WHERE i.substancia_a_id=s.id OR i.substancia_b_id=s.id) "
        "ORDER BY s.n_produtos_ativos DESC LIMIT 1").fetchone()


def achar_regra_jejum(con):
    return con.execute(
        "SELECT s.id, s.nome_dcb FROM regra_administracao r "
        "JOIN substancia s ON s.id=r.substancia_id WHERE r.tipo='JEJUM' "
        "ORDER BY s.n_produtos_ativos DESC LIMIT 1").fetchone()
