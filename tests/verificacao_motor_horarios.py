# -*- coding: utf-8 -*-
"""
VERIFICACAO 2 (independente) do motor de horarios.

Nao repete os casos clinicos. Procura defeito por outros quatro caminhos:

  V1  Implementacao ALTERNATIVA do calculo de distancia entre horarios,
      escrita de outro jeito (varredura minuto a minuto), comparada com a
      do motor em todos os pares de um dia inteiro.
  V2  Invariantes que independem do caso: todo conflito tem de citar
      horarios que existem na agenda, toda separacao afirmada tem de ter
      regra correspondente no banco, nenhum intervalo pode aparecer sem
      estar na fonte.
  V3  Consulta independente ao banco: para cada conflito de separacao, ir
      ao banco por SQL proprio e conferir que a regra existe com aquele
      intervalo.
  V4  Propriedade: agenda sem regra nenhuma e com horarios bem espacados
      nao pode gerar conflito. Ausencia de dado nao pode virar alerta.

Uso: python tests/verificacao_motor_horarios.py
"""
from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "rules"))
sys.path.insert(0, str(RAIZ / "tests"))

from casos_clinicos import (adicionar_item, adicionar_medicamento,  # noqa: E402
                            banco_temporario, criar_atendimento,
                            substancia_com_separacao, substancia_por_nome)
from motor_horarios import (distancia_minutos, montar_agenda,  # noqa: E402
                            para_hora, para_minutos)

falhas = []


def confere(desc, ok, detalhe=""):
    print("  [%s] %s %s" % ("OK " if ok else "FALHA", desc, detalhe))
    if not ok:
        falhas.append(desc)


# ------------------------------------------------------------------ V1
def distancia_por_varredura(a: str, b: str):
    """Mesma pergunta, algoritmo diferente.

    Em vez de aritmetica modular, avanca minuto a minuto a partir de A nos
    dois sentidos ate encontrar B. Lento de proposito: o objetivo e nao
    compartilhar nenhuma linha de codigo com a implementacao do motor.
    """
    ma, mb = para_minutos(a), para_minutos(b)
    if ma is None or mb is None:
        return None
    frente = 0
    p = ma
    while p != mb and frente <= 1440:
        p = (p + 1) % 1440
        frente += 1
    tras = 0
    p = ma
    while p != mb and tras <= 1440:
        p = (p - 1) % 1440
        tras += 1
    return min(frente, tras)


def v1_calculo_alternativo():
    print("\nV1 — implementação alternativa do cálculo de distância")
    divergencias = []
    horas = [para_hora(m) for m in range(0, 1440, 7)]     # 206 horários
    for a, b in itertools.combinations(horas, 2):
        d1 = distancia_minutos(a, b)
        d2 = distancia_por_varredura(a, b)
        if d1 != d2:
            divergencias.append((a, b, d1, d2))
    confere("as duas implementações concordam em %d pares"
            % len(list(itertools.combinations(horas, 2))),
            not divergencias, str(divergencias[:3]))

    # a volta do dia e o caso que uma subtracao ingenua erra
    confere("23:30 e 00:30 distam 60 min", distancia_minutos("23:30", "00:30") == 60,
            str(distancia_minutos("23:30", "00:30")))
    confere("mesma hora dista 0", distancia_minutos("08:00", "08:00") == 0)
    confere("hora inválida devolve None",
            distancia_minutos("25:00", "08:00") is None)
    confere("texto livre devolve None",
            distancia_minutos("de manhã", "08:00") is None)


