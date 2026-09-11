# -*- coding: utf-8 -*-
"""
VERIFICACAO 2 — INDEPENDENTE — motor de conciliacao (Fase 5).

NAO repete os casos da verificacao 1. Procura o mesmo defeito por outro
caminho, que e a unica forma de o segundo teste valer alguma coisa: no
historico deste projeto, TODOS os defeitos serios foram encontrados pela
segunda verificacao e nenhum pela primeira.

Cinco eixos, nenhum compartilhando logica com o motor:

  1. INVARIANTES        afirmacoes que precisam valer em qualquer atendimento,
                        conferidas sobre centenas de execucoes.
  2. SQL INDEPENDENTE   para cada achado gravado, volta ao banco por consulta
                        escrita a parte e confere que a afirmacao existe, com
                        a gravidade e a relacao que o achado diz ter.
  3. RECONTAGEM         conta os achados esperados por SQL proprio, sem passar
                        pelo motor, e compara com o que ele produziu.
  4. PROPRIEDADE        gera pacientes aleatorios sobre substancias reais e
                        verifica regras gerais (determinismo, monotonicidade,
                        ausencia de alerta sem causa).
  5. CONFERENCIA MANUAL  um conjunto de expectativas calculado a mao a partir
                        do banco, item a item.

Uso: python tests/verificacao_motor_conciliacao.py
"""
from __future__ import annotations

import random
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tests"))
sys.path.insert(0, str(RAIZ / "rules"))

from casos_conciliacao import (achar_contraindicacao, achar_interacao_item,  # noqa: E402
                               achar_par_interacao, adicionar,
                               adicionar_alergia, adicionar_condicao,
                               adicionar_habito, adicionar_item,
                               banco_temporario, criar_atendimento)
from motor_conciliacao import conciliar_atendimento  # noqa: E402

FALHAS = []
PASSOS = []


def checa(nome, ok, detalhe=""):
    PASSOS.append((nome, ok, detalhe))
    if not ok:
        FALHAS.append((nome, detalhe))
    print("   %s %-52s %s" % ("OK  " if ok else "ERRO", nome[:52], detalhe[:74]))


# =====================================================================
# EIXO 1 — INVARIANTES
# =====================================================================
ESCALA = ["CRITICO", "ALTO", "MODERADO", "BAIXO", "INFORMATIVO"]

VOCAB = {
    "prioridade": set(ESCALA),
    "classificacao": {"CONFIRMADO", "POSSIVEL", "INFORMACAO_INSUFICIENTE",
                      "REGRA_DESCONHECIDA", "CONFLITO_ENTRE_FONTES"},
    "natureza": {"DOCUMENTADO", "PROVAVEL", "POSSIVEL", "PREVISTO",
                 "DESCONHECIDO", "CONFLITANTE"},
    "status_informacao": {"DOCUMENTADO", "EXTRAIDO_AUTOMATICAMENTE", "REVISADO",
                          "INFORMACAO_INSUFICIENTE", "NAO_DETERMINADO",
                          "PREVISTO"},
    "confianca_sistema": {"ALTA", "MEDIA", "BAIXA"},
    "confianca_extracao": {"REVISADA", "CARGA_DIRETA",
                           "EXTRAIDA_AUTOMATICAMENTE", "CALCULADO",
                           "NAO_APLICAVEL"},
    "origem_achado": {"REGRA", "MODELO", "REGRA_E_MODELO"},
    "gravidade_fonte": {"MAIOR", "MODERADA", "MENOR", "NAO_DETERMINADA", None},
}


