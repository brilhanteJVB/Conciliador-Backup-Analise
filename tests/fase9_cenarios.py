# -*- coding: utf-8 -*-
"""
FASE 9 — BATERIA DE CENARIOS CLINICOS INTEGRADOS.

Dez pacientes sinteticos, dez situacoes diferentes, cada um conduzido do
inicio ao fim PELA INTERFACE — paciente, anamnese, condicoes, alergias,
medicamentos, posologia, horarios, rotina, itens, conciliacao, analise,
achados, evidencia, previsao, revisao, relatorio.

A pergunta desta fase nao e "cada modulo funciona?" — isso as fases 3 a 8 ja
responderam. E "o sistema inteiro funciona quando tudo roda junto?". Por isso
cada cenario afirma um RESULTADO ESPERADO, e nao apenas que a pagina abriu.

FARMACOLOGIA REAL, PACIENTE SINTETICO. Todos os pares, contraindicacoes,
classes e regras vem do banco e foram localizados por consulta antes de o
teste ser escrito; o que e inventado e a pessoa. Os identificadores estao
fixados de proposito: um cenario que depende da ordem do resultado de busca
nao prova nada quando a ordem muda.

TUDO NUMA COPIA DO BANCO. Dois motivos: os cenarios 3 e 4 precisam HOMOLOGAR
um modelo, e homologar em producao seria o teste ligando aquilo que a Fase 7
decidiu manter desligado (D-041); e nenhum atendimento sintetico deve sobrar
no banco de producao depois — ja aconteceu, e a Fase 9 achou o residuo.

Uso: python tests/fase9_cenarios.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in ("app", "rules", "pipeline", "tests"):
    sys.path.insert(0, str(RAIZ / _p))

from werkzeug.datastructures import MultiDict          # noqa: E402

BANCO = RAIZ / "database" / "conciliador.db"

# ------------------------------------------------------------------ fixturas
# Localizadas por consulta ao banco em 10/09/2026. Cada uma tem o motivo ao
# lado; se o banco mudar, o teste falha alto em vez de mudar de significado.
S = {
    "bromexina":     555,    # R05CB02 — grau ZERO no grafo de interacao
    "dimeticona":    677,    # P03AX05 — grau ZERO
    "macrogol":     1468,    # A06AD15 — grau ZERO
    "varfarina":    2070,
    "ibuprofeno":   1039,    # varfarina x ibuprofeno = MAIOR documentada
    "losartana":    1458,
    "dipirona":     1506,
    "haloperidol":   301,    # N05AD01 \ par SEM documento, com previsao
    "levomepromazina": 1427,  # N05AA02 /  gravada (predicao #6)
    "glibenclamida": 1000,   # CONTRAINDICADO em insuficiencia renal
    "gliclazida":   1010,    # A10BB09 \ duplicidade de 4o nivel ATC
    "glimepirida":  1016,    # A10BB12 /
    "levotiroxina": 1432,    # separar 4 h da classe A02A
    "carbonato_calcio": 1156,  # A02AC01 — o antiacido do outro lado
}
DOENCA_RENAL = 6            # insuficiencia renal

# Nomes completos e distintos, num dicionario so: e por eles que a conferencia
# de vazamento entre relatorios compara, e comparar por prefixo ja deu falso
# positivo ("Cenário 1" e substring de "Cenário 10").
PACIENTE = {
    1:  "Cenário 1 — controle negativo",
    2:  "Cenário 2 — interação documentada",
    3:  "Cenário 3 — previsão do modelo",
    4:  "Cenário 4 — regra e modelo no mesmo par",
    5:  "Cenário 5 — alergia declarada",
    6:  "Cenário 6 — contraindicação por doença",
    7:  "Cenário 7 — duplicidade terapêutica",
    8:  "Cenário 8 — conflito de horário",
    9:  "Cenário 9 — informação insuficiente",
    10: "Cenário 10 — divergência de conciliação",
}

PASSOS, FALHAS = [], []
CENARIOS = []


def checa(cenario, nome, ok, detalhe=""):
    PASSOS.append((cenario, nome, ok, detalhe))
    if not ok:
        FALHAS.append((cenario, nome, detalhe))
    print("   %s %-52s %s" % ("OK  " if ok else "ERRO", nome[:52],
                              str(detalhe)[:64]))


# =====================================================================
# CONSTRUCAO DO ATENDIMENTO — so pela interface
# =====================================================================
def novo(c, nome):
    r = c.post("/novo", data={"nome": nome, "farmaceutico": "Farm. Fase 9",
                              "crf": "CRF-AM 90009"})
    codigo = r.headers["Location"].split("/a/")[1].split("/")[0]
    c.post("/a/%s/paciente" % codigo,
           data={"nome": nome, "data_nascimento": "1958-04-12", "sexo": "F",
                 "peso_kg": "68", "altura_cm": "160",
                 "farmaceutico": "Farm. Fase 9", "crf": "CRF-AM 90009"})
    return codigo


def med(c, codigo, rotulo, sid=None, lista="EM_USO", origem="PRESCRITO",
        dose=None, unidade="mg", vezes=None, horarios=(), continuo=True):
    """Um medicamento com posologia, exatamente como a tela faz."""
    r = c.post("/a/%s/medicamento" % codigo,
               data={"nome_relatado": rotulo,
                     "escolha": ("substancia:%d" % sid) if sid else "",
                     "lista": lista, "origem": origem})
    if r.status_code != 302:
        return None
    grupo = r.headers["Location"].rstrip("/").split("/")[-1]
    campos = [("via_administracao", "oral")]
    if dose is not None:
        campos += [("dose_valor", str(dose)), ("dose_unidade", unidade)]
    if vezes is not None:
        campos.append(("vezes_por_dia", str(vezes)))
    if continuo:
        campos.append(("uso_continuo", "on"))
    campos += [("horario", h) for h in horarios]
    c.post("/a/%s/posologia/%s" % (codigo, grupo), data=MultiDict(campos))
    return grupo


def rotina_padrao(c, codigo):
    c.post("/a/%s/rotina" % codigo,
           data={"ACORDAR": "06:30", "CAFE_MANHA": "07:00", "ALMOCO": "12:00",
                 "LANCHE_TARDE": "16:00", "JANTAR": "19:30", "DORMIR": "22:30"})


def analisar(c, codigo):
    return c.post("/a/%s/analisar" % codigo, follow_redirects=True)


def resultado(sv, codigo):
    con = sv.conectar()
    try:
        return sv.resultado_atual(con, codigo)
    finally:
        con.close()


def achados_de(res, tipo=None, subtipo=None, natureza=None):
    saida = res.achados
    if tipo:
        saida = [a for a in saida if a.tipo == tipo]
    if subtipo:
        saida = [a for a in saida if a.subtipo == subtipo]
    if natureza:
        saida = [a for a in saida if a.natureza == natureza]
    return saida


def envolve(a, *sids):
    return {a.substancia_a_id, a.substancia_b_id} >= set(sids)


# =====================================================================
# CENARIO 1 — SEM PROBLEMAS (controle negativo)
# =====================================================================
def cenario_1(c, sv):
    """Tres farmacos de grau ZERO no grafo, classes ATC de 4o nivel
    distintas, nenhuma contraindicacao e nenhuma alergia. O sistema pode
    orientar; nao pode alarmar."""
    print("\nCENARIO 1 — sem problemas (controle negativo)")
    cod = novo(c, PACIENTE[1])
    med(c, cod, "Bromexina 8 mg", S["bromexina"], dose=8, vezes=3,
        horarios=("08:00", "14:00", "20:00"))
    med(c, cod, "Dimeticona 40 mg", S["dimeticona"], dose=40, vezes=3,
        horarios=("08:00", "14:00", "20:00"))
    med(c, cod, "Macrogol 13,7 g", S["macrogol"], dose=13.7, unidade="g",
        vezes=1, horarios=("08:00",))
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    graves = [a for a in res.achados if a.prioridade in ("CRITICO", "ALTO")]
    checa(1, "nenhum alerta crítico ou alto", not graves,
          "%d achado(s), 0 crítico/alto" % res.resumo["achados"]
          if not graves else [a.titulo[:40] for a in graves[:2]])
    checa(1, "nenhuma interação fármaco × fármaco",
          not achados_de(res, "FARMACO_FARMACO"),
          "%d" % len(achados_de(res, "FARMACO_FARMACO")))
    checa(1, "nenhuma duplicidade terapêutica",
          not achados_de(res, "DUPLICIDADE"))
    checa(1, "a ausência de interação é DECLARADA, não silenciada",
          any(n.motivo in ("SEM_INTERACAO_CONHECIDA", "SUBSTANCIA_SEM_COBERTURA")
              for n in res.nao_avaliado),
          "motivos: %s" % sorted({n.motivo for n in res.nao_avaliado})[:3])
    pagina = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
    checa(1, "a tela não exibe bloco de previsão", 'id="bloco-previsto"'
          not in pagina)
    CENARIOS.append((1, "sem problemas", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 2 — INTERACAO DOCUMENTADA
# =====================================================================
def cenario_2(c, sv):
    """Varfarina x ibuprofeno: MAIOR, documentada, duas fontes."""
    print("\nCENARIO 2 — interação documentada (REGRA, com evidência)")
    cod = novo(c, PACIENTE[2])
    med(c, cod, "Varfarina 5 mg", S["varfarina"], dose=5, vezes=1,
        horarios=("20:00",))
    med(c, cod, "Ibuprofeno 600 mg", S["ibuprofeno"], origem="AUTOMEDICACAO",
        dose=600, vezes=3, horarios=("08:00", "14:00", "22:00"),
        continuo=False)
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    alvo = next((a for a in achados_de(res, "FARMACO_FARMACO")
                 if envolve(a, S["varfarina"], S["ibuprofeno"])), None)
    checa(2, "a interação documentada foi detectada", alvo is not None,
          alvo.titulo[:52] if alvo else "não detectada")
    if alvo is None:
        return cod
    checa(2, "natureza DOCUMENTADO, nunca PREVISTO",
          alvo.natureza == "DOCUMENTADO", alvo.natureza)
    checa(2, "origem do achado = REGRA", alvo.origem_achado == "REGRA",
          alvo.origem_achado)
    checa(2, "gravidade MAIOR vinda da fonte",
          alvo.gravidade_fonte == "MAIOR", alvo.gravidade_fonte)
    checa(2, "prioridade CRÍTICO ou ALTO",
          alvo.prioridade in ("CRITICO", "ALTO"), alvo.prioridade)
    checa(2, "tem evidência anexada, com fonte nomeada",
          len(alvo.evidencias) > 0 and all(e.fonte for e in alvo.evidencias),
          "%d evidência(s) de %d fonte(s)"
          % (len(alvo.evidencias), len({e.fonte for e in alvo.evidencias})))
    checa(2, "não tem probabilidade de modelo",
          alvo.probabilidade_modelo is None)
    checa(2, "a origem da afirmação não aponta para predição",
          not (alvo.origem_afirmacao or "").startswith("predicao."),
          alvo.origem_afirmacao)

    det = c.get("/a/%s/achado?chave=%s"
                % (cod, alvo.grupo_chave)).data.decode("utf-8")
    checa(2, "o detalhe mostra a cadeia de evidência",
          "Cadeia de detecção" in det and "Origem no banco" in det)
    checa(2, "o detalhe NÃO mostra painel de modelo",
          "painel-modelo" not in det)
    CENARIOS.append((2, "interação documentada", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 3 — INTERACAO PREVISTA PELO MODELO
# =====================================================================
def cenario_3(c, sv, con, modelo_id):
    """Haloperidol x levomepromazina: nenhuma fonte do acervo afirma o par,
    e o modelo lhe atribui probabilidade alta."""
    print("\nCENARIO 3 — possível interação PREVISTA pelo modelo")
    a, b = sorted((S["haloperidol"], S["levomepromazina"]))
    documentado = con.execute(
        "SELECT COUNT(*) FROM interacao_substancia WHERE substancia_a_id=? "
        "AND substancia_b_id=?", (a, b)).fetchone()[0]
    checa(3, "o par realmente não tem documento no acervo", documentado == 0,
          "%d linha(s) em interacao_substancia" % documentado)

    cod = novo(c, PACIENTE[3])
    med(c, cod, "Haloperidol 1 mg", S["haloperidol"], dose=1, vezes=2,
        horarios=("08:00", "20:00"))
    med(c, cod, "Levomepromazina 25 mg", S["levomepromazina"], dose=25,
        vezes=1, horarios=("20:00",))
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    previstos = achados_de(res, natureza="PREVISTO")
    checa(3, "o motor produziu exatamente 1 achado PREVISTO",
          len(previstos) == 1, len(previstos))
    if not previstos:
        return cod
    p = previstos[0]
    checa(3, "origem do achado = MODELO", p.origem_achado == "MODELO",
          p.origem_achado)
    checa(3, "aponta para predicao.<id>",
          (p.origem_afirmacao or "").startswith("predicao."),
          p.origem_afirmacao)
    checa(3, "não tem NENHUMA evidência documental anexada",
          len(p.evidencias) == 0, len(p.evidencias))
    checa(3, "gravidade da fonte ausente — o modelo não gradua",
          p.gravidade_fonte is None)
    checa(3, "nível de evidência ausente", p.nivel_evidencia is None)
    checa(3, "confiança do sistema BAIXA", p.confianca_sistema == "BAIXA",
          p.confianca_sistema)
    checa(3, "prioridade com teto INFORMATIVO",
          p.prioridade == "INFORMATIVO", p.prioridade)
    checa(3, "probabilidade e confiança são campos separados",
          p.probabilidade_modelo is not None
          and p.confianca_sistema == "BAIXA",
          "prob=%.4f · confiança=%s" % (p.probabilidade_modelo,
                                        p.confianca_sistema))
    checa(3, "previsto NÃO entra na contagem de achados do resumo",
          res.resumo["achados"] == len(achados_de(res)) - len(previstos)
          or "achados_previstos" in res.resumo,
          "achados=%s previstos=%s" % (res.resumo.get("achados"),
                                       res.resumo.get("achados_previstos")))

    pagina = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
    checa(3, "a tela tem bloco próprio de previsão",
          'id="bloco-previsto"' in pagina)
    checa(3, "o bloco declara que não é alerta nem interação documentada",
          "não é alerta" in pagina and "não é interação documentada" in pagina)
    det = c.get("/a/%s/achado?chave=%s"
                % (cod, p.grupo_chave)).data.decode("utf-8")
    checa(3, "o detalhe declara a AUSÊNCIA de evidência documental",
          "Não há evidência documental" in det)
    for campo in ("Modelo", "Versão", "Limiar de alerta", "Semente",
                  "Versão dos dados"):
        checa(3, "o painel de rastreabilidade mostra %r" % campo,
              campo in det)
    checa(3, "o painel avisa que a contribuição não é SHAP",
          "Não é SHAP" in det or "não é SHAP" in det)
    checa(3, "o painel nega que a contribuição seja mecanismo farmacológico",
          "não é mecanismo" in det)
    checa(3, "o painel lista os atributos que pesaram",
          "O que o modelo pesou" in det)
    CENARIOS.append((3, "previsão do modelo", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 4 — DOCUMENTADA + PREVISAO PARA O MESMO PAR
# =====================================================================
def cenario_4(c, sv, con, modelo_id):
    """O par tem documento E previsao de 0,999. A arquitetura tem de bloquear
    a previsao: onde ha documento, a previsao nem existe."""
    print("\nCENARIO 4 — documentada + previsão no MESMO par")
    a, b = sorted((S["varfarina"], S["ibuprofeno"]))
    con.execute(
        "INSERT OR REPLACE INTO predicao (modelo_id, substancia_a_id, "
        "substancia_b_id, probabilidade, probabilidade_calibrada, "
        "explicacao_json) VALUES (?,?,?,?,?,?)",
        (modelo_id, a, b, 0.9990, 0.9990,
         json.dumps([{"atributo": "atc_n2_igual", "valor": 1.0,
                      "efeito": 0.31}], ensure_ascii=False)))
    con.commit()
    liberada = con.execute(
        "SELECT COUNT(*) FROM vw_predicao_liberada WHERE substancia_a_id=? "
        "AND substancia_b_id=?", (a, b)).fetchone()[0]
    checa(4, "a view bloqueia a previsão do par documentado (prob 0,999)",
          liberada == 0, "%d linha(s) liberada(s)" % liberada)

    cod = novo(c, PACIENTE[4])
    med(c, cod, "Varfarina 5 mg", S["varfarina"], dose=5, vezes=1,
        horarios=("20:00",))
    med(c, cod, "Ibuprofeno 600 mg", S["ibuprofeno"], origem="AUTOMEDICACAO",
        dose=600, vezes=3, horarios=("08:00", "14:00", "22:00"),
        continuo=False)
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    do_par = [x for x in res.achados
              if x.tipo == "FARMACO_FARMACO" and envolve(x, a, b)]
    checa(4, "o par produziu achado, e ele é DOCUMENTADO",
          len(do_par) == 1 and do_par[0].natureza == "DOCUMENTADO",
          "%d achado(s): %s" % (len(do_par),
                                [x.natureza for x in do_par]))
    checa(4, "nenhum achado PREVISTO para o par documentado",
          not [x for x in do_par if x.natureza == "PREVISTO"])
    checa(4, "a regra documental prevaleceu, sem alerta duplicado",
          len({x.grupo_chave for x in do_par}) == len(do_par) == 1)
    pagina = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
    checa(4, "a tela não mostra bloco de previsão para este paciente",
          'id="bloco-previsto"' not in pagina)

    con.execute("DELETE FROM predicao WHERE substancia_a_id=? AND "
                "substancia_b_id=? AND modelo_id=?", (a, b, modelo_id))
    con.commit()
    CENARIOS.append((4, "regra × modelo", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 5 — ALERGIA
# =====================================================================
def cenario_5(c, sv):
    print("\nCENARIO 5 — alergia declarada e medicamento em uso")
    cod = novo(c, PACIENTE[5])
    c.post("/a/%s/alergia" % cod,
           data={"substancia_id": S["dipirona"],
                 "reacao": "urticária e edema de lábios", "gravidade": "GRAVE"})
    med(c, cod, "Dipirona 500 mg", S["dipirona"], origem="AUTOMEDICACAO",
        dose=500, vezes=4, horarios=("06:00", "12:00", "18:00", "00:00"),
        continuo=False)
    med(c, cod, "Losartana 50 mg", S["losartana"], dose=50, vezes=1,
        horarios=("08:00",))
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    alergias = achados_de(res, "FARMACO_ALERGIA")
    checa(5, "o achado de alergia apareceu", len(alergias) >= 1,
          "%d" % len(alergias))
    if not alergias:
        return cod
    al = alergias[0]
    checa(5, "prioridade derivada da lógica do sistema, não do acaso",
          al.prioridade in ("CRITICO", "ALTO"), al.prioridade)
    checa(5, "a justificativa da prioridade está escrita",
          bool(al.justificativa_prioridade),
          (al.justificativa_prioridade or "")[:52])
    checa(5, "o achado cita a reação relatada pelo paciente",
          "urticária" in (al.contexto_paciente or "") + (al.explicacao or ""),
          (al.contexto_paciente or "")[:52])
    checa(5, "o achado é DOCUMENTADO pela declaração do paciente, não previsto",
          al.natureza != "PREVISTO", al.natureza)
    CENARIOS.append((5, "alergia", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 6 — CONTRAINDICACAO POR DOENCA
# =====================================================================
def cenario_6(c, sv):
    """Glibenclamida e contraindicada em insuficiencia renal (bula ANVISA)."""
    print("\nCENARIO 6 — contraindicação contextualizada ao paciente")
    cod = novo(c, PACIENTE[6])
    c.post("/a/%s/condicao" % cod, data={"doenca_id": DOENCA_RENAL})
    med(c, cod, "Glibenclamida 5 mg", S["glibenclamida"], dose=5, vezes=1,
        horarios=("07:30",))
    med(c, cod, "Macrogol 13,7 g", S["macrogol"], dose=13.7, unidade="g",
        vezes=1, horarios=("08:00",))
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    doenca = achados_de(res, "FARMACO_DOENCA")
    checa(6, "o achado fármaco × doença apareceu", len(doenca) >= 1,
          "%d" % len(doenca))
    if not doenca:
        return cod
    d = doenca[0]
    checa(6, "está contextualizado à condição DESTE paciente",
          "renal" in (d.contexto_paciente or d.titulo or "").lower(),
          (d.contexto_paciente or d.titulo or "")[:52])
    checa(6, "o subtipo declara a relação (contraindicado/cautela)",
          d.subtipo in ("CONTRAINDICADO", "USAR_COM_CAUTELA", "EVITAR"),
          d.subtipo)
    checa(6, "traz fonte e trecho da bula",
          bool(d.fonte) and (bool(d.trecho) or bool(d.evidencias)),
          "%s · %d evidência(s)" % (d.fonte, len(d.evidencias)))
    checa(6, "declara que a extração foi automática, não revisada",
          d.confianca_extracao in ("EXTRAIDA_AUTOMATICAMENTE", "CALCULADO",
                                   "REGEX"), d.confianca_extracao)
    CENARIOS.append((6, "contraindicação", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 7 — DUPLICIDADE TERAPEUTICA
# =====================================================================
def cenario_7(c, sv):
    """Gliclazida + glimepirida: duas sulfonilureias, mesmo 4o nivel ATC."""
    print("\nCENARIO 7 — duplicidade terapêutica (mesma classe ATC de 4º nível)")
    cod = novo(c, PACIENTE[7])
    med(c, cod, "Gliclazida 30 mg", S["gliclazida"], dose=30, vezes=1,
        horarios=("07:30",))
    med(c, cod, "Glimepirida 2 mg", S["glimepirida"], dose=2, vezes=1,
        horarios=("07:30",))
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    dup = achados_de(res, "DUPLICIDADE")
    checa(7, "a duplicidade foi detectada", len(dup) >= 1, "%d" % len(dup))
    if not dup:
        return cod
    d = next((x for x in dup if x.subtipo == "MESMA_CLASSE_ATC4"), dup[0])
    checa(7, "é duplicidade de CLASSE, no 4º nível ATC",
          d.subtipo == "MESMA_CLASSE_ATC4", d.subtipo)
    checa(7, "nomeia as duas substâncias",
          bool(d.item_a) and bool(d.item_b), "%s × %s" % (d.item_a, d.item_b))
    checa(7, "não é apresentada como interação fármaco × fármaco",
          d.tipo == "DUPLICIDADE", d.tipo)
    checa(7, "explica por que a classe importa", bool(d.explicacao),
          (d.explicacao or "")[:52])
    CENARIOS.append((7, "duplicidade", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 8 — CONFLITO DE HORARIO
# =====================================================================
def cenario_8(c, sv):
    """Levotiroxina exige 4 h de separacao da classe A02A (antiacidos). O
    carbonato de calcio e A02AC01. Marcados para o MESMO horario."""
    print("\nCENARIO 8 — conflito de horário entre medicamentos")
    cod = novo(c, PACIENTE[8])
    med(c, cod, "Levotiroxina 50 mcg", S["levotiroxina"], dose=50,
        unidade="mcg", vezes=1, horarios=("07:00",))
    med(c, cod, "Carbonato de cálcio 500 mg", S["carbonato_calcio"], dose=500,
        vezes=1, horarios=("07:00",))
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    agenda = res.agenda
    temporais = [a for a in res.achados
                 if a.tipo in ("REGRA_ADMINISTRACAO", "HORARIO", "SEPARACAO")
                 or a.alvo_tipo == "POSOLOGIA"]
    checa(8, "a agenda foi montada e tem eventos",
          agenda is not None and len(agenda.eventos) > 0,
          "%d evento(s)" % (len(agenda.eventos) if agenda else 0))
    checa(8, "o motor de horários registrou conflito ou orientação",
          bool(agenda and agenda.conflitos) or bool(temporais),
          "%d conflito(s) na agenda · %d achado(s) temporal(is)"
          % (len(agenda.conflitos) if agenda else 0, len(temporais)))
    if agenda and agenda.conflitos:
        conf = agenda.conflitos[0]
        checa(8, "o conflito nomeia os itens envolvidos e a justificativa",
              len(conf.itens) >= 1 and bool(conf.justificativa),
              "%s — %s" % (conf.tipo, (conf.justificativa or "")[:40]))
        checa(8, "a classificação do conflito é uma das três do motor",
              conf.classificacao in ("CONFLITO_CONFIRMADO", "POSSIVEL_CONFLITO",
                                     "REGRA_DESCONHECIDA"),
              conf.classificacao)
        checa(8, "quando a fonte não publica intervalo, ele NÃO é inventado",
              all(x.intervalo_exigido is not None
                  or x.classificacao == "REGRA_DESCONHECIDA"
                  or not x.tipo.startswith("SEPARACAO")
                  for x in agenda.conflitos),
              [(x.tipo, x.intervalo_exigido) for x in agenda.conflitos][:2])
    checa(8, "o que não pôde ser avaliado no tempo está declarado",
          any(n.motivo in ("HORARIO_NAO_INFORMADO",
                           "REGRA_SEM_INTERVALO_ESTABELECIDO",
                           "POSOLOGIA_NAO_INFORMADA")
              for n in res.nao_avaliado) or bool(agenda and agenda.conflitos),
          sorted({n.motivo for n in res.nao_avaliado})[:3])
    CENARIOS.append((8, "conflito de horário", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 9 — INFORMACAO INSUFICIENTE
# =====================================================================
def cenario_9(c, sv):
    """De proposito: um item que o cadastro nao reconhece, um sem dose e um
    sem horario. O sistema tem de DECLARAR o que nao avaliou."""
    print("\nCENARIO 9 — informação insuficiente")
    cod = novo(c, PACIENTE[9])
    med(c, cod, "aquele comprimido azul da vizinha", None, dose=None,
        vezes=None, horarios=(), continuo=False)
    med(c, cod, "Losartana (dose que não sei)", S["losartana"], dose=None,
        vezes=1, horarios=())
    analisar(c, cod)
    res = resultado(sv, cod)

    motivos = {n.motivo for n in res.nao_avaliado}
    checa(9, "o item não reconhecido foi declarado, não ignorado",
          "SUBSTANCIA_NAO_RECONHECIDA" in motivos, sorted(motivos)[:4])
    checa(9, "a dose ausente foi declarada",
          "DOSE_NAO_INFORMADA" in motivos
          or bool(achados_de(res, "POSOLOGIA")), sorted(motivos)[:4])
    checa(9, "o horário ausente foi declarado",
          "HORARIO_NAO_INFORMADO" in motivos or "POSOLOGIA_NAO_INFORMADA"
          in motivos, sorted(motivos)[:4])
    checa(9, "o sistema NÃO concluiu ausência de risco",
          not any("não há risco" in (a.explicacao or "").lower()
                  or "sem risco" in (a.explicacao or "").lower()
                  for a in res.achados))
    checa(9, "as limitações da análise estão escritas",
          len(res.limitacoes) > 0, "%d limitação(ões)" % len(res.limitacoes))

    pagina = c.get("/a/%s/resultados" % cod).data.decode("utf-8")
    checa(9, "a tela mostra a seção do que não foi avaliado",
          "não avaliou" in pagina or "não avaliado" in pagina.lower())
    checa(9, "o item não reconhecido aparece marcado na tela",
          "não reconhecido" in c.get("/a/%s/medicamentos" % cod)
          .data.decode("utf-8"))
    CENARIOS.append((9, "informação insuficiente", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# CENARIO 10 — DIVERGENCIA DE CONCILIACAO
# =====================================================================
def cenario_10(c, sv):
    """A receita diz 50 mg uma vez ao dia; a paciente relata 100 mg."""
    print("\nCENARIO 10 — divergência entre o prescrito e o relatado")
    cod = novo(c, PACIENTE[10])
    med(c, cod, "Losartana 50 mg", S["losartana"], lista="PRESCRITA",
        dose=50, vezes=1, horarios=("08:00",))
    med(c, cod, "Losartana 50 mg", S["losartana"], lista="RELATADA",
        dose=100, vezes=1, horarios=("08:00",))
    med(c, cod, "Macrogol 13,7 g", S["macrogol"], lista="RELATADA",
        origem="AUTOMEDICACAO", dose=13.7, unidade="g", vezes=1,
        horarios=("08:00",))
    rotina_padrao(c, cod)
    analisar(c, cod)
    res = resultado(sv, cod)

    div = [p for p in res.divergencias if p.tipo_divergencia]
    checa(10, "a divergência foi identificada", len(div) >= 1,
          "%d: %s" % (len(div), sorted({p.tipo_divergencia for p in div})))
    dose = next((p for p in div if p.tipo_divergencia == "DOSE_DIFERENTE"), None)
    checa(10, "a divergência de dose foi classificada corretamente",
          dose is not None,
          "prescrito=%s relatado=%s" % (dose.valor_prescrito,
                                        dose.valor_relatado) if dose else "—")
    checa(10, "a intencionalidade NÃO foi determinada automaticamente",
          all(p.intencionalidade == "NAO_DETERMINADA" for p in div),
          sorted({p.intencionalidade for p in div}))
    so_relato = [p for p in div if p.tipo_divergencia == "SO_NO_RELATO"]
    checa(10, "o item só relatado também virou divergência",
          len(so_relato) >= 1, "%d" % len(so_relato))

    con = sv.conectar()
    try:
        gravadas = con.execute(
            "SELECT COUNT(*) FROM conciliacao_par cp JOIN conciliacao co "
            "ON co.id = cp.conciliacao_id JOIN atendimento a "
            "ON a.id = co.atendimento_id WHERE a.codigo=? AND "
            "cp.intencionalidade <> 'NAO_DETERMINADA'", (cod,)).fetchone()[0]
    finally:
        con.close()
    checa(10, "nada foi gravado como intencional sem assinatura",
          gravadas == 0, "%d linha(s)" % gravadas)

    pagina = c.get("/a/%s/conciliacao" % cod).data.decode("utf-8")
    checa(10, "a tela de conciliação mostra as duas listas lado a lado",
          "Prescrito" in pagina and "Relatado pelo paciente" in pagina)
    CENARIOS.append((10, "divergência", cod, res.resumo["achados"]))
    return cod


# =====================================================================
# RELATORIO DE CADA CENARIO
# =====================================================================
def relatorios(c, sv):
    print("\nRELATORIO — um por cenário, conferindo que não se misturam")
    textos = {}
    for numero, nome, cod, _n in CENARIOS:
        r = c.get("/a/%s/relatorio" % cod)
        t = c.get("/a/%s/relatorio.txt" % cod)
        ok = r.status_code == 200 and t.status_code == 200
        textos[cod] = t.data.decode("utf-8")
        checa(numero, "relatório de %r abre em HTML e em texto" % nome[:22],
              ok, "%d bytes" % len(textos[cod]))
    # O nome COMPLETO, nunca o prefixo: "Cenário 1" e substring de
    # "Cenário 10", e comparar por prefixo acusava vazamento onde nao havia.
    # Foi o primeiro falso positivo desta bateria.
    nomes = {cod: PACIENTE[numero] for numero, _n, cod, _x in CENARIOS}
    vazou = []
    for cod, texto in textos.items():
        for outro, nome_outro in nomes.items():
            if outro != cod and nome_outro in texto:
                vazou.append((cod, nome_outro))
    checa(0, "nenhum relatório cita o paciente de outro cenário", not vazou,
          vazou[:2])
    checa(0, "cada relatório cita o SEU próprio paciente",
          all(nomes[cod] in texto for cod, texto in textos.items()),
          "%d relatório(s)" % len(textos))


# =====================================================================
def main() -> int:
    print("=" * 78)
    print("FASE 9 — BATERIA DE CENARIOS CLINICOS INTEGRADOS")
    print("=" * 78)
    t0 = time.time()
    tmp = Path(tempfile.mkdtemp())
    copia = tmp / "conciliador.db"
    shutil.copy(BANCO, copia)

    import servicos as sv
    sv.BANCO = copia
    import web
    web.app.config["TESTING"] = True
    c = web.app.test_client()

    con = sqlite3.connect(copia)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        # ---- modelo homologado SO NA COPIA, para os cenarios 3 e 4
        # O modelo homologado tem de ser AQUELE cujas previsoes existem: as
        # 600 linhas de `predicao` pertencem a um modelo_id so, e homologar o
        # outro daria uma view vazia por motivo errado — o cenario 3 passaria
        # a testar nada e ainda pareceria correto.
        linha = con.execute(
            "SELECT m.id, m.versao, COUNT(p.id) n FROM modelo m "
            "LEFT JOIN predicao p ON p.modelo_id = m.id "
            "WHERE m.nome='m1_existencia_interacao' "
            "GROUP BY m.id ORDER BY n DESC, m.id LIMIT 1").fetchone()
        if linha is None:
            print("\nBANCO SEM MODELO REGISTRADO — rode `python ml/executar_tudo.py`.")
            return 1
        modelo_id, versao, n_prev = linha
        if not n_prev:
            print("\nNENHUM MODELO TEM PREVISAO GRAVADA — rode "
                  "`python ml/80_fila_curadoria.py`.")
            return 1
        con.execute("UPDATE modelo SET status='HOMOLOGADO', limiar_alerta=0.90,"
                    " ativo=1 WHERE id=?", (modelo_id,))
        con.commit()
        print("modelo homologado NA COPIA: %s — %d previsao(oes), limiar 0,90"
              % (versao, n_prev))
        print("banco de trabalho: %s\n" % copia)

        cenario_1(c, sv)
        cenario_2(c, sv)
        cenario_3(c, sv, con, modelo_id)
        cenario_4(c, sv, con, modelo_id)
        cenario_5(c, sv)
        cenario_6(c, sv)
        cenario_7(c, sv)
        cenario_8(c, sv)
        cenario_9(c, sv)
        cenario_10(c, sv)
        relatorios(c, sv)

        # ---- o banco de PRODUCAO nao pode ter sido tocado
        prod = sqlite3.connect(BANCO)
        try:
            ativos = prod.execute(
                "SELECT COUNT(*) FROM modelo WHERE ativo=1").fetchone()[0]
            atend = prod.execute(
                "SELECT COUNT(*) FROM atendimento WHERE codigo IN (%s)"
                % ",".join("?" * len(CENARIOS)),
                [c_ for _n, _r, c_, _x in CENARIOS]).fetchone()[0]
        finally:
            prod.close()
        print("\nPRODUCAO — o teste nao pode ter deixado rastro")
        checa(0, "nenhum modelo ficou ativo no banco de produção",
              ativos == 0, "%d ativo(s)" % ativos)
        checa(0, "nenhum atendimento do teste foi para produção",
              atend == 0, "%d atendimento(s)" % atend)
    finally:
        con.close()
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 78)
    print("%d cenário(s) · %d conferência(s) · %d ok · %d falha(s) · %.1fs"
          % (len(CENARIOS), len(PASSOS), len(PASSOS) - len(FALHAS),
             len(FALHAS), time.time() - t0))
    for numero, nome, det in FALHAS:
        print("  FALHA [cenário %s] %s — %s" % (numero, nome, det))
    if not FALHAS:
        print("\nOS DEZ CENARIOS PRODUZIRAM O RESULTADO ESPERADO.")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
