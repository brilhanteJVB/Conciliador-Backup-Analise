# -*- coding: utf-8 -*-
"""
Casos clinicos sinteticos para testar o motor de horarios.

REGRA: nenhuma evidencia farmacologica e inventada aqui. Os casos usam
substancias reais do banco e as regras que a Fase 3 carregou das fontes.
O que e sintetico e o PACIENTE (nome, rotina, horarios) -- nunca a
farmacologia.

Os casos sao montados dentro de uma transacao e desfeitos ao final, para
nao sujar o banco de producao.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BANCO = RAIZ / "database" / "conciliador.db"

ROTINA_PADRAO = {
    "ACORDAR": "06:30", "CAFE_MANHA": "07:00", "ALMOCO": "12:00",
    "LANCHE_TARDE": "16:00", "JANTAR": "19:30", "DORMIR": "22:30",
}


@contextmanager
def banco_temporario():
    """Conexao que desfaz tudo no final."""
    con = sqlite3.connect(BANCO)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
    finally:
        con.rollback()
        con.close()


def substancia_por_nome(con, termo):
    r = con.execute(
        "SELECT id, nome_dcb FROM substancia WHERE nome_dcb = ? "
        "OR nome_dcb LIKE ? ORDER BY length(nome_dcb) LIMIT 1",
        (termo, termo + "%")).fetchone()
    return r


def substancia_com_regra(con, tipo):
    """Qualquer substancia que realmente tenha a regra pedida."""
    return con.execute(
        "SELECT s.id, s.nome_dcb FROM regra_administracao r "
        "JOIN substancia s ON s.id = r.substancia_id "
        "WHERE r.tipo = ? ORDER BY s.n_produtos_ativos DESC LIMIT 1",
        (tipo,)).fetchone()


def substancia_com_separacao(con, com_intervalo=True, alvo_tipo="ITEM"):
    """Uma regra de separacao real, do tipo de alvo pedido.

    O tipo importa: separacao contra ITEM se verifica olhando os
    suplementos que o paciente declarou; contra CLASSE_ATC se verifica
    olhando os outros MEDICAMENTOS dele. Misturar os dois no teste produz
    falso negativo -- foi o que aconteceu na primeira execucao.
    """
    sql = ("SELECT s.id, s.nome_dcb, r.intervalo_horas, r.alvo_tipo, "
           "COALESCE(i.nome, c.nome_pt) "
           "FROM regra_separacao r JOIN substancia s ON s.id = r.substancia_id "
           "LEFT JOIN item_nao_medicamentoso i ON i.id = r.alvo_item_id "
           "LEFT JOIN classe_atc c ON c.codigo = r.alvo_classe_atc "
           "WHERE r.alvo_tipo = ? AND r.intervalo_horas IS %s NULL LIMIT 1"
           % ("NOT" if com_intervalo else ""))
    return con.execute(sql, (alvo_tipo,)).fetchone()


def criar_atendimento(con, codigo, rotina=None):
    cur = con.execute("INSERT INTO paciente (nome, data_nascimento, sexo, "
                      "peso_kg) VALUES (?,?,?,?)",
                      ("Paciente de teste " + codigo, "1960-01-01", "F", 70.0))
    pid = cur.lastrowid
    cur = con.execute("INSERT INTO atendimento (paciente_id, codigo, "
                      "farmaceutico) VALUES (?,?,?)",
                      (pid, codigo, "teste automatizado"))
    aid = cur.lastrowid
    for evento, hora in (rotina if rotina is not None else ROTINA_PADRAO).items():
        con.execute("INSERT INTO rotina_paciente (atendimento_id, evento, hora) "
                    "VALUES (?,?,?)", (aid, evento, hora))
    return aid


def adicionar_medicamento(con, atendimento_id, substancia_id, nome,
                          dose=1.0, unidade="comprimido", vezes=1,
                          intervalo=None, horarios=(), continuo=1,
                          prn=0, condicao=None, via="oral", origem="PRESCRITO"):
    cur = con.execute(
        "INSERT INTO atendimento_medicamento (atendimento_id, substancia_id, "
        "nome_relatado, origem, reconhecimento, confianca_reconhecimento) "
        "VALUES (?,?,?,?,?,?)",
        (atendimento_id, substancia_id, nome, origem,
         "NOME_EXATO" if substancia_id else "NAO_RECONHECIDO",
         "ALTA" if substancia_id else None))
    am = cur.lastrowid
    cur = con.execute(
        "INSERT INTO posologia (atendimento_medicamento_id, dose_valor, "
        "dose_unidade, vezes_por_dia, intervalo_horas, via_administracao, "
        "uso_continuo, se_necessario, condicao_uso) VALUES (?,?,?,?,?,?,?,?,?)",
        (am, dose, unidade, vezes, intervalo, via, continuo, prn, condicao))
    pid = cur.lastrowid
    for h in horarios:
        con.execute("INSERT INTO horario_administracao (posologia_id, hora, "
                    "definido_por) VALUES (?,?,'PACIENTE')", (pid, h))
    return am


def adicionar_item(con, atendimento_id, nome_item, horario=None,
                   frequencia="DIARIO"):
    r = con.execute("SELECT id FROM item_nao_medicamentoso WHERE nome=?",
                    (nome_item,)).fetchone()
    con.execute(
        "INSERT INTO atendimento_item (atendimento_id, item_id, nome_relatado, "
        "frequencia, horario_habitual) VALUES (?,?,?,?,?)",
        (atendimento_id, r[0] if r else None, nome_item, frequencia, horario))


def sem_posologia(con, atendimento_id, substancia_id, nome):
    """Medicamento registrado sem posologia: caso comum de balcao."""
    con.execute(
        "INSERT INTO atendimento_medicamento (atendimento_id, substancia_id, "
        "nome_relatado, origem, reconhecimento) VALUES (?,?,?,?,?)",
        (atendimento_id, substancia_id, nome, "AUTOMEDICACAO", "NOME_EXATO"))