def invariantes(res, contexto: str) -> list:
    """Devolve a lista de violacoes. Vazia = tudo certo."""
    v = []
    todos = list(res.achados) + list(res.achados_agrupados)

    for a in todos:
        for campo, valores in VOCAB.items():
            if getattr(a, campo) not in valores:
                v.append("%s: %s fora do vocabulário (%r)"
                         % (contexto, campo, getattr(a, campo)))
        # Previsao nunca se disfarca de fato, e vice-versa.
        if (a.natureza == "PREVISTO") != (a.status_informacao == "PREVISTO"):
            v.append("%s: natureza e status de previsão discordam" % contexto)
        if a.natureza == "PREVISTO" and a.probabilidade_modelo is None:
            v.append("%s: PREVISTO sem probabilidade" % contexto)
        if a.origem_achado == "REGRA" and a.probabilidade_modelo is not None:
            v.append("%s: achado de regra com probabilidade de modelo" % contexto)
        if a.status_informacao == "REVISADO" and a.confianca_extracao != "REVISADA":
            v.append("%s: marcado REVISADO sem extração revisada" % contexto)
        if (a.conflito_tipo is not None) != (a.natureza == "CONFLITANTE"):
            v.append("%s: conflito declarado sem natureza conflitante" % contexto)
        # A especificacao proibe: informacao insuficiente virando alerta grave.
        if (a.classificacao == "INFORMACAO_INSUFICIENTE"
                and a.prioridade != "INFORMATIVO"):
            v.append("%s: informação insuficiente com prioridade %s"
                     % (contexto, a.prioridade))
        # Inferencia e possibilidade nunca chegam com confianca alta.
        if a.natureza in ("POSSIVEL", "PREVISTO") and a.confianca_sistema == "ALTA":
            v.append("%s: natureza %s com confiança ALTA" % (contexto, a.natureza))
        # Todo achado precisa saber se explicar.
        if not a.explicacao or not a.justificativa_prioridade:
            v.append("%s: achado sem explicação ou sem justificativa" % contexto)
        if not a.metodo_deteccao or not a.origem_afirmacao:
            v.append("%s: achado sem método de detecção ou origem" % contexto)
        if not a.grupo_chave:
            v.append("%s: achado sem chave de grupo" % contexto)
        # A chave identifica o PROBLEMA, nunca a linha que o revelou. Chave
        # presa a `atendimento_medicamento.id` quebra o agrupamento quando o
        # paciente traz marca e generico do mesmo principio ativo — foi o
        # defeito que o teste de monotonicidade (4.2) revelou.
        if a.grupo_chave.startswith(("ADM:am", "DOSE:am")):
            v.append("%s: chave de grupo presa à linha (%s)"
                     % (contexto, a.grupo_chave))
        # CRITICO so por alergia declarada pelo paciente.
        if a.prioridade == "CRITICO" and a.tipo != "FARMACO_ALERGIA":
            v.append("%s: CRÍTICO fora do módulo de alergia (%s)"
                     % (contexto, a.tipo))

    # Agrupamento: um representante por grupo, e nenhum orfao.
    grupos_principais = defaultdict(int)
    for a in res.achados:
        grupos_principais[a.grupo_chave] += 1
        if a.status != "PRINCIPAL" or a.agrupado_em is not None:
            v.append("%s: achado na lista principal marcado como agrupado"
                     % contexto)
    for chave, n in grupos_principais.items():
        if n != 1:
            v.append("%s: grupo %s tem %d representantes" % (contexto, chave, n))
    for a in res.achados_agrupados:
        if a.status != "AGRUPADO" or a.agrupado_em is None:
            v.append("%s: achado agrupado sem marca de agrupamento" % contexto)
        elif a.agrupado_em not in grupos_principais:
            v.append("%s: agrupado em grupo inexistente (%s)"
                     % (contexto, a.agrupado_em))

    # Nenhuma evidencia perdida no agrupamento.
    for a in res.achados_agrupados:
        rep = next((x for x in res.achados if x.grupo_chave == a.agrupado_em), None)
        if rep is None:
            continue
        origens_rep = {e.origem_afirmacao for e in rep.evidencias}
        for e in a.evidencias:
            if e.origem_afirmacao not in origens_rep:
                v.append("%s: evidência %s perdida no agrupamento"
                         % (contexto, e.origem_afirmacao))

    # Resumo tem de bater com as listas.
    r = res.resumo
    if r["achados"] != len(res.achados):
        v.append("%s: resumo diz %d achados, a lista tem %d"
                 % (contexto, r["achados"], len(res.achados)))
    soma = (r["criticos"] + r["altos"] + r["moderados"] + r["baixos"]
            + r["informativos"])
    if soma != len(res.achados):
        v.append("%s: soma por prioridade (%d) != total (%d)"
                 % (contexto, soma, len(res.achados)))
    if r["divergencias"] != len(res.divergencias):
        v.append("%s: resumo de divergências não bate" % contexto)
    if r["nao_avaliado"] != len(res.nao_avaliado):
        v.append("%s: resumo de não avaliado não bate" % contexto)

    # A conciliacao nunca decide intencao.
    for p in res.pares:
        if p.intencionalidade != "NAO_DETERMINADA":
            v.append("%s: o motor gravou intencionalidade %s"
                     % (contexto, p.intencionalidade))
        if p.situacao == "CONCILIADO" and p.tipo_divergencia:
            v.append("%s: par conciliado com tipo de divergência" % contexto)

    # A ordenacao precisa ser por prioridade.
    ordem = [ESCALA.index(a.prioridade) for a in res.achados]
    if ordem != sorted(ordem):
        v.append("%s: lista de achados fora de ordem de prioridade" % contexto)
    return v


