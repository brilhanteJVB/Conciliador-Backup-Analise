# -*- coding: utf-8 -*-
"""
VERIFICACAO 1 — FUNCIONAL — a aplicacao (Fase 6).

Exercita a aplicacao pelo caminho do usuario: requisicoes HTTP reais contra as
rotas do Flask, com formularios preenchidos como a tela preenche. Nao chama
servico por dentro — se a rota, o formulario ou o template estiverem errados,
o teste falha.

Cobre a bateria da especificacao (secao 25): fluxo completo, paciente sem
achados, paciente com varios achados, medicamento sem regra, informacao
incompleta, divergencia, conflito de horario, interacao, alergia, condicao
clinica, duplicidade, item/suplemento e erro de entrada.

LIMPEZA: os atendimentos criados aqui sao apagados no final, inclusive se um
teste falhar. Nenhum deles sobrevive no banco.

Uso: python tests/teste_aplicacao.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in ("app", "rules", "pipeline", "tests"):
    sys.path.insert(0, str(RAIZ / _p))

from werkzeug.datastructures import MultiDict  # noqa: E402

import busca                       # noqa: E402
import servicos as sv              # noqa: E402
import web                         # noqa: E402

RESULTADOS = []
CRIADOS = []


def registra(nome, ok, detalhe=""):
    RESULTADOS.append((nome, ok, detalhe))
    print("   %s %-50s %s" % ("OK  " if ok else "ERRO", nome[:50],
                              str(detalhe)[:72]))


def cliente():
    web.app.config["TESTING"] = True
    return web.app.test_client()


def criar(c, nome="Paciente de teste", farmaceutico="Farm. Teste",
          crf="CRF-TS 001") -> str:
    r = c.post("/novo", data={"nome": nome, "farmaceutico": farmaceutico,
                              "crf": crf})
    codigo = r.headers["Location"].split("/a/")[1].split("/")[0]
    CRIADOS.append(codigo)
    return codigo


def texto(resposta) -> str:
    return resposta.data.decode("utf-8")


def add_med(c, codigo, termo, nome, lista="RELATADA", origem="PRESCRITO"):
    """Passa pela busca da tela e adiciona o primeiro resultado."""
    con = sv.conectar()
    try:
        achados = busca.buscar_medicamento(con, termo)
    finally:
        con.close()
    escolha = achados[0].chave if achados else ""
    r = c.post("/a/%s/medicamento" % codigo,
               data={"nome_relatado": nome, "escolha": escolha,
                     "lista": lista, "origem": origem})
    return r.headers.get("Location", "").rstrip("/").split("/")[-1], achados


def add_posologia(c, codigo, grupo_id, **campos):
    horarios = campos.pop("horarios", [])
    dados = {k: v for k, v in campos.items() if v is not None}
    dados = {k: ("on" if v is True else v) for k, v in dados.items()}
    campos_multi = MultiDict([(k, str(v)) for k, v in dados.items()]
                             + [("horario", h) for h in horarios])
    return c.post("/a/%s/posologia/%s" % (codigo, grupo_id), data=campos_multi)


def limpar():
    if not CRIADOS:
        return
    con = sv.conectar()
    try:
        for codigo in CRIADOS:
            linha = con.execute("SELECT id, paciente_id FROM atendimento "
                                "WHERE codigo=?", (codigo,)).fetchone()
            if not linha:
                continue
            con.execute("DELETE FROM atendimento WHERE id=?", (linha[0],))
            con.execute("DELETE FROM paciente WHERE id=?", (linha[1],))
        con.commit()
    finally:
        con.close()


# =====================================================================
# 1 — FLUXO COMPLETO
# =====================================================================
def t01_fluxo_completo(c):
    """criar → anamnese → medicamento → posologia → rotina → analisar →
    achado → evidência → relatório. É o teste que prova que existe sistema."""
    codigo = criar(c, "Fluxo Completo")

    r = c.post("/a/%s/paciente" % codigo,
               data={"nome": "Fluxo Completo", "data_nascimento": "1955-04-02",
                     "sexo": "F", "peso_kg": "70", "altura_cm": "160",
                     "farmaceutico": "Farm. Teste", "crf": "CRF-TS 001"})
    registra("01.1 paciente salvo e redireciona para anamnese",
             r.status_code == 302 and "anamnese" in r.headers["Location"],
             r.headers.get("Location"))

    con = sv.conectar()
    try:
        cond = busca.buscar_condicao(con, "hipertens")
        subst = busca.buscar_substancia(con, "dipirona")
    finally:
        con.close()
    c.post("/a/%s/condicao" % codigo, data={"doenca_id": cond[0].id})
    c.post("/a/%s/alergia" % codigo,
           data={"substancia_id": subst[0].substancia_id,
                 "reacao": "urticária", "gravidade": "GRAVE"})
    c.post("/a/%s/habitos" % codigo,
           data={"situacao_ALCOOL": "ATUAL", "frequencia_ALCOOL": "diário",
                 "situacao_TABAGISMO": "NUNCA"})
    pagina = texto(c.get("/a/%s/anamnese" % codigo))
    registra("01.2 condição, alergia e hábito aparecem na anamnese",
             cond[0].nome in pagina and subst[0].rotulo in pagina
             and "urticária" in pagina)

    grupo, achados_busca = add_med(c, codigo, "varfarina", "Varfarina 5 mg",
                                   "PRESCRITA")
    registra("01.3 busca encontrou e a tela adicionou",
             bool(achados_busca) and grupo.isdigit(),
             "%s -> grupo %s" % (achados_busca[0].rotulo, grupo))

    add_posologia(c, codigo, grupo, dose_valor="5", dose_unidade="mg",
                  vezes_por_dia="1", via_administracao="oral",
                  uso_continuo=True, horarios=["20:00"])
    pagina = texto(c.get("/a/%s/medicamentos" % codigo))
    registra("01.4 posologia salva e exibida na lista",
             "5 mg" in pagina and "20:00" in pagina)

    r = c.post("/a/%s/rotina" % codigo,
               data={"ACORDAR": "06:30", "CAFE_MANHA": "07:00",
                     "ALMOCO": "12:00", "JANTAR": "19:30", "DORMIR": "22:30"})
    registra("01.5 rotina salva e leva a alimentos",
             r.status_code == 302 and "itens" in r.headers["Location"])

    r = c.post("/a/%s/analisar" % codigo, follow_redirects=True)
    pagina = texto(r)
    registra("01.6 análise executa e mostra resultados",
             r.status_code == 200 and "Resultados da conciliação" in pagina)

    con = sv.conectar()
    try:
        res = sv.resultado_atual(con, codigo)
    finally:
        con.close()
    alvo = res.achados[0] if res.achados else None
    if alvo is None:
        return registra("01.7 abrir achado", False, "nenhum achado produzido")
    r = c.get("/a/%s/achado?chave=%s" % (codigo, alvo.grupo_chave))
    pagina = texto(r)
    registra("01.7 achado abre com os seis eixos",
             r.status_code == 200
             and "Gravidade da fonte" in pagina
             and "Confiança do sistema" in pagina
             and "Prioridade de exibição" in pagina
             and "Natureza da afirmação" in pagina
             and "Neste paciente" in pagina
             and "Nível de evidência" in pagina)
    registra("01.8 a evidência aparece com fonte e origem",
             "Evidência" in pagina and "Origem no banco" in pagina)

    r = c.post("/a/%s/achado/revisar" % codigo,
               data={"chave": alvo.grupo_chave, "situacao": "REVISADO",
                     "profissional": "Farm. Teste", "crf": "CRF-TS 001",
                     "observacao": "conferido com a paciente"},
               follow_redirects=True)
    registra("01.9 revisão profissional registrada",
             "conferido com a paciente" in texto(r))

    r = c.get("/a/%s/relatorio" % codigo)
    pagina = texto(r)
    registra("01.10 relatório traz resumo, achados e limitações",
             r.status_code == 200 and "Conciliação medicamentosa" in pagina
             and "Resumo" in pagina and "Farmacoterapia" in pagina
             and "O que o sistema não avaliou" in pagina)

    r = c.get("/a/%s/relatorio.txt" % codigo)
    registra("01.11 relatório em texto puro",
             r.status_code == 200 and "CONCILIAÇÃO MEDICAMENTOSA" in texto(r))


# =====================================================================
# 2 — CENARIOS CLINICOS
# =====================================================================
def t02_interacao(c):
    codigo = criar(c, "Interação Maior")
    con = sv.conectar()
    try:
        par = con.execute(
            "SELECT sa.nome_dcb, sb.nome_dcb FROM interacao_substancia i "
            "JOIN substancia sa ON sa.id=i.substancia_a_id "
            "JOIN substancia sb ON sb.id=i.substancia_b_id "
            "WHERE i.gravidade='MAIOR' AND sa.n_produtos_ativos>20 "
            "AND sb.n_produtos_ativos>20 LIMIT 1").fetchone()
    finally:
        con.close()
    for nome in par:
        g, _ = add_med(c, codigo, nome, nome)
        add_posologia(c, codigo, g, dose_valor="1", dose_unidade="comprimido",
                      vezes_por_dia="1", horarios=["08:00"])
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("02 interação maior aparece como Alto",
             "Interação entre" in pagina and "Alto" in pagina,
             "%s × %s" % par)


def t03_alergia(c):
    codigo = criar(c, "Alergia Crítica")
    con = sv.conectar()
    try:
        s = busca.buscar_substancia(con, "dipirona")[0]
    finally:
        con.close()
    g, _ = add_med(c, codigo, "dipirona", "Dipirona 500 mg")
    add_posologia(c, codigo, g, dose_valor="500", dose_unidade="mg",
                  vezes_por_dia="3", horarios=["08:00", "14:00", "20:00"])
    c.post("/a/%s/alergia" % codigo,
           data={"substancia_id": s.substancia_id, "reacao": "anafilaxia",
                 "gravidade": "ANAFILAXIA"})
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("03 alergia à substância em uso vira Crítico",
             "Crítico" in pagina and "Alergia" in pagina)


def t04_condicao(c):
    codigo = criar(c, "Contraindicação")
    con = sv.conectar()
    try:
        ci = con.execute(
            "SELECT s.nome_dcb, i.doenca_id, d.nome FROM interacao_doenca i "
            "JOIN substancia s ON s.id=i.substancia_id "
            "JOIN doenca d ON d.id=i.doenca_id "
            "WHERE i.relacao='CONTRAINDICADO' AND d.nome NOT IN "
            "('gravidez','lactação') ORDER BY s.n_produtos_ativos DESC "
            "LIMIT 1").fetchone()
    finally:
        con.close()
    g, _ = add_med(c, codigo, ci[0], ci[0])
    add_posologia(c, codigo, g, dose_valor="1", dose_unidade="comprimido",
                  vezes_por_dia="1", horarios=["08:00"])
    c.post("/a/%s/condicao" % codigo, data={"doenca_id": ci[1]})
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("04 contraindicação por condição aparece, marcada como extraída",
             "Contraindicação" in pagina
             and "Extraído automaticamente" in pagina,
             "%s + %s" % (ci[0], ci[2]))


def t05_duplicidade(c):
    codigo = criar(c, "Duplicidade")
    for nome in ("Dipirona 500 mg (marca)", "Dipirona genérico"):
        g, _ = add_med(c, codigo, "dipirona", nome)
        add_posologia(c, codigo, g, dose_valor="500", dose_unidade="mg",
                      vezes_por_dia="1", horarios=["08:00"])
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("05 marca e genérico do mesmo ativo viram duplicidade",
             "Duplicidade" in pagina)


def t06_divergencia(c):
    codigo = criar(c, "Divergência de dose")
    g1, _ = add_med(c, codigo, "losartana", "Losartana 50 mg", "PRESCRITA")
    add_posologia(c, codigo, g1, dose_valor="50", dose_unidade="mg",
                  vezes_por_dia="1", horarios=["08:00"])
    g2, _ = add_med(c, codigo, "losartana", "Losartana 50 mg", "RELATADA")
    add_posologia(c, codigo, g2, dose_valor="100", dose_unidade="mg",
                  vezes_por_dia="1", horarios=["08:00"])
    pagina = texto(c.get("/a/%s/conciliacao" % codigo))
    registra("06.1 conciliação mostra a divergência de dose",
             "Dose diferente" in pagina and "50 mg" in pagina
             and "100 mg" in pagina)
    registra("06.2 intencionalidade nasce não determinada",
             "Não determinada" in pagina)
    r = c.post("/a/%s/divergencia/registrar" % codigo,
               data={"chave": "DOSE_DIFERENTE|" + _sid(codigo, "losartana"),
                     "intencionalidade": "INTENCIONAL",
                     "profissional": "Farm. Teste", "crf": "CRF-TS 001",
                     "observacao": "médico ajustou na consulta"},
               follow_redirects=True)
    registra("06.3 profissional registra a intencionalidade",
             "médico ajustou na consulta" in texto(r))


def _sid(codigo, termo):
    con = sv.conectar()
    try:
        r = busca.buscar_substancia(con, termo)
        return str(r[0].substancia_id)
    finally:
        con.close()


def t07_conflito_horario(c):
    codigo = criar(c, "Conflito de horário")
    con = sv.conectar()
    try:
        jej = con.execute(
            "SELECT s.nome_dcb FROM regra_administracao r "
            "JOIN substancia s ON s.id=r.substancia_id WHERE r.tipo='JEJUM' "
            "ORDER BY s.n_produtos_ativos DESC LIMIT 1").fetchone()[0]
    finally:
        con.close()
    g, _ = add_med(c, codigo, jej, jej)
    add_posologia(c, codigo, g, dose_valor="1", dose_unidade="comprimido",
                  vezes_por_dia="1", horarios=["07:05"])
    c.post("/a/%s/rotina" % codigo,
           data={"ACORDAR": "06:30", "CAFE_MANHA": "07:00",
                 "ALMOCO": "12:00", "JANTAR": "19:30", "DORMIR": "22:30"})
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("07 jejum junto do café da manhã vira achado de horário",
             "Horário de administração" in pagina, jej)


def t08_item(c):
    codigo = criar(c, "Item declarado")
    con = sv.conectar()
    try:
        it = con.execute(
            "SELECT s.nome_dcb, ii.item_id, i.nome FROM interacao_item ii "
            "JOIN substancia s ON s.id=ii.substancia_id "
            "JOIN item_nao_medicamentoso i ON i.id=ii.item_id "
            "ORDER BY s.n_produtos_ativos DESC LIMIT 1").fetchone()
    finally:
        con.close()
    g, _ = add_med(c, codigo, it[0], it[0])
    add_posologia(c, codigo, g, dose_valor="1", dose_unidade="comprimido",
                  vezes_por_dia="1", horarios=["08:00"])
    c.post("/a/%s/item" % codigo,
           data={"item_id": it[1], "frequencia": "DIARIO",
                 "horario_habitual": "08:00"})
    pagina_itens = texto(c.get("/a/%s/itens" % codigo))
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("08 item declarado é registrado e entra na análise",
             it[2] in pagina_itens and it[2] in pagina, "%s × %s" % (it[0], it[2]))


def t09_sem_achado(c):
    codigo = criar(c, "Sem achados")
    con = sv.conectar()
    try:
        s = con.execute(
            "SELECT s.nome_dcb FROM substancia s WHERE s.n_produtos_ativos>10 "
            "AND NOT EXISTS (SELECT 1 FROM interacao_substancia i "
            "  WHERE i.substancia_a_id=s.id OR i.substancia_b_id=s.id) "
            "ORDER BY s.n_produtos_ativos DESC LIMIT 1").fetchone()[0]
    finally:
        con.close()
    g, _ = add_med(c, codigo, s, s)
    add_posologia(c, codigo, g, dose_valor="1", dose_unidade="comprimido",
                  vezes_por_dia="1", horarios=["08:00"])
    for h in ("TABAGISMO", "ALCOOL", "CAFEINA"):
        c.post("/a/%s/habitos" % codigo, data={"situacao_" + h: "NUNCA"})
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("09 sem achado clínico, a tela diz que isso não é ausência de risco",
             "não" in pagina and "ausência de risco" in pagina, s)


def t10_sem_regra(c):
    codigo = criar(c, "Sem cobertura")
    con = sv.conectar()
    try:
        s = con.execute(
            "SELECT s.nome_dcb FROM substancia s WHERE s.n_produtos_ativos>10 "
            "AND NOT EXISTS (SELECT 1 FROM interacao_substancia i "
            "  WHERE i.substancia_a_id=s.id OR i.substancia_b_id=s.id) "
            "LIMIT 1").fetchone()[0]
    finally:
        con.close()
    g, _ = add_med(c, codigo, s, s)
    add_posologia(c, codigo, g, dose_valor="1", dose_unidade="comprimido",
                  vezes_por_dia="1", horarios=["08:00"])
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("10 substância sem cobertura é declarada, não silenciada",
             "sem cobertura na base" in pagina.lower()
             or "Substância sem cobertura" in pagina, s)


def t11_nao_reconhecido(c):
    codigo = criar(c, "Não reconhecido")
    r = c.post("/a/%s/medicamento" % codigo,
               data={"nome_relatado": "aquele comprimido branco",
                     "escolha": "", "lista": "RELATADA",
                     "origem": "NAO_INFORMADO"})
    lista = texto(c.get("/a/%s/medicamentos" % codigo))
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    registra("11 item não reconhecido é marcado na tela e no resultado",
             r.status_code == 302 and "não reconhecido" in lista
             and "não reconhecido" in pagina.lower())


def t12_incompleto(c):
    codigo = criar(c, "Informação incompleta")
    g, _ = add_med(c, codigo, "dipirona", "Dipirona")
    # sem dose, sem horário, sem rotina
    add_posologia(c, codigo, g, vezes_por_dia="1")
    pagina = texto(c.get("/a/%s/resultados" % codigo))
    pendencias = texto(c.get("/a/%s/medicamentos" % codigo))
    registra("12.1 falta de dado vira declaração, não alerta grave",
             "Dose não informada" in pagina or "não informada" in pagina)
    registra("12.2 as pendências aparecem no painel lateral",
             "O que ainda falta" in pendencias and "Rotina não informada" in pendencias)


def t13_polimedicado(c):
    codigo = criar(c, "Polimedicado")
    con = sv.conectar()
    try:
        nomes = [n for (n,) in con.execute(
            "SELECT nome_dcb FROM substancia WHERE n_produtos_ativos>40 "
            "ORDER BY n_produtos_ativos DESC LIMIT 6")]
    finally:
        con.close()
    for nome in nomes:
        g, _ = add_med(c, codigo, nome, nome)
        add_posologia(c, codigo, g, dose_valor="1", dose_unidade="comprimido",
                      vezes_por_dia="1", horarios=["08:00"])
    r = c.post("/a/%s/analisar" % codigo, follow_redirects=True)
    pagina = texto(r)
    con = sv.conectar()
    try:
        res = sv.resultado_atual(con, codigo)
    finally:
        con.close()
    registra("13 paciente polimedicado produz vários achados ordenados",
             res.resumo["achados"] > 3 and "Resultados da conciliação" in pagina,
             "%d achados, %d medicamentos" % (res.resumo["achados"],
                                              res.resumo["medicamentos"]))


# =====================================================================
# 3 — VALIDACAO DE ENTRADA E ERROS
# =====================================================================
def t14_erros_de_entrada(c):
    codigo = criar(c, "Erros de entrada")
    g, _ = add_med(c, codigo, "dipirona", "Dipirona")

    casos = [
        ("horário impossível", "/a/%s/posologia/%s" % (codigo, g),
         [("horario", "99:99")], "Horário inválido"),
        ("frequência fora da faixa", "/a/%s/posologia/%s" % (codigo, g),
         [("vezes_por_dia", "40")], "entre 1 e 12"),
        ("dose não numérica", "/a/%s/posologia/%s" % (codigo, g),
         [("dose_valor", "meio comprimido")], "precisa ser um número"),
        ("término antes do início", "/a/%s/posologia/%s" % (codigo, g),
         [("data_inicio", "2026-05-01"), ("data_fim_prevista", "2026-04-01")],
         "anterior"),
        ("contínuo com data de término", "/a/%s/posologia/%s" % (codigo, g),
         [("uso_continuo", "on"), ("data_fim_prevista", "2026-12-01")],
         "não combina"),
        ("rotina com hora impossível", "/a/%s/rotina" % codigo,
         [("ACORDAR", "25:00")], "Horário inválido"),
    ]
    falhas = []
    for nome, rota, dados, esperado in casos:
        r = c.post(rota, data=MultiDict(dados), follow_redirects=True)
        if esperado.lower() not in texto(r).lower():
            falhas.append(nome)
    registra("14.1 entradas inválidas são recusadas com mensagem legível",
             not falhas, "6 casos, %d sem mensagem: %s"
             % (len(falhas), ", ".join(falhas)))

    r = c.post("/novo", data={"nome": "   "}, follow_redirects=True)
    registra("14.2 atendimento sem nome de paciente é recusado",
             "Informe o nome do paciente" in texto(r))

    r = c.post("/a/%s/medicamento" % codigo,
               data={"nome_relatado": "Dipirona", "escolha": "",
                     "lista": "RELATADA", "origem": "PRESCRITO"},
               follow_redirects=True)
    registra("14.3 duplicação acidental do mesmo item é impedida",
             "já está na lista" in texto(r))

    r = c.get("/a/NAO-EXISTE/paciente", follow_redirects=True)
    registra("14.4 atendimento inexistente não quebra a aplicação",
             r.status_code == 200 and "não encontrado" in texto(r).lower())

    r = c.get("/a/%s/achado?chave=NAO_EXISTE" % codigo)
    registra("14.5 achado inexistente devolve página de erro, não stack trace",
             r.status_code == 404 and "Traceback" not in texto(r))

    r = c.get("/rota/que/nao/existe")
    registra("14.6 rota inexistente devolve 404 tratado",
             r.status_code == 404 and "não existe" in texto(r))


def t15_edicao_e_remocao(c):
    codigo = criar(c, "Edição e remoção")
    g, _ = add_med(c, codigo, "dipirona", "Dipirona 500 mg")
    add_posologia(c, codigo, g, dose_valor="500", dose_unidade="mg",
                  vezes_por_dia="3", horarios=["08:00", "14:00", "20:00"])
    add_posologia(c, codigo, g, dose_valor="1000", dose_unidade="mg",
                  vezes_por_dia="2", horarios=["08:00", "20:00"])
    con = sv.conectar()
    try:
        grupos = sv.listar_medicamentos(con, codigo)
        n_pos = con.execute(
            "SELECT COUNT(*) FROM posologia p JOIN atendimento_medicamento am "
            "ON am.id=p.atendimento_medicamento_id JOIN atendimento a "
            "ON a.id=am.atendimento_id WHERE a.codigo=?", (codigo,)).fetchone()[0]
    finally:
        con.close()
    registra("15.1 editar posologia substitui, não duplica",
             len(grupos) == 1 and grupos[0].posologia["dose_valor"] == 1000
             and len(grupos[0].horarios) == 2 and n_pos == len(grupos[0].ids),
             "dose %s, %d horários, %d posologia(s)"
             % (grupos[0].posologia["dose_valor"], len(grupos[0].horarios), n_pos))

    c.post("/a/%s/medicamento/%s/lista" % (codigo, g),
           data={"lista": "PRESCRITA"})
    con = sv.conectar()
    try:
        g2 = sv.listar_medicamentos(con, codigo)[0]
    finally:
        con.close()
    registra("15.2 mover de lista preserva a posologia",
             g2.lista == "PRESCRITA" and g2.posologia["dose_valor"] == 1000)

    c.post("/a/%s/medicamento/%s/remover" % (codigo, g2.grupo_id))
    con = sv.conectar()
    try:
        restantes = sv.listar_medicamentos(con, codigo)
        orfas = con.execute(
            "SELECT COUNT(*) FROM posologia p WHERE NOT EXISTS "
            "(SELECT 1 FROM atendimento_medicamento am "
            " WHERE am.id = p.atendimento_medicamento_id)").fetchone()[0]
    finally:
        con.close()
    registra("15.3 remover apaga o item e não deixa posologia órfã",
             not restantes and orfas == 0, "%d órfã(s)" % orfas)


def t16_persistencia_navegando(c):
    """Trocar de secao nao pode perder dado."""
    codigo = criar(c, "Persistência")
    c.post("/a/%s/paciente" % codigo,
           data={"nome": "Persistência", "data_nascimento": "1970-01-01",
                 "sexo": "M", "peso_kg": "80", "farmaceutico": "Farm. Teste"})
    g, _ = add_med(c, codigo, "dipirona", "Dipirona 500 mg")
    add_posologia(c, codigo, g, dose_valor="500", dose_unidade="mg",
                  vezes_por_dia="2", horarios=["08:00", "20:00"])
    c.post("/a/%s/rotina" % codigo, data={"ACORDAR": "06:00",
                                          "ALMOCO": "12:30"})
    con = sv.conectar()
    try:
        cond = busca.buscar_condicao(con, "diabetes")
    finally:
        con.close()
    c.post("/a/%s/condicao" % codigo, data={"doenca_id": cond[0].id})

    for rota in ("paciente", "anamnese", "medicamentos", "rotina", "itens",
                 "conciliacao", "resultados", "relatorio"):
        c.get("/a/%s/%s" % (codigo, rota))

    p = texto(c.get("/a/%s/paciente" % codigo))
    m = texto(c.get("/a/%s/medicamentos" % codigo))
    ro = texto(c.get("/a/%s/rotina" % codigo))
    an = texto(c.get("/a/%s/anamnese" % codigo))
    registra("16 nada se perde ao navegar entre as etapas",
             "1970-01-01" in p and "80" in p and "500 mg" in m
             and "06:00" in ro and "12:30" in ro and cond[0].nome in an)


def t17_analise_usa_o_atendimento_certo(_c):
    """Resultado de um paciente nao pode aparecer no atendimento de outro.

    Usa um cliente NOVO de proposito. O cliente compartilhado acumula
    mensagens de flash da sessao, e uma mensagem pendente de outro teste
    apareceria na pagina seguinte — o que e comportamento normal do Flask, e
    nao vazamento de dados. Foi assim que a primeira versao deste teste
    reprovou a aplicacao por um artefato do proprio teste.
    """
    c = cliente()
    a = criar(c, "Paciente A")
    b = criar(c, "Paciente B")
    ga, _ = add_med(c, a, "varfarina", "Varfarina 5 mg")
    add_posologia(c, a, ga, dose_valor="5", dose_unidade="mg",
                  vezes_por_dia="1", horarios=["20:00"])
    gb, _ = add_med(c, b, "metformina", "Metformina 850 mg")
    add_posologia(c, b, gb, dose_valor="850", dose_unidade="mg",
                  vezes_por_dia="2", horarios=["08:00", "20:00"])
    c.post("/a/%s/analisar" % a)
    c.post("/a/%s/analisar" % b)
    c.get("/a/%s/resultados" % a)          # consome mensagens pendentes
    pa = texto(c.get("/a/%s/medicamentos" % a))
    c.get("/a/%s/resultados" % b)
    pb = texto(c.get("/a/%s/medicamentos" % b))
    con = sv.conectar()
    try:
        ra, rb = sv.resultado_atual(con, a), sv.resultado_atual(con, b)
    finally:
        con.close()
    itens_a = " ".join(x.item_a + " " + (x.item_b or "") for x in ra.achados)
    itens_b = " ".join(x.item_a + " " + (x.item_b or "") for x in rb.achados)
    registra("17 resultados não vazam entre atendimentos",
             "Varfarina" in pa and "Metformina" not in pa
             and "Metformina" in pb and "Varfarina" not in pb
             and "Metformina" not in itens_a and "Varfarina" not in itens_b,
             "A: %d achados · B: %d achados" % (len(ra.achados), len(rb.achados)))


def t18_relatorio_sem_analise(c):
    """Relatorio antes de analisar nao pode quebrar."""
    codigo = criar(c, "Relatório sem análise")
    g, _ = add_med(c, codigo, "dipirona", "Dipirona")
    r = c.get("/a/%s/relatorio" % codigo)
    registra("18 relatório funciona mesmo sem análise gravada",
             r.status_code == 200 and "Conciliação medicamentosa" in texto(r))


def t19_analise_sem_medicamento(c):
    codigo = criar(c, "Sem medicamento")
    r = c.post("/a/%s/analisar" % codigo, follow_redirects=True)
    registra("19 analisar sem medicamento é recusado com explicação",
             "Não há nenhum medicamento" in texto(r))


def t20_concluir_reabrir(c):
    codigo = criar(c, "Conclusão")
    g, _ = add_med(c, codigo, "dipirona", "Dipirona")
    add_posologia(c, codigo, g, dose_valor="500", dose_unidade="mg",
                  vezes_por_dia="1", horarios=["08:00"])
    c.post("/a/%s/concluir" % codigo)
    pagina = texto(c.get("/a/%s/relatorio" % codigo))
    c.post("/a/%s/reabrir" % codigo)
    pagina2 = texto(c.get("/a/%s/paciente" % codigo))
    registra("20 concluir e reabrir o atendimento",
             "concluído" in pagina and "concluído" not in pagina2)


def t21_busca(c):
    codigo = criar(c, "Busca")
    p1 = texto(c.get("/a/%s/medicamentos?q=dipirona" % codigo))
    p2 = texto(c.get("/a/%s/medicamentos?q=zzzzzznaoexiste" % codigo))
    con = sv.conectar()
    try:
        ean = con.execute("SELECT ean FROM apresentacao_ean WHERE ean <> "
                          "'0000000000000' LIMIT 1").fetchone()[0]
    finally:
        con.close()
    p3 = texto(c.get("/a/%s/medicamentos?q=%s" % (codigo, ean)))
    r = c.get("/api/busca/medicamento?q=dipi")
    registra("21.1 busca por nome traz resultado com confiança declarada",
             "dipirona" in p1.lower() and "confiança" in p1.lower())
    registra("21.2 busca sem resultado oferece registrar assim mesmo",
             "Nada encontrado" in p2 and "Registrar assim mesmo" in p2)
    registra("21.3 código de barras é reconhecido como determinístico",
             "código de barras" in p3, ean)
    registra("21.4 autocompletar responde JSON",
             r.status_code == 200 and isinstance(r.json, list) and r.json)


def main() -> int:
    print("=" * 78)
    print("VERIFICACAO 1 — FUNCIONAL — APLICACAO DO FARMACEUTICO")
    print("=" * 78)
    c = cliente()
    testes = [t01_fluxo_completo, t02_interacao, t03_alergia, t04_condicao,
              t05_duplicidade, t06_divergencia, t07_conflito_horario, t08_item,
              t09_sem_achado, t10_sem_regra, t11_nao_reconhecido,
              t12_incompleto, t13_polimedicado, t14_erros_de_entrada,
              t15_edicao_e_remocao, t16_persistencia_navegando,
              t17_analise_usa_o_atendimento_certo, t18_relatorio_sem_analise,
              t19_analise_sem_medicamento, t20_concluir_reabrir, t21_busca]
    try:
        for fn in testes:
            print("\n%s" % (fn.__doc__ or fn.__name__).split("\n")[0].strip())
            try:
                fn(c)
            except Exception as exc:            # noqa: BLE001
                registra(fn.__name__, False, "EXCEÇÃO: %r" % exc)
    finally:
        limpar()

    falhas = [r for r in RESULTADOS if not r[1]]
    print("\n" + "=" * 78)
    print("%d verificação(ões) · %d ok · %d falha(s) · %d atendimento(s) "
          "criados e apagados"
          % (len(RESULTADOS), len(RESULTADOS) - len(falhas), len(falhas),
             len(CRIADOS)))
    for nome, _ok, det in falhas:
        print("  FALHA: %s — %s" % (nome, det))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