# ------------------------------------------------------------------ V2
def v2_invariantes(con):
    print("\nV2 — invariantes independentes do caso")
    s = substancia_por_nome(con, "levotiroxina")
    sep = substancia_com_separacao(con, com_intervalo=True, alvo_tipo="ITEM")
    a = criar_atendimento(con, "V-01")
    adicionar_medicamento(con, a, s[0], "Puran T4", 50, "mcg", 1,
                          horarios=("07:00",))
    adicionar_medicamento(con, a, sep[0], sep[1], 1, "comprimido", 2,
                          intervalo=12, horarios=("08:00", "13:00"))
    adicionar_item(con, a, sep[4], horario="08:00")
    ag = montar_agenda(con, a)

    horas_agenda = {e.hora for e in ag.eventos if e.hora}
    horas_rotina = set(ag.rotina.values())
    horas_itens = {h for (h,) in con.execute(
        "SELECT horario_habitual FROM atendimento_item WHERE atendimento_id=? "
        "AND horario_habitual IS NOT NULL", (a,))}
    conhecidas = horas_agenda | horas_rotina | horas_itens
    fora = [(c.tipo, h) for c in ag.conflitos for h in c.horarios
            if h not in conhecidas]
    confere("todo horário citado em conflito existe na agenda ou na rotina",
            not fora, str(fora[:3]))

    confere("todo conflito tem justificativa não vazia",
            all(c.justificativa.strip() for c in ag.conflitos))
    validas = {"CONFLITO_CONFIRMADO", "POSSIVEL_CONFLITO",
               "INFORMACAO_INSUFICIENTE", "REGRA_DESCONHECIDA",
               "SEM_CONFLITO_IDENTIFICADO"}
    confere("toda classificação está no vocabulário",
            all(c.classificacao in validas for c in ag.conflitos),
            str({c.classificacao for c in ag.conflitos} - validas))

    # nenhum intervalo pode ser afirmado sem estar na fonte
    inventados = []
    for c in ag.conflitos:
        if c.intervalo_exigido is None:
            continue
        existe = con.execute(
            "SELECT 1 FROM regra_separacao WHERE intervalo_horas = ? LIMIT 1",
            (c.intervalo_exigido,)).fetchone()
        if not existe and c.tipo.startswith("SEPARACAO"):
            inventados.append((c.tipo, c.intervalo_exigido))
    confere("nenhum intervalo de separação sem origem no banco",
            not inventados, str(inventados))

    # toda regra citada no evento tem de vir da view liberada
    for e in ag.eventos:
        if e.regra_administracao:
            ok = con.execute(
                "SELECT 1 FROM vw_regra_administracao_liberada r "
                "JOIN substancia s ON s.id=r.substancia_id "
                "WHERE s.nome_dcb=? AND r.tipo=?",
                (e.substancia, e.regra_administracao)).fetchone()
            confere("regra de %s vem da view liberada" % e.medicamento[:18],
                    bool(ok), e.regra_administracao)

    # extracao automatica nunca some
    com_conf = [e for e in ag.eventos if e.regra_administracao]
    confere("toda regra aplicada carrega a confiança da extração",
            all(e.confianca_extracao for e in com_conf),
            str([(e.medicamento, e.confianca_extracao) for e in com_conf][:2]))


# ------------------------------------------------------------------ V3
def v3_conferencia_sql(con):
    print("\nV3 — conferência por consulta SQL independente")
    sep = substancia_com_separacao(con, com_intervalo=True, alvo_tipo="ITEM")
    a = criar_atendimento(con, "V-02")
    adicionar_medicamento(con, a, sep[0], sep[1], 1, "comprimido", 1,
                          horarios=("08:00",))
    adicionar_item(con, a, sep[4], horario="08:30")
    ag = montar_agenda(con, a)

    conf = [c for c in ag.conflitos if c.tipo == "SEPARACAO_NAO_RESPEITADA"]
    confere("conflito de separação produzido", bool(conf))
    for c in conf:
        linha = con.execute(
            "SELECT r.intervalo_horas, i.nome, f.nome "
            "FROM regra_separacao r "
            "JOIN item_nao_medicamentoso i ON i.id = r.alvo_item_id "
            "JOIN fonte f ON f.id = r.fonte_id "
            "WHERE r.substancia_id = ? AND i.nome = ?",
            (sep[0], sep[4])).fetchone()
        confere("regra existe no banco com o mesmo intervalo",
                bool(linha) and linha[0] == c.intervalo_exigido,
                "banco=%s conflito=%s" % (linha[0] if linha else None,
                                          c.intervalo_exigido))
        confere("fonte do conflito bate com a do banco",
                bool(linha) and linha[2] == c.fonte,
                "banco=%s conflito=%s" % (linha[2] if linha else None, c.fonte))
        # distancia recalculada aqui, sem usar o motor
        d = distancia_por_varredura("08:00", "08:30")
        confere("intervalo observado confere com cálculo externo",
                abs(c.intervalo_observado - d / 60.0) < 0.01,
                "motor=%s externo=%.2f" % (c.intervalo_observado, d / 60.0))