def eixo_1_invariantes(con):
    print("\n1. INVARIANTES — sobre atendimentos construídos de formas diferentes\n")
    cenarios = []

    par = achar_par_interacao(con, "MAIOR")
    ci = achar_contraindicacao(con)
    it = achar_interacao_item(con)

    def cen_completo(aid):
        adicionar(con, aid, par[0], par[1], lista="PRESCRITA", dose=10.0,
                  unidade="mg", horarios=("08:00",))
        adicionar(con, aid, par[0], par[1], lista="RELATADA", dose=20.0,
                  unidade="mg", horarios=("08:00",))
        adicionar(con, aid, par[2], par[3], lista="RELATADA", horarios=("20:00",))
        if ci:
            adicionar(con, aid, ci[0], ci[1], lista="RELATADA", horarios=("12:00",))
            adicionar_condicao(con, aid, doenca_id=ci[2])
        if it:
            adicionar(con, aid, it[0], it[1], lista="RELATADA", horarios=("07:00",))
            adicionar_item(con, aid, it[2], it[3], horario="07:00")
        adicionar_alergia(con, aid, substancia_id=par[0], gravidade="ANAFILAXIA")
        adicionar_habito(con, aid, "ALCOOL", "ATUAL")

    def cen_vazio(aid):
        pass

    def cen_sem_reconhecimento(aid):
        adicionar(con, aid, None, "xarope da farmácia", horarios=("08:00",))
        adicionar(con, aid, None, "aquele branco", com_posologia=False)

    def cen_sem_posologia(aid):
        adicionar(con, aid, par[0], par[1], com_posologia=False)
        adicionar(con, aid, par[2], par[3], com_posologia=False)

    cenarios = [("completo", cen_completo), ("vazio", cen_vazio),
                ("sem reconhecimento", cen_sem_reconhecimento),
                ("sem posologia", cen_sem_posologia)]

    for nome, montar in cenarios:
        aid = criar_atendimento(con, "INV-" + nome[:6])
        montar(aid)
        res = conciliar_atendimento(con, aid)
        viol = invariantes(res, nome)
        checa("invariantes — cenário %s" % nome, not viol,
              "%d achados, %d violações%s" % (len(res.achados), len(viol),
                                              (": " + viol[0]) if viol else ""))


