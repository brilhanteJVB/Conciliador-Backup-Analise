# -*- coding: utf-8 -*-
"""
VERIFICACAO 1 — FUNCIONAL — motor de conciliacao (Fase 5).

Casos clinicos sinteticos sobre farmacologia REAL do banco. O paciente e
inventado; a evidencia farmacologica, nunca.

Cobre a bateria exigida pela especificacao (secao 16) e os sete casos
dificeis (secao 17), que foram escritos para revelar erro de arquitetura, nao
para passar.

DOIS CASOS USAM ANDAIME DE TESTE, e isso esta declarado onde acontece:
o caso B (fontes discordantes) e o caso de conflito de gravidade inserem uma
segunda afirmacao de uma fonte real DENTRO da transacao desfeita. O motivo e
medido e esta no relatorio: **hoje o acervo nao tem nenhum conflito real entre
fontes**, porque das duas bases de interacao so uma gradua gravidade, e as
duas bases de regra de administracao quase nao se sobrepoem. Sem o andaime, a
maquinaria de conflito ficaria sem teste — o que seria pior do que declarar
que o cenario foi construido.

Uso: python tests/teste_motor_conciliacao.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tests"))
sys.path.insert(0, str(RAIZ / "rules"))

from casos_conciliacao import (ROTINA_PADRAO, achar_alergia_cruzada,  # noqa: E402
                               achar_contraindicacao, achar_duplicidade_atc,
                               achar_interacao_habito, achar_interacao_item,
                               achar_par_cyp, achar_par_interacao,
                               achar_par_sem_gravidade, achar_regra_jejum,
                               achar_substancia_sem_interacao, adicionar,
                               adicionar_alergia, adicionar_condicao,
                               adicionar_habito, adicionar_item,
                               banco_temporario, criar_atendimento)
from casos_clinicos import substancia_com_separacao  # noqa: E402
from motor_conciliacao import conciliar_atendimento  # noqa: E402

RESULTADOS = []


def registra(nome, ok, detalhe="", pulado=False):
    RESULTADOS.append((nome, ok, detalhe, pulado))
    marca = "PULADO" if pulado else ("OK  " if ok else "ERRO")
    print("   %-6s %-46s %s" % (marca, nome[:46], detalhe[:78]))


def acha(res, tipo=None, subtipo=None, prioridade=None, incluir_agrupados=False):
    fonte = list(res.achados) + (list(res.achados_agrupados)
                                 if incluir_agrupados else [])
    return [a for a in fonte
            if (tipo is None or a.tipo == tipo)
            and (subtipo is None or a.subtipo == subtipo)
            and (prioridade is None or a.prioridade == prioridade)]


# =====================================================================
# BATERIA DA SECAO 16
# =====================================================================
def caso_01_interacao(con):
    par = achar_par_interacao(con, "MAIOR")
    if not par:
        return registra("01 interação medicamento × medicamento", False,
                        "nenhum par MAIOR no banco", pulado=True)
    a, na, b, nb = par
    aid = criar_atendimento(con, "C01")
    adicionar(con, aid, a, na, horarios=("08:00",))
    adicionar(con, aid, b, nb, horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    achados = acha(res, "FARMACO_FARMACO")
    ok = (len(achados) == 1 and achados[0].gravidade_fonte == "MAIOR"
          and achados[0].prioridade == "ALTO")
    registra("01 interação medicamento × medicamento", ok,
             "%s × %s → %s/%s" % (na, nb, achados[0].prioridade if achados
                                  else "-", achados[0].gravidade_fonte
                                  if achados else "-"))


def caso_02_alergia(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, _b, _nb = par
    aid = criar_atendimento(con, "C02")
    adicionar(con, aid, a, na, horarios=("08:00",))
    adicionar_alergia(con, aid, substancia_id=a, reacao="urticária",
                      gravidade="MODERADA")
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_ALERGIA", "SUBSTANCIA_EXATA")
    ok = len(ach) == 1 and ach[0].prioridade == "CRITICO"
    registra("02 alergia à substância em uso", ok,
             "%s → %s" % (na, ach[0].prioridade if ach else "-"))


def caso_02b_alergia_cruzada(con):
    par = achar_alergia_cruzada(con)
    if not par:
        return registra("02b alergia por classe ATC", False, "sem par", pulado=True)
    ida, na, idb, nb, atc = par
    aid = criar_atendimento(con, "C02B")
    adicionar(con, aid, ida, na, horarios=("08:00",))
    adicionar_alergia(con, aid, substancia_id=idb, reacao="exantema")
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_ALERGIA", "MESMA_CLASSE_ATC")
    ok = (len(ach) == 1 and ach[0].prioridade == "ALTO"
          and ach[0].natureza == "POSSIVEL")
    registra("02b alergia por classe ATC (possível)", ok,
             "%s ~ %s (%s) → %s/%s" % (na, nb, atc,
                                       ach[0].prioridade if ach else "-",
                                       ach[0].natureza if ach else "-"))


def caso_03_contraindicacao(con):
    ci = achar_contraindicacao(con)
    if not ci:
        return registra("03 contraindicação por condição", False,
                        "sem contraindicação carregada", pulado=True)
    sid, nome, did, doenca = ci
    aid = criar_atendimento(con, "C03")
    adicionar(con, aid, sid, nome, horarios=("08:00",))
    adicionar_condicao(con, aid, doenca_id=did)
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_DOENCA")
    # A extracao e por regex e nao foi revisada: a confianca e BAIXA e a
    # prioridade cai de ALTO para MODERADO. Isso e o comportamento correto.
    ok = (len(ach) == 1 and ach[0].subtipo == "CONTRAINDICADO"
          and ach[0].confianca_sistema == "BAIXA"
          and ach[0].prioridade == "MODERADO"
          and ach[0].status_informacao == "EXTRAIDO_AUTOMATICAMENTE"
          and ach[0].trecho)
    registra("03 contraindicação por condição", ok,
             "%s + %s → %s (conf %s, %s)"
             % (nome, doenca, ach[0].prioridade if ach else "-",
                ach[0].confianca_sistema if ach else "-",
                ach[0].status_informacao if ach else "-"))


def caso_04_duplicidade(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, _b, _nb = par
    aid = criar_atendimento(con, "C04")
    adicionar(con, aid, a, na + " 10 mg", horarios=("08:00",))
    adicionar(con, aid, a, na + " genérico", horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "DUPLICIDADE", "MESMA_SUBSTANCIA")
    ok = len(ach) == 1 and ach[0].prioridade == "ALTO"
    registra("04 duplicidade da mesma substância", ok,
             "%s duas vezes → %s" % (na, ach[0].prioridade if ach else "-"))


def caso_04b_duplicidade_terapeutica(con):
    dup = achar_duplicidade_atc(con)
    if not dup:
        return registra("04b duplicidade terapêutica (ATC 4)", False,
                        "sem grupo", pulado=True)
    atc, subs = dup
    aid = criar_atendimento(con, "C04B")
    for sid, nome in subs:
        adicionar(con, aid, sid, nome, horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "DUPLICIDADE", "MESMA_CLASSE_ATC4")
    ok = len(ach) == 1 and ach[0].prioridade == "MODERADO"
    registra("04b duplicidade terapêutica (ATC 4)", ok,
             "%s: %s → %s" % (atc, " + ".join(n for _i, n in subs),
                              ach[0].prioridade if ach else "-"))


def caso_05_dose_diferente(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, _b, _nb = par
    aid = criar_atendimento(con, "C05")
    adicionar(con, aid, a, na, lista="PRESCRITA", dose=10.0, unidade="mg",
              vezes=1, horarios=("08:00",))
    adicionar(con, aid, a, na, lista="RELATADA", dose=20.0, unidade="mg",
              vezes=1, horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    div = [p for p in res.divergencias if p.tipo_divergencia == "DOSE_DIFERENTE"]
    ach = acha(res, "DIVERGENCIA_CONCILIACAO", "DOSE_DIFERENTE")
    ok = (len(div) == 1 and len(ach) == 1
          and div[0].valor_prescrito == "10 mg"
          and div[0].valor_relatado == "20 mg"
          and div[0].intencionalidade == "NAO_DETERMINADA")
    registra("05 diferença de dose (prescrito × relatado)", ok,
             "%s: %s vs %s" % (na, div[0].valor_prescrito if div else "-",
                               div[0].valor_relatado if div else "-"))


def caso_06_frequencia_diferente(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, _b, _nb = par
    aid = criar_atendimento(con, "C06")
    adicionar(con, aid, a, na, lista="PRESCRITA", vezes=2,
              horarios=("08:00", "20:00"))
    adicionar(con, aid, a, na, lista="RELATADA", vezes=1, horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    tipos = {p.tipo_divergencia for p in res.divergencias}
    ok = "FREQUENCIA_DIFERENTE" in tipos and "HORARIO_DIFERENTE" in tipos
    registra("06 diferença de frequência e de horário", ok,
             "divergências: %s" % ", ".join(sorted(t for t in tipos if t)))


def caso_07_conflito_horario(con):
    sep = substancia_com_separacao(con, com_intervalo=True, alvo_tipo="ITEM")
    if not sep:
        return registra("07 conflito de horário (separação × item)", False,
                        "sem regra de separação com intervalo", pulado=True)
    sid, nome, intervalo, _tipo, alvo = sep
    aid = criar_atendimento(con, "C07")
    adicionar(con, aid, sid, nome, horarios=("08:00",))
    item = con.execute("SELECT id FROM item_nao_medicamentoso WHERE nome=?",
                       (alvo,)).fetchone()
    adicionar_item(con, aid, item[0] if item else None, alvo, horario="08:15")
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "CONFLITO_HORARIO", "SEPARACAO_NAO_RESPEITADA")
    x = ach[0] if ach else None
    # A base do conflito e MODERADO. TODAS as 71 regras de separacao do banco
    # sao extracao por regex nao revisada, entao a confianca do sistema e
    # BAIXA e a prioridade desce um degrau, com o motivo escrito na
    # justificativa. Exigir MODERADO aqui seria exigir do sistema que
    # ignorasse a propria limitacao — foi o que a primeira versao deste teste
    # fez, e o errado era o teste.
    ok = (x is not None and x.classificacao == "CONFIRMADO"
          and ((x.confianca_sistema == "BAIXA" and x.prioridade == "BAIXO"
                and "Rebaixado" in x.justificativa_prioridade)
               or (x.confianca_sistema != "BAIXA" and x.prioridade == "MODERADO")))
    registra("07 conflito de horário (separação × item)", ok,
             "%s × %s (%gh) → %s, confiança %s"
             % (nome, alvo, intervalo, x.prioridade if x else "-",
                x.confianca_sistema if x else "-"))


def caso_08_conflito_refeicao(con):
    jej = achar_regra_jejum(con)
    if not jej:
        return registra("08 conflito com refeição (jejum)", False,
                        "sem regra de jejum", pulado=True)
    sid, nome = jej
    aid = criar_atendimento(con, "C08")
    # Rotina padrao: cafe da manha as 07:00. Tomar em jejum as 07:05 conflita.
    adicionar(con, aid, sid, nome, horarios=("07:05",))
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "CONFLITO_HORARIO", "JEJUM_PROXIMO_DE_REFEICAO")
    ok = len(ach) == 1
    registra("08 conflito com refeição (jejum × café)", ok,
             "%s às 07:05, café às 07:00 → %s"
             % (nome, ach[0].prioridade if ach else "não detectado"))


def caso_09_separacao_classe_atc(con):
    sep = substancia_com_separacao(con, com_intervalo=True, alvo_tipo="CLASSE_ATC")
    if not sep:
        return registra("09 separação por classe ATC", False, "sem regra",
                        pulado=True)
    sid, nome, intervalo, _t, classe = sep
    codigo = con.execute("SELECT codigo FROM classe_atc WHERE nome_pt=? OR "
                         "nome_en=? LIMIT 1", (classe, classe)).fetchone()
    if not codigo:
        return registra("09 separação por classe ATC", False, "classe sem código",
                        pulado=True)
    outro = con.execute("SELECT id, nome_dcb FROM substancia WHERE atc_codigo "
                        "LIKE ? AND id<>? LIMIT 1",
                        (codigo[0] + "%", sid)).fetchone()
    if not outro:
        return registra("09 separação por classe ATC", False,
                        "nenhuma substância na classe", pulado=True)
    aid = criar_atendimento(con, "C09")
    adicionar(con, aid, sid, nome, horarios=("08:00",))
    adicionar(con, aid, outro[0], outro[1], horarios=("08:10",))
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "CONFLITO_HORARIO", "SEPARACAO_NAO_RESPEITADA")
    ok = len(ach) >= 1
    registra("09 separação por classe ATC", ok,
             "%s × %s (%s) → %d achado(s)" % (nome, outro[1], classe, len(ach)))


def caso_10_informacao_insuficiente(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, b, nb = par
    aid = criar_atendimento(con, "C10")
    adicionar(con, aid, a, na, lista="PRESCRITA", dose=None, horarios=("08:00",))
    adicionar(con, aid, b, nb, lista="RELATADA", com_posologia=False)
    res = conciliar_atendimento(con, aid)
    dose = acha(res, "POSOLOGIA", "DOSE_NAO_INFORMADA")
    graves = [a2 for a2 in res.achados
              if a2.classificacao == "INFORMACAO_INSUFICIENTE"
              and a2.prioridade not in ("INFORMATIVO",)]
    motivos = {n.motivo for n in res.nao_avaliado}
    ok = (len(dose) == 1 and dose[0].prioridade == "INFORMATIVO"
          and not graves
          and {"DOSE_NAO_INFORMADA", "POSOLOGIA_NAO_INFORMADA"} & motivos)
    registra("10 informação insuficiente não vira alerta grave", ok,
             "%d achado(s) insuficientes, nenhum acima de informativo"
             % len([a2 for a2 in res.achados
                    if a2.classificacao == "INFORMACAO_INSUFICIENTE"]))


def caso_11_duas_fontes(con):
    par = achar_par_interacao(con, n_fontes=2)
    if not par:
        return registra("11 mesmo par afirmado por duas fontes", False,
                        "sem par com duas fontes", pulado=True)
    a, na, b, nb = par
    aid = criar_atendimento(con, "C11")
    adicionar(con, aid, a, na, horarios=("08:00",))
    adicionar(con, aid, b, nb, horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_FARMACO")
    fontes = {e.fonte for e in ach[0].evidencias} if ach else set()
    ok = len(ach) == 1 and len(fontes) == 2
    registra("11 duas fontes → um alerta, duas evidências", ok,
             "%s × %s: %d achado, %d evidências de %d fonte(s)"
             % (na, nb, len(ach), len(ach[0].evidencias) if ach else 0,
                len(fontes)))


def caso_12_item_alimento(con):
    it = achar_interacao_item(con)
    if not it:
        return registra("12 medicamento × alimento/planta", False, "sem dado",
                        pulado=True)
    sid, nome, item_id, item, tipo_item, gravidade = it
    aid = criar_atendimento(con, "C12")
    adicionar(con, aid, sid, nome, horarios=("08:00",))
    adicionar_item(con, aid, item_id, item, horario="12:00")
    res = conciliar_atendimento(con, aid)
    ach = [a for a in res.achados if a.item_b == item]
    ok = len(ach) == 1 and ach[0].subtipo == "ITEM_EM_USO"
    registra("12 medicamento × item declarado pelo paciente", ok,
             "%s × %s (%s) → %s/%s" % (nome, item, tipo_item,
                                       ach[0].tipo if ach else "-",
                                       ach[0].prioridade if ach else "-"))


def caso_12b_item_nao_declarado(con):
    it = achar_interacao_item(con)
    sid, nome, item_id, item, _t, _g = it
    aid = criar_atendimento(con, "C12B")
    adicionar(con, aid, sid, nome, horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    ach = [a for a in res.achados if a.item_b == item]
    ok = (len(ach) == 1 and ach[0].subtipo == "ORIENTACAO_PREVENTIVA"
          and ach[0].prioridade == "INFORMATIVO")
    registra("12b item não declarado vira orientação, não alerta", ok,
             "%s × %s → %s" % (nome, item, ach[0].prioridade if ach else "-"))


def caso_13_habito(con):
    hb = achar_interacao_habito(con, "ALCOOL")
    if not hb:
        return registra("13 medicamento × hábito (álcool)", False, "sem dado",
                        pulado=True)
    sid, nome, habito, gravidade = hb
    aid = criar_atendimento(con, "C13")
    adicionar(con, aid, sid, nome, horarios=("08:00",))
    adicionar_habito(con, aid, "ALCOOL", "ATUAL", frequencia="fim de semana")
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_HABITO")
    x = ach[0] if ach else None
    # Mesma situacao do caso 07: gravidade MODERADA na fonte, mas as 196
    # linhas de interacao com habito vieram de extracao por regex, entao a
    # confianca e BAIXA e a exibicao desce um degrau. A GRAVIDADE nao muda —
    # e por isso que ela e uma coluna separada da prioridade.
    ok = (x is not None and x.gravidade_fonte == gravidade
          and x.classificacao == "CONFIRMADO"
          and ((x.confianca_sistema == "BAIXA" and x.prioridade == "BAIXO")
               or (x.confianca_sistema != "BAIXA" and x.prioridade == "MODERADO")))
    registra("13 medicamento × hábito (álcool declarado)", ok,
             "%s + álcool → gravidade %s, prioridade %s (confiança %s)"
             % (nome, x.gravidade_fonte if x else "-",
                x.prioridade if x else "-", x.confianca_sistema if x else "-"))


def caso_14_cyp(con):
    par = achar_par_cyp(con, "FORTE")
    if not par:
        return registra("14 medicamento × CYP (inferência)", False, "sem par",
                        pulado=True)
    ia, na, ib, nb, sistema, papel = par
    aid = criar_atendimento(con, "C14")
    adicionar(con, aid, ia, na, horarios=("08:00",))
    adicionar(con, aid, ib, nb, horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_CYP", incluir_agrupados=True)
    principal = acha(res, "FARMACO_CYP")
    alvo = ach[0] if ach else None
    ok = (alvo is not None and alvo.natureza == "POSSIVEL"
          and alvo.confianca_sistema == "BAIXA"
          and (not principal or principal[0].prioridade == "MODERADO"))
    registra("14 medicamento × CYP: inferência, nunca documento", ok,
             "%s %s %s × %s substrato → natureza %s"
             % (na, papel.lower(), sistema, nb,
                alvo.natureza if alvo else "-"))


def caso_15_prn(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, _b, _nb = par
    aid = criar_atendimento(con, "C15")
    adicionar(con, aid, a, na, vezes=None, prn=1, continuo=0,
              condicao="se dor", horarios=())
    res = conciliar_atendimento(con, aid)
    eventos = [e for e in res.agenda.eventos if e.se_necessario]
    ok = (len(eventos) == 1
          and eventos[0].status_informacao == "SE_NECESSARIO_SEM_HORARIO_FIXO"
          and not acha(res, "CONFLITO_HORARIO"))
    registra("15 medicamento PRN não gera conflito de horário", ok,
             "%s se necessário → %d evento sem hora, 0 conflito"
             % (na, len(eventos)))


def caso_16_sem_cobertura(con):
    s = achar_substancia_sem_interacao(con)
    if not s:
        return registra("16 medicamento sem regra aplicável", False,
                        "todas as substâncias têm interação", pulado=True)
    sid, nome = s
    aid = criar_atendimento(con, "C16")
    adicionar(con, aid, sid, nome, horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    sem_cob = [n for n in res.nao_avaliado
               if n.motivo == "SUBSTANCIA_SEM_COBERTURA"
               and n.modulo == "FARMACO_FARMACO"]
    ok = len(sem_cob) == 1 and not acha(res, "FARMACO_FARMACO")
    registra("16 sem cobertura é declarado, não silenciado", ok,
             "%s → %d declaração(ões) de ausência de cobertura"
             % (nome, len(sem_cob)))


def caso_17_nao_reconhecido(con):
    aid = criar_atendimento(con, "C17")
    adicionar(con, aid, None, "remedinho da vizinha", horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    motivos = [n for n in res.nao_avaliado
               if n.motivo == "SUBSTANCIA_NAO_RECONHECIDA"]
    par = [p for p in res.pares if p.tipo_divergencia == "SEM_CORRESPONDENCIA"]
    ok = len(motivos) >= 1 and len(par) == 1
    registra("17 medicamento não reconhecido", ok,
             "%d declaração(ões) + %d par de revisão necessária"
             % (len(motivos), len(par)))


def caso_18_sem_gravidade(con):
    par = achar_par_sem_gravidade(con)
    if not par:
        return registra("18 interação sem gravidade na fonte", False,
                        "sem par", pulado=True)
    a, na, b, nb = par
    aid = criar_atendimento(con, "C18")
    adicionar(con, aid, a, na, horarios=("08:00",))
    adicionar(con, aid, b, nb, horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_FARMACO")
    declarado = [n for n in res.nao_avaliado
                 if n.motivo == "GRAVIDADE_NAO_GRADUADA_NA_FONTE"]
    ok = (len(ach) == 1 and ach[0].gravidade_fonte == "NAO_DETERMINADA"
          and ach[0].prioridade == "BAIXO"
          and ach[0].status_informacao == "NAO_DETERMINADO"
          and len(declarado) == 1)
    registra("18 gravidade ausente: nem inflada, nem escondida", ok,
             "%s × %s → %s, declarado %d vez"
             % (na, nb, ach[0].prioridade if ach else "-", len(declarado)))


# =====================================================================
# CASOS DIFICEIS — SECAO 17
# =====================================================================
def dificil_A_tres_problemas(con):
    """Um medicamento com interacao + contraindicacao + conflito de horario.
    Os tres precisam sobreviver e ser priorizados corretamente."""
    linha = con.execute(
        "SELECT s.id, s.nome_dcb FROM substancia s "
        "WHERE EXISTS (SELECT 1 FROM interacao_doenca x WHERE x.substancia_id=s.id "
        "              AND x.relacao='CONTRAINDICADO') "
        "AND EXISTS (SELECT 1 FROM interacao_substancia x "
        "            WHERE (x.substancia_a_id=s.id OR x.substancia_b_id=s.id) "
        "              AND x.gravidade='MAIOR') "
        "AND EXISTS (SELECT 1 FROM regra_administracao x WHERE x.substancia_id=s.id) "
        "ORDER BY s.n_produtos_ativos DESC LIMIT 1").fetchone()
    if not linha:
        return registra("A três problemas no mesmo medicamento", False,
                        "sem substância com os três", pulado=True)
    sid, nome = linha
    doenca = con.execute(
        "SELECT doenca_id, (SELECT nome FROM doenca WHERE id=doenca_id) "
        "FROM interacao_doenca WHERE substancia_id=? AND relacao='CONTRAINDICADO' "
        "LIMIT 1", (sid,)).fetchone()
    outro = con.execute(
        "SELECT CASE WHEN substancia_a_id=? THEN substancia_b_id ELSE substancia_a_id END, "
        "(SELECT nome_dcb FROM substancia WHERE id = CASE WHEN substancia_a_id=? "
        " THEN substancia_b_id ELSE substancia_a_id END) "
        "FROM interacao_substancia WHERE (substancia_a_id=? OR substancia_b_id=?) "
        "AND gravidade='MAIOR' LIMIT 1", (sid, sid, sid, sid)).fetchone()
    if not doenca or not outro:
        return registra("A três problemas no mesmo medicamento", False,
                        "faltou contraindicação ou par MAIOR", pulado=True)
    aid = criar_atendimento(con, "DIF-A")
    adicionar(con, aid, sid, nome, horarios=("07:05",))
    adicionar(con, aid, outro[0], outro[1], horarios=("07:05",))
    adicionar_condicao(con, aid, doenca_id=doenca[0])
    res = conciliar_atendimento(con, aid)
    tem_int = bool(acha(res, "FARMACO_FARMACO"))
    tem_ci = bool(acha(res, "FARMACO_DOENCA"))
    tem_horario = bool(acha(res, "CONFLITO_HORARIO")
                       or acha(res, "REGRA_ADMINISTRACAO"))
    ordenado = [a.prioridade for a in res.achados]
    from _prioridade import ESCALA
    bem_ordenado = ordenado == sorted(ordenado, key=ESCALA.index)
    ok = tem_int and tem_ci and tem_horario and bem_ordenado
    registra("A três problemas preservados e ordenados", ok,
             "%s: interação=%s CI=%s horário/adm=%s ordem=%s"
             % (nome, tem_int, tem_ci, tem_horario, bem_ordenado))


def dificil_B_fontes_discordantes(con):
    """ANDAIME DE TESTE. Hoje o acervo NAO tem conflito real entre fontes de
    gravidade: das duas bases de interacao, so o DDInter gradua. Para provar
    que a maquinaria funciona, o teste insere uma terceira afirmacao do mesmo
    par, de outra fonte real, com gravidade diferente — dentro da transacao
    que sera desfeita. O banco de producao nao e tocado."""
    par = achar_par_interacao(con, "MAIOR")
    a, na, b, nb = par
    fonte_outra = con.execute(
        "SELECT id, nome FROM fonte WHERE nome='Curadoria farmaceutica'"
    ).fetchone()
    con.execute(
        "INSERT INTO interacao_substancia (substancia_a_id, substancia_b_id, "
        "tipo, gravidade, origem, fonte_id, status_revisao) "
        "VALUES (?,?,'NAO_DETERMINADO','MENOR','CURADORIA',?,'APROVADO')",
        (a, b, fonte_outra[0]))
    aid = criar_atendimento(con, "DIF-B")
    adicionar(con, aid, a, na, horarios=("08:00",))
    adicionar(con, aid, b, nb, horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_FARMACO")
    x = ach[0] if ach else None
    divergentes = [e for e in x.evidencias if e.papel == "DIVERGE"] if x else []
    ok = (x is not None and x.natureza == "CONFLITANTE"
          and x.conflito_tipo == "GRAVIDADE"
          and len(divergentes) == 2
          and x.gravidade_fonte == "MAIOR"        # adota a mais grave
          and "DISCORDAM" in x.explicacao.upper())
    registra("B fontes discordam: nenhuma é escolhida em silêncio", ok,
             "natureza=%s, %d evidências divergentes, adotou %s"
             % (x.natureza if x else "-", len(divergentes),
                x.gravidade_fonte if x else "-"))


def dificil_C_extraida_nao_revisada(con):
    """Regra extraida automaticamente precisa continuar identificada."""
    ci = achar_contraindicacao(con)
    if not ci:
        return registra("C extração automática continua identificada", False,
                        "sem dado", pulado=True)
    sid, nome, did, doenca = ci
    aid = criar_atendimento(con, "DIF-C")
    adicionar(con, aid, sid, nome, horarios=("08:00",))
    adicionar_condicao(con, aid, doenca_id=did)
    res = conciliar_atendimento(con, aid)
    ach = acha(res, "FARMACO_DOENCA")
    x = ach[0] if ach else None
    ok = (x is not None
          and x.status_informacao == "EXTRAIDO_AUTOMATICAMENTE"
          and x.confianca_extracao == "EXTRAIDA_AUTOMATICAMENTE"
          and x.status_informacao != "REVISADO"
          and x.natureza != "DOCUMENTADO")
    registra("C extração automática nunca vira revisada", ok,
             "status=%s natureza=%s" % (x.status_informacao if x else "-",
                                        x.natureza if x else "-"))


def dificil_D_sem_dado(con):
    """Sem dado suficiente, o sistema nao pode gerar falso alerta."""
    aid = criar_atendimento(con, "DIF-D", rotina={})
    s = achar_substancia_sem_interacao(con)
    adicionar(con, aid, s[0], s[1], dose=None, com_posologia=True, vezes=None)
    res = conciliar_atendimento(con, aid)
    graves = [a for a in res.achados
              if a.prioridade in ("CRITICO", "ALTO", "MODERADO")]
    ok = not graves and res.nao_avaliado
    registra("D falta de dado não gera alerta grave", ok,
             "%d achado(s), 0 acima de baixo; %d declarações de não avaliado"
             % (len(res.achados), len(res.nao_avaliado)))


def dificil_E_dois_mecanismos(con):
    """O MESMO par descoberto por interacao documentada E por inferencia CYP:
    tem de virar UM alerta, com as evidencias das duas rotas preservadas."""
    linha = con.execute(
        "SELECT a.substancia_id, sa.nome_dcb, b.substancia_id, sb.nome_dcb "
        "FROM papel_farmacocinetico a "
        "JOIN papel_farmacocinetico b ON b.sistema=a.sistema AND b.papel='SUBSTRATO' "
        "JOIN substancia sa ON sa.id=a.substancia_id "
        "JOIN substancia sb ON sb.id=b.substancia_id "
        "WHERE a.papel IN ('INIBIDOR','INDUTOR') AND a.substancia_id<>b.substancia_id "
        "AND EXISTS (SELECT 1 FROM interacao_substancia i "
        "  WHERE i.substancia_a_id=MIN(a.substancia_id,b.substancia_id) "
        "    AND i.substancia_b_id=MAX(a.substancia_id,b.substancia_id)) "
        "LIMIT 1").fetchone()
    if not linha:
        return registra("E mesmo problema por dois mecanismos", False,
                        "nenhum par documentado e inferível", pulado=True)
    ia, na, ib, nb = linha
    aid = criar_atendimento(con, "DIF-E")
    adicionar(con, aid, ia, na, horarios=("08:00",))
    adicionar(con, aid, ib, nb, horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    chave = "PAR:%d-%d" % (min(ia, ib), max(ia, ib))
    principais = [a for a in res.achados if a.grupo_chave == chave]
    agrupados = [a for a in res.achados_agrupados if a.agrupado_em == chave]
    rep = principais[0] if principais else None
    metodos = {e.origem_afirmacao.split(".")[0] for e in rep.evidencias} if rep else set()
    ok = (len(principais) == 1 and len(agrupados) >= 1
          and "interacao_substancia" in metodos
          and "papel_farmacocinetico" in metodos)
    registra("E dedup sem perder evidência", ok,
             "%s × %s: 1 principal + %d agrupado(s); evidências de %s"
             % (na, nb, len(agrupados), ", ".join(sorted(metodos))))


def dificil_F_so_no_relato(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, b, nb = par
    aid = criar_atendimento(con, "DIF-F")
    adicionar(con, aid, a, na, lista="PRESCRITA", horarios=("08:00",))
    adicionar(con, aid, a, na, lista="RELATADA", horarios=("08:00",))
    adicionar(con, aid, b, nb, lista="RELATADA", horarios=("20:00",),
              origem="AUTOMEDICACAO")
    res = conciliar_atendimento(con, aid)
    so_relato = [p for p in res.divergencias
                 if p.tipo_divergencia == "SO_NO_RELATO"]
    conciliados = res.conciliados
    ok = (len(so_relato) == 1 and so_relato[0].nome_exibicao == nb
          and len(conciliados) == 1)
    registra("F item relatado ausente da prescrição", ok,
             "%d só no relato, %d conciliado" % (len(so_relato),
                                                 len(conciliados)))


def dificil_G_so_na_prescricao(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, b, nb = par
    aid = criar_atendimento(con, "DIF-G")
    adicionar(con, aid, a, na, lista="PRESCRITA", horarios=("08:00",))
    adicionar(con, aid, b, nb, lista="PRESCRITA", horarios=("20:00",))
    adicionar(con, aid, a, na, lista="RELATADA", horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    so_pres = [p for p in res.divergencias
               if p.tipo_divergencia == "SO_NA_PRESCRICAO"]
    ok = len(so_pres) == 1 and so_pres[0].nome_exibicao == nb
    registra("G item prescrito ausente do relato", ok,
             "%d só na prescrição (%s)"
             % (len(so_pres), so_pres[0].nome_exibicao if so_pres else "-"))


# =====================================================================
# CASOS COMPLEMENTARES
# =====================================================================
def caso_19_polimedicado(con):
    """Varios problemas no mesmo paciente, com prescricao e relato."""
    par = achar_par_interacao(con, "MAIOR")
    ci = achar_contraindicacao(con)
    hb = achar_interacao_habito(con, "ALCOOL")
    a, na, b, nb = par
    aid = criar_atendimento(con, "C19")
    adicionar(con, aid, a, na, lista="PRESCRITA", dose=10.0, unidade="mg",
              horarios=("08:00",))
    adicionar(con, aid, a, na, lista="RELATADA", dose=20.0, unidade="mg",
              horarios=("08:00",))
    adicionar(con, aid, b, nb, lista="RELATADA", horarios=("20:00",))
    if ci:
        adicionar(con, aid, ci[0], ci[1], lista="RELATADA", horarios=("12:00",))
        adicionar_condicao(con, aid, doenca_id=ci[2])
    if hb:
        adicionar(con, aid, hb[0], hb[1], lista="RELATADA", horarios=("22:00",))
        adicionar_habito(con, aid, "ALCOOL", "ATUAL")
    adicionar_alergia(con, aid, livre="dipirona, acho")
    res = conciliar_atendimento(con, aid)
    tipos = {a2.tipo for a2 in res.achados}
    ok = (len(tipos) >= 4 and res.resumo["divergencias"] >= 1
          and res.resumo["achados"] == len(res.achados)
          and res.resumo["requer_revisao_profissional"])
    registra("19 paciente polimedicado: vários módulos juntos", ok,
             "%d achados de %d módulos; %d divergências"
             % (res.resumo["achados"], len(tipos), res.resumo["divergencias"]))


def caso_20_controle_negativo(con):
    """Controle negativo: paciente com um unico medicamento sem cobertura,
    sem condicao, sem alergia e sem habito. Nao pode haver alerta clinico."""
    s = achar_substancia_sem_interacao(con)
    aid = criar_atendimento(con, "C20")
    adicionar(con, aid, s[0], s[1], horarios=("08:00",))
    for h in ("TABAGISMO", "ALCOOL", "CAFEINA"):
        adicionar_habito(con, aid, h, "NUNCA")
    res = conciliar_atendimento(con, aid)
    clinicos = [a for a in res.achados
                if a.prioridade in ("CRITICO", "ALTO", "MODERADO")]
    ok = not clinicos
    registra("20 controle negativo: zero alerta clínico", ok,
             "%d achados no total, %d clínicos" % (len(res.achados),
                                                   len(clinicos)))


def caso_21_persistencia(con):
    """O resultado precisa caber no esquema — todos os CHECK inclusive."""
    par = achar_par_interacao(con, "MAIOR")
    ci = achar_contraindicacao(con)
    a, na, b, nb = par
    aid = criar_atendimento(con, "C21")
    adicionar(con, aid, a, na, lista="PRESCRITA", dose=10.0, unidade="mg",
              horarios=("08:00",))
    adicionar(con, aid, a, na, lista="RELATADA", dose=20.0, unidade="mg",
              horarios=("08:00",))
    adicionar(con, aid, b, nb, lista="RELATADA", horarios=("20:00",))
    if ci:
        adicionar(con, aid, ci[0], ci[1], lista="RELATADA", horarios=("12:00",))
        adicionar_condicao(con, aid, doenca_id=ci[2])
    res = conciliar_atendimento(con, aid, persistir=True)
    n_ach = con.execute("SELECT COUNT(*) FROM achado WHERE conciliacao_id=?",
                        (res.conciliacao_id,)).fetchone()[0]
    n_ev = con.execute(
        "SELECT COUNT(*) FROM achado_evidencia e JOIN achado a ON a.id=e.achado_id "
        "WHERE a.conciliacao_id=?", (res.conciliacao_id,)).fetchone()[0]
    n_view = con.execute("SELECT COUNT(*) FROM vw_achado_clinico "
                         "WHERE conciliacao_id=?", (res.conciliacao_id,)).fetchone()[0]
    n_par = con.execute("SELECT COUNT(*) FROM conciliacao_par WHERE conciliacao_id=?",
                        (res.conciliacao_id,)).fetchone()[0]
    resumo = con.execute("SELECT n_achados, n_divergencias FROM conciliacao "
                         "WHERE id=?", (res.conciliacao_id,)).fetchone()
    ok = (res.conciliacao_id and n_ach == len(res.achados) + len(res.achados_agrupados)
          and n_ev >= n_ach and n_view == len(res.achados)
          and n_par == len(res.pares) and resumo[0] == len(res.achados)
          and resumo[1] == len(res.divergencias))
    registra("21 persistência cabe no esquema", ok,
             "%d achados (%d na view), %d evidências, %d pares"
             % (n_ach, n_view, n_ev, n_par))


def caso_22_explicacao(con):
    """Todo achado precisa saber dizer POR QUE apareceu."""
    par = achar_par_interacao(con, "MAIOR")
    a, na, b, nb = par
    aid = criar_atendimento(con, "C22")
    adicionar(con, aid, a, na, horarios=("08:00",))
    adicionar(con, aid, b, nb, horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    faltando = [a2.titulo for a2 in res.achados
                if not a2.explicacao or not a2.justificativa_prioridade
                or not a2.metodo_deteccao or not a2.origem_afirmacao]
    cadeia = res.achados[0].por_que_apareceu() if res.achados else ""
    ok = (not faltando and "Detecção:" in cadeia and "Prioridade" in cadeia)
    registra("22 todo achado explica por que apareceu", ok,
             "%d achado(s), %d sem cadeia completa"
             % (len(res.achados), len(faltando)))


def caso_23_sem_prescricao(con):
    """Balcao comum: nao ha prescricao. Nao pode virar N divergencias."""
    par = achar_par_interacao(con, "MAIOR")
    a, na, b, nb = par
    aid = criar_atendimento(con, "C23")
    adicionar(con, aid, a, na, lista="RELATADA", horarios=("08:00",))
    adicionar(con, aid, b, nb, lista="RELATADA", horarios=("20:00",))
    res = conciliar_atendimento(con, aid)
    declarado = [n for n in res.nao_avaliado
                 if n.motivo == "SEM_CORRESPONDENCIA_ENTRE_LISTAS"]
    ok = not res.divergencias and len(declarado) == 1
    registra("23 sem prescrição não inventa divergência", ok,
             "%d divergências, %d declaração de ausência de lista"
             % (len(res.divergencias), len(declarado)))


def caso_24_conciliado_nao_e_duplicidade(con):
    """O mesmo farmaco na prescricao E no relato e um ACERTO da conciliacao,
    nunca uma duplicidade."""
    par = achar_par_interacao(con, "MAIOR")
    a, na, _b, _nb = par
    aid = criar_atendimento(con, "C24")
    adicionar(con, aid, a, na, lista="PRESCRITA", dose=10.0, unidade="mg",
              horarios=("08:00",))
    adicionar(con, aid, a, na, lista="RELATADA", dose=10.0, unidade="mg",
              horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    dup = acha(res, "DUPLICIDADE")
    ok = not dup and len(res.conciliados) == 1
    registra("24 item conciliado não vira duplicidade", ok,
             "%d duplicidade(s), %d conciliado(s)" % (len(dup),
                                                      len(res.conciliados)))


def caso_25_descontinuado(con):
    par = achar_par_interacao(con, "MAIOR")
    a, na, _b, _nb = par
    aid = criar_atendimento(con, "C25")
    adicionar(con, aid, a, na, lista="PRESCRITA", horarios=("08:00",))
    adicionar(con, aid, a, na, lista="RELATADA", horarios=("08:00",))
    adicionar(con, aid, a, na, lista="ANTERIOR", horarios=("08:00",))
    res = conciliar_atendimento(con, aid)
    d = [p for p in res.divergencias
         if p.tipo_divergencia == "DESCONTINUADO_EM_USO"]
    ach = acha(res, "DIVERGENCIA_CONCILIACAO", "DESCONTINUADO_EM_USO")
    ok = len(d) == 1 and len(ach) == 1 and ach[0].prioridade == "ALTO"
    registra("25 suspenso que continua em uso", ok,
             "%d divergência → %s" % (len(d), ach[0].prioridade if ach else "-"))


CASOS = [
    caso_01_interacao, caso_02_alergia, caso_02b_alergia_cruzada,
    caso_03_contraindicacao, caso_04_duplicidade,
    caso_04b_duplicidade_terapeutica, caso_05_dose_diferente,
    caso_06_frequencia_diferente, caso_07_conflito_horario,
    caso_08_conflito_refeicao, caso_09_separacao_classe_atc,
    caso_10_informacao_insuficiente, caso_11_duas_fontes, caso_12_item_alimento,
    caso_12b_item_nao_declarado, caso_13_habito, caso_14_cyp, caso_15_prn,
    caso_16_sem_cobertura, caso_17_nao_reconhecido, caso_18_sem_gravidade,
    caso_19_polimedicado, caso_20_controle_negativo, caso_21_persistencia,
    caso_22_explicacao, caso_23_sem_prescricao,
    caso_24_conciliado_nao_e_duplicidade, caso_25_descontinuado,
]
DIFICEIS = [dificil_A_tres_problemas, dificil_B_fontes_discordantes,
            dificil_C_extraida_nao_revisada, dificil_D_sem_dado,
            dificil_E_dois_mecanismos, dificil_F_so_no_relato,
            dificil_G_so_na_prescricao]


def main() -> int:
    print("=" * 78)
    print("VERIFICACAO 1 — FUNCIONAL — MOTOR DE CONCILIACAO")
    print("=" * 78)
    print("\nBATERIA DE CASOS CLINICOS (especificacao, secao 16)\n")
    for fn in CASOS:
        with banco_temporario() as con:
            try:
                fn(con)
            except Exception as exc:      # noqa: BLE001
                registra(fn.__name__, False, "EXCEÇÃO: %r" % exc)
    print("\nCASOS DIFICEIS (especificacao, secao 17)\n")
    for fn in DIFICEIS:
        with banco_temporario() as con:
            try:
                fn(con)
            except Exception as exc:      # noqa: BLE001
                registra(fn.__name__, False, "EXCEÇÃO: %r" % exc)

    falhas = [r for r in RESULTADOS if not r[1] and not r[3]]
    pulados = [r for r in RESULTADOS if r[3]]
    print("\n" + "=" * 78)
    print("%d caso(s) · %d ok · %d falha(s) · %d pulado(s) por ausência de dado"
          % (len(RESULTADOS), len(RESULTADOS) - len(falhas) - len(pulados),
             len(falhas), len(pulados)))
    for nome, _ok, det, _p in falhas:
        print("  FALHA: %s — %s" % (nome, det))
    for nome, _ok, det, _p in pulados:
        print("  PULADO: %s — %s" % (nome, det))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