# ------------------------------------------------------------------ V4
def v4_propriedade(con):
    print("\nV4 — propriedade: sem regra e sem proximidade, sem conflito")
    # substancia sem nenhuma regra de administracao nem de separacao
    livre = con.execute(
        "SELECT s.id, s.nome_dcb FROM substancia s "
        "WHERE NOT EXISTS (SELECT 1 FROM regra_administracao r "
        "                  WHERE r.substancia_id = s.id) "
        "AND NOT EXISTS (SELECT 1 FROM regra_separacao p "
        "                WHERE p.substancia_id = s.id) "
        "AND s.n_produtos_ativos > 5 LIMIT 1").fetchone()
    if not livre:
        print("     (nenhuma substância sem regra; propriedade não testável)")
        return
    a = criar_atendimento(con, "V-03")
    adicionar_medicamento(con, a, livre[0], livre[1], 1, "comprimido", 2,
                          intervalo=12, horarios=("08:00", "20:00"))
    ag = montar_agenda(con, a)
    confere("substância sem regra não gera conflito",
            not ag.conflitos, str([c.tipo for c in ag.conflitos]))
    confere("mas a agenda foi montada", len(ag.eventos) == 2)

    # A rotina padrao dos casos e acordar 06:30 / dormir 22:30. Horarios
    # dentro dessa janela nao podem gerar conflito nenhum para uma
    # substancia sem regra. Fora dela, HORARIO_FORA_DA_ROTINA e um acerto,
    # nao falso positivo: a primeira versao deste teste sorteava a partir
    # das 06:00 e acusava o motor por detectar corretamente.
    print("     teste aleatorio: 60 agendas dentro da janela acordada")
    random.seed(20260909)
    inesperados = []
    for i in range(60):
        h1 = random.randint(7, 21)
        a = criar_atendimento(con, "V-R%02d" % i)
        adicionar_medicamento(con, a, livre[0], livre[1], 1, "comprimido", 1,
                              horarios=("%02d:00" % h1,))
        ag = montar_agenda(con, a)
        if ag.conflitos:
            inesperados.append((h1, [c.tipo for c in ag.conflitos]))
    confere("nenhuma agenda dentro da rotina gerou conflito sem regra",
            not inesperados, str(inesperados[:2]))

    print("     fora da janela, o motor TEM de acusar")
    nao_detectou = []
    for h1 in (3, 4, 23):
        a = criar_atendimento(con, "V-F%02d" % h1)
        adicionar_medicamento(con, a, livre[0], livre[1], 1, "comprimido", 1,
                              horarios=("%02d:00" % h1,))
        ag = montar_agenda(con, a)
        if "HORARIO_FORA_DA_ROTINA" not in [c.tipo for c in ag.conflitos]:
            nao_detectou.append(h1)
    confere("horario fora da rotina e sempre detectado",
            not nao_detectou, str(nao_detectou))


def main() -> int:
    print("VERIFICAÇÃO INDEPENDENTE — motor de horários")
    v1_calculo_alternativo()
    with banco_temporario() as con:
        v2_invariantes(con)
        v3_conferencia_sql(con)
        v4_propriedade(con)
    print("\n" + "=" * 66)
    if falhas:
        print("FALHAS: %d" % len(falhas))
        for f in falhas:
            print("  -", f)
        return 1
    print("VERIFICAÇÃO INDEPENDENTE PASSOU")
    return 0


if __name__ == "__main__":
    sys.exit(main())