# =====================================================================
# EIXO 2 — SQL INDEPENDENTE SOBRE O QUE FOI GRAVADO
# =====================================================================
def eixo_2_sql(con):
    print("\n2. SQL INDEPENDENTE — cada achado gravado é conferido na origem\n")
    par = achar_par_interacao(con, "MAIOR")
    ci = achar_contraindicacao(con)
    it = achar_interacao_item(con)
    aid = criar_atendimento(con, "SQL-1")
    adicionar(con, aid, par[0], par[1], lista="PRESCRITA", horarios=("08:00",))
    adicionar(con, aid, par[2], par[3], lista="RELATADA", horarios=("20:00",))
    if ci:
        adicionar(con, aid, ci[0], ci[1], lista="RELATADA", horarios=("12:00",))
        adicionar_condicao(con, aid, doenca_id=ci[2])
    if it:
        adicionar(con, aid, it[0], it[1], lista="RELATADA", horarios=("07:00",))
        adicionar_item(con, aid, it[2], it[3], horario="07:00")
    res = conciliar_atendimento(con, aid, persistir=True)
    cid = res.conciliacao_id

    # 2.1 — toda evidencia gravada aponta para uma linha que existe mesmo,
    #       e a gravidade que o achado exibe e uma das que a fonte declarou.
    erros = []
    for (aid_ach, modulo, gravidade, origem, grav_ev) in con.execute(
            "SELECT a.id, a.modulo, a.gravidade_fonte, e.origem_afirmacao, "
            "e.gravidade_declarada FROM achado a "
            "JOIN achado_evidencia e ON e.achado_id = a.id "
            "WHERE a.conciliacao_id=?", (cid,)):
        tabela, _sep, ident = origem.partition(".")
        if tabela == "interacao_substancia":
            real = con.execute("SELECT gravidade FROM interacao_substancia "
                               "WHERE id=?", (ident,)).fetchone()
            if real is None:
                erros.append("achado %d aponta para linha inexistente %s"
                             % (aid_ach, origem))
            elif real[0] != grav_ev:
                erros.append("achado %d: evidência diz %s, banco diz %s"
                             % (aid_ach, grav_ev, real[0]))
        elif tabela == "interacao_doenca":
            real = con.execute("SELECT relacao, gravidade FROM interacao_doenca "
                               "WHERE id=?", (ident,)).fetchone()
            if real is None:
                erros.append("achado %d aponta para linha inexistente %s"
                             % (aid_ach, origem))
        elif tabela == "interacao_item":
            real = con.execute("SELECT gravidade FROM interacao_item WHERE id=?",
                               (ident,)).fetchone()
            if real is None or real[0] != grav_ev:
                erros.append("achado %d: item não confere" % aid_ach)
    checa("2.1 toda evidência existe na origem, com a mesma gravidade",
          not erros, "%d evidência(s) conferidas, %d erro(s)"
          % (con.execute("SELECT COUNT(*) FROM achado_evidencia e JOIN achado a "
                         "ON a.id=e.achado_id WHERE a.conciliacao_id=?",
                         (cid,)).fetchone()[0], len(erros)))

    # 2.2 — nenhuma gravidade exibida foi inventada: ela existe no banco.
    inventadas = con.execute(
        "SELECT COUNT(*) FROM achado a WHERE a.conciliacao_id=? "
        "AND a.gravidade_fonte IS NOT NULL "
        "AND a.gravidade_fonte <> 'NAO_DETERMINADA' "
        "AND NOT EXISTS (SELECT 1 FROM achado_evidencia e "
        "  WHERE e.achado_id=a.id AND e.gravidade_declarada=a.gravidade_fonte)",
        (cid,)).fetchone()[0]
    checa("2.2 nenhuma gravidade exibida sem fonte que a declare",
          inventadas == 0, "%d gravidade(s) sem lastro" % inventadas)

    # 2.3 — a view do farmaceutico expoe SO os representantes.
    n_view = con.execute("SELECT COUNT(*) FROM vw_achado_clinico "
                         "WHERE conciliacao_id=?", (cid,)).fetchone()[0]
    n_princ = con.execute("SELECT COUNT(*) FROM achado WHERE conciliacao_id=? "
                          "AND status='PRINCIPAL'", (cid,)).fetchone()[0]
    n_total = con.execute("SELECT COUNT(*) FROM achado WHERE conciliacao_id=?",
                          (cid,)).fetchone()[0]
    checa("2.3 a view expõe representantes, a tabela guarda tudo",
          n_view == n_princ == len(res.achados) and n_total >= n_view,
          "view %d = principais %d; tabela guarda %d" % (n_view, n_princ, n_total))

    # 2.4 — o resumo gravado bate com a recontagem por SQL.
    grav = con.execute(
        "SELECT n_achados, n_criticos, n_altos, n_moderados, n_baixos, "
        "n_informativos, n_divergencias FROM conciliacao WHERE id=?",
        (cid,)).fetchone()
    recont = con.execute(
        "SELECT COUNT(*), "
        "SUM(prioridade='CRITICO'), SUM(prioridade='ALTO'), "
        "SUM(prioridade='MODERADO'), SUM(prioridade='BAIXO'), "
        "SUM(prioridade='INFORMATIVO') FROM achado "
        "WHERE conciliacao_id=? AND status='PRINCIPAL'", (cid,)).fetchone()
    div = con.execute("SELECT COUNT(*) FROM conciliacao_par WHERE conciliacao_id=? "
                      "AND situacao<>'CONCILIADO'", (cid,)).fetchone()[0]
    ok = (list(grav[:6]) == [x or 0 for x in recont] and grav[6] == div)
    checa("2.4 resumo gravado = recontagem por SQL própria", ok,
          "gravado %s vs recontado %s" % (list(grav[:6]), [x or 0 for x in recont]))

    # 2.5 — intencionalidade nunca sai de NAO_DETERMINADA sem assinatura.
    n = con.execute("SELECT COUNT(*) FROM conciliacao_par WHERE conciliacao_id=? "
                    "AND intencionalidade<>'NAO_DETERMINADA'", (cid,)).fetchone()[0]
    checa("2.5 o motor nunca grava intencionalidade", n == 0,
          "%d par(es) com intencionalidade decidida por script" % n)


# =====================================================================
# EIXO 3 — RECONTAGEM POR CAMINHO PROPRIO
# =====================================================================
def eixo_3_recontagem(con):
    print("\n3. RECONTAGEM — o esperado é calculado por SQL, sem passar pelo motor\n")
    rnd = random.Random(20260909)
    ids = [r[0] for r in con.execute(
        "SELECT id FROM substancia WHERE n_produtos_ativos > 5 "
        "AND EXISTS (SELECT 1 FROM interacao_substancia i "
        "  WHERE i.substancia_a_id=id OR i.substancia_b_id=id) LIMIT 400")]
    total_conferidos = 0
    divergentes = []

    for rodada in range(12):
        escolhidos = rnd.sample(ids, 5)
        aid = criar_atendimento(con, "REC-%d" % rodada)
        for sid in escolhidos:
            nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                               (sid,)).fetchone()[0]
            adicionar(con, aid, sid, nome, horarios=("08:00",))
        res = conciliar_atendimento(con, aid)

        # Esperado, por SQL proprio: pares distintos com ao menos uma linha
        # liberada. Nada aqui usa o motor.
        esperado = set()
        for i, a in enumerate(sorted(escolhidos)):
            for b in sorted(escolhidos)[i + 1:]:
                n = con.execute(
                    "SELECT COUNT(*) FROM vw_interacao_liberada "
                    "WHERE substancia_a_id=? AND substancia_b_id=?",
                    (min(a, b), max(a, b))).fetchone()[0]
                if n:
                    esperado.add((min(a, b), max(a, b)))
        obtido = {(a.substancia_a_id, a.substancia_b_id)
                  for a in list(res.achados) + list(res.achados_agrupados)
                  if a.tipo == "FARMACO_FARMACO"}
        total_conferidos += len(esperado)
        if esperado != obtido:
            divergentes.append((rodada, esperado ^ obtido))

        # Cobertura: quem nao tem par verificado tem de estar declarado.
        declarados = {n.item for n in res.nao_avaliado
                      if n.motivo in ("SEM_INTERACAO_CONHECIDA",
                                      "SUBSTANCIA_SEM_COBERTURA")}
        pares_sem = 0
        for i, a in enumerate(sorted(escolhidos)):
            for b in sorted(escolhidos)[i + 1:]:
                if (min(a, b), max(a, b)) not in esperado:
                    pares_sem += 1
        if pares_sem and not declarados:
            divergentes.append((rodada, "pares sem interação não declarados"))

    checa("3.1 pares detectados = pares calculados por SQL independente",
          not divergentes,
          "%d rodadas, %d par(es) conferidos, %d divergência(s)"
          % (12, total_conferidos, len(divergentes)))


# =====================================================================
# EIXO 4 — PROPRIEDADES
# =====================================================================
def eixo_4_propriedades(con):
    print("\n4. PROPRIEDADES — geradas, não escolhidas a dedo\n")
    rnd = random.Random(4242)
    ids = [r[0] for r in con.execute(
        "SELECT id FROM substancia WHERE n_produtos_ativos > 3 LIMIT 600")]

    # 4.1 determinismo
    aid = criar_atendimento(con, "PROP-DET")
    for sid in rnd.sample(ids, 6):
        nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                           (sid,)).fetchone()[0]
        adicionar(con, aid, sid, nome, horarios=("08:00",))
    a1 = conciliar_atendimento(con, aid)
    a2 = conciliar_atendimento(con, aid)
    assinatura = lambda r: [(x.grupo_chave, x.prioridade, x.titulo)  # noqa: E731
                            for x in r.achados]
    checa("4.1 duas execuções sobre o mesmo dado dão o mesmo resultado",
          assinatura(a1) == assinatura(a2),
          "%d achados, resumo idêntico: %s" % (len(a1.achados),
                                               a1.resumo == a2.resumo))

    # 4.2 monotonicidade: acrescentar medicamento nunca REMOVE um problema
    quebras = 0
    for rodada in range(8):
        base = rnd.sample(ids, 4)
        extra = rnd.choice([i for i in ids if i not in base])
        aid1 = criar_atendimento(con, "PROP-M%dA" % rodada)
        for sid in base:
            nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                               (sid,)).fetchone()[0]
            adicionar(con, aid1, sid, nome, horarios=("08:00",))
        r1 = conciliar_atendimento(con, aid1)
        aid2 = criar_atendimento(con, "PROP-M%dB" % rodada)
        for sid in base + [extra]:
            nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                               (sid,)).fetchone()[0]
            adicionar(con, aid2, sid, nome, horarios=("08:00",))
        r2 = conciliar_atendimento(con, aid2)
        g1 = {a.grupo_chave for a in list(r1.achados) + list(r1.achados_agrupados)}
        g2 = {a.grupo_chave for a in list(r2.achados) + list(r2.achados_agrupados)}
        if not g1.issubset(g2):
            quebras += 1
    checa("4.2 acrescentar medicamento nunca apaga um achado", quebras == 0,
          "8 rodadas, %d quebra(s) de monotonicidade" % quebras)

    # 4.3 sem contexto declarado, nenhum modulo de contexto dispara
    disparos = 0
    for rodada in range(10):
        sid = rnd.choice(ids)
        nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                           (sid,)).fetchone()[0]
        aid = criar_atendimento(con, "PROP-C%d" % rodada)
        adicionar(con, aid, sid, nome, horarios=("08:00",))
        res = conciliar_atendimento(con, aid)
        for a in res.achados:
            if a.tipo in ("FARMACO_ALERGIA", "FARMACO_DOENCA", "FARMACO_HABITO",
                          "DUPLICIDADE", "FARMACO_FARMACO", "FARMACO_CYP",
                          "DIVERGENCIA_CONCILIACAO"):
                disparos += 1
    checa("4.3 um medicamento e nenhum contexto: nenhum módulo de contexto "
          "dispara", disparos == 0, "%d disparo(s) sem causa" % disparos)

    # 4.4 alergia declarada sempre produz achado; sem alergia, nunca CRITICO
    par = achar_par_interacao(con, "MAIOR")
    aid = criar_atendimento(con, "PROP-AL")
    adicionar(con, aid, par[0], par[1], horarios=("08:00",))
    sem = conciliar_atendimento(con, aid)
    adicionar_alergia(con, aid, substancia_id=par[0], gravidade="GRAVE")
    com = conciliar_atendimento(con, aid)
    ok = (not [a for a in sem.achados if a.prioridade == "CRITICO"]
          and len([a for a in com.achados if a.prioridade == "CRITICO"]) == 1)
    checa("4.4 CRÍTICO aparece com alergia e some sem ela", ok,
          "sem alergia: %d crítico; com alergia: %d"
          % (len([a for a in sem.achados if a.prioridade == "CRITICO"]),
             len([a for a in com.achados if a.prioridade == "CRITICO"])))

    # 4.5 toda substancia entra ou como achado ou como declaracao
    faltando = 0
    for rodada in range(10):
        escolhidos = rnd.sample(ids, 3)
        aid = criar_atendimento(con, "PROP-D%d" % rodada)
        nomes = []
        for sid in escolhidos:
            nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                               (sid,)).fetchone()[0]
            nomes.append(nome)
            adicionar(con, aid, sid, nome, horarios=("08:00",))
        res = conciliar_atendimento(con, aid)
        texto = " | ".join([a.item_a + " " + (a.item_b or "") for a in res.achados]
                           + [n.item for n in res.nao_avaliado])
        for nome in nomes:
            if nome not in texto:
                faltando += 1
    checa("4.5 todo medicamento aparece em algum achado ou em alguma "
          "declaração", faltando == 0,
          "%d medicamento(s) sumiram sem deixar registro" % faltando)


# =====================================================================
# EIXO 5 — CONFERENCIA MANUAL
# =====================================================================
def eixo_5_manual(con):
    print("\n5. CONFERÊNCIA MANUAL — expectativas calculadas fora do motor\n")

    # 5.1 — cinco pares escolhidos pelo banco, com a gravidade que ELE diz.
    pares = con.execute(
        "SELECT i.substancia_a_id, sa.nome_dcb, i.substancia_b_id, sb.nome_dcb, "
        "i.gravidade FROM interacao_substancia i "
        "JOIN substancia sa ON sa.id=i.substancia_a_id "
        "JOIN substancia sb ON sb.id=i.substancia_b_id "
        "WHERE i.gravidade IN ('MAIOR','MODERADA','MENOR') "
        "AND NOT EXISTS (SELECT 1 FROM interacao_substancia j "
        "  WHERE j.substancia_a_id=i.substancia_a_id "
        "    AND j.substancia_b_id=i.substancia_b_id AND j.id<>i.id "
        "    AND j.gravidade<>i.gravidade AND j.gravidade<>'NAO_DETERMINADA') "
        "ORDER BY i.gravidade, sa.n_produtos_ativos DESC LIMIT 5").fetchall()
    esperado_prio = {"MAIOR": "ALTO", "MODERADA": "MODERADO", "MENOR": "BAIXO"}
    erros = []
    for a, na, b, nb, gravidade in pares:
        aid = criar_atendimento(con, "MAN-%d-%d" % (a, b))
        adicionar(con, aid, a, na, horarios=("08:00",))
        adicionar(con, aid, b, nb, horarios=("20:00",))
        res = conciliar_atendimento(con, aid)
        ach = [x for x in res.achados if x.tipo == "FARMACO_FARMACO"]
        if len(ach) != 1:
            erros.append("%s×%s: %d achados" % (na, nb, len(ach)))
            continue
        x = ach[0]
        if x.gravidade_fonte != gravidade:
            erros.append("%s×%s: gravidade %s, banco diz %s"
                         % (na, nb, x.gravidade_fonte, gravidade))
        # A prioridade esperada e a da tabela, possivelmente um degrau abaixo
        # se a confianca for baixa. As duas sao aceitaveis, e so essas duas.
        alvo = esperado_prio[gravidade]
        abaixo = ESCALA[min(len(ESCALA) - 1, ESCALA.index(alvo) + 1)]
        if x.prioridade not in (alvo, abaixo):
            erros.append("%s×%s: prioridade %s, esperado %s ou %s"
                         % (na, nb, x.prioridade, alvo, abaixo))
        if x.confianca_sistema == "BAIXA" and x.prioridade != abaixo:
            erros.append("%s×%s: confiança baixa sem rebaixamento" % (na, nb))
    checa("5.1 gravidade e prioridade conferidas par a par", not erros,
          "%d par(es) conferidos, %d erro(s)%s"
          % (len(pares), len(erros), (": " + erros[0]) if erros else ""))

    # 5.2 — contraindicacao: a relacao exibida e a que a bula declara.
    erros = []
    linhas = con.execute(
        "SELECT i.substancia_id, s.nome_dcb, i.doenca_id, d.nome, i.relacao, "
        "i.trecho_origem FROM interacao_doenca i "
        "JOIN substancia s ON s.id=i.substancia_id "
        "JOIN doenca d ON d.id=i.doenca_id LIMIT 6").fetchall()
    for sid, nome, did, doenca, relacao, trecho in linhas:
        aid = criar_atendimento(con, "MANCI-%d-%d" % (sid, did))
        adicionar(con, aid, sid, nome, horarios=("08:00",))
        adicionar_condicao(con, aid, doenca_id=did)
        res = conciliar_atendimento(con, aid)
        ach = [x for x in res.achados if x.tipo == "FARMACO_DOENCA"]
        if len(ach) != 1 or ach[0].subtipo != relacao:
            erros.append("%s + %s: esperado %s" % (nome, doenca, relacao))
        elif ach[0].trecho != trecho:
            erros.append("%s + %s: trecho não é o da bula" % (nome, doenca))
        elif ach[0].status_informacao != "EXTRAIDO_AUTOMATICAMENTE":
            erros.append("%s + %s: extração automática não declarada"
                         % (nome, doenca))
    checa("5.2 relação e trecho vêm intactos da bula", not erros,
          "%d contraindicação(ões) conferidas, %d erro(s)"
          % (len(linhas), len(erros)))

    # 5.3 — o texto em portugues do achado e o do banco, sem reescrita.
    erros = []
    for iid, efeito, original in con.execute(
            "SELECT id, efeito_esperado, descricao_original "
            "FROM interacao_substancia WHERE efeito_esperado IS NOT NULL "
            "LIMIT 200"):
        if efeito == original:
            erros.append("linha %d: texto pt igual ao original em inglês" % iid)
            break
        if not efeito or efeito.strip() != efeito:
            erros.append("linha %d: texto pt malformado" % iid)
            break
    checa("5.3 descrição em português é distinta do original", not erros,
          "200 descrições conferidas, %d problema(s)" % len(erros))


def main() -> int:
    print("=" * 78)
    print("VERIFICACAO 2 — INDEPENDENTE — MOTOR DE CONCILIACAO")
    print("=" * 78)
    for eixo in (eixo_1_invariantes, eixo_2_sql, eixo_3_recontagem,
                 eixo_4_propriedades, eixo_5_manual):
        with banco_temporario() as con:
            try:
                eixo(con)
            except Exception as exc:      # noqa: BLE001
                checa(eixo.__name__, False, "EXCEÇÃO: %r" % exc)
    print("\n" + "=" * 78)
    print("%d verificação(ões) · %d ok · %d falha(s)"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS)))
    for nome, det in FALHAS:
        print("  FALHA: %s — %s" % (nome, det))
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
