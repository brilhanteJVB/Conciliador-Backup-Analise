# -*- coding: utf-8 -*-
"""
VERIFICACAO 2 — INDEPENDENTE — a aplicacao (Fase 6).

NAO repete a V1. A V1 pergunta "a tela funciona?"; esta pergunta outra coisa:

    **a tela esta mesmo consumindo os servicos, ou produzindo resultado proprio?**

Cinco eixos, nenhum deles refazendo o caminho da V1:

  1. CONFRONTO       o que a pagina mostra e comparado, item a item, com o que
                     `conciliar_atendimento` devolve quando chamado direto.
  2. INSPECAO DO     depois de cada acao da INTERFACE, o banco e lido por SQL
     BANCO           proprio e as colunas gravadas sao conferidas uma a uma.
  3. ARQUITETURA     leitura do CODIGO-FONTE: a camada de interface nao pode
                     conter SQL sobre conhecimento farmacologico, e nenhum
                     template pode calcular prioridade.
  4. PERSISTENCIA    analisar duas vezes, conferir que nada duplica, que a
                     anotacao humana sobrevive e que o CHECK do esquema segura
                     o que tem de segurar.
  5. INTEGRIDADE     nada de orfao, nada de vazamento entre atendimentos,
                     evidencia nunca separada do achado.

Uso: python tests/verificacao_aplicacao.py
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in ("app", "rules", "pipeline", "tests"):
    sys.path.insert(0, str(RAIZ / _p))

from werkzeug.datastructures import MultiDict   # noqa: E402

import busca                        # noqa: E402
import servicos as sv               # noqa: E402
import web                          # noqa: E402
from motor_conciliacao import conciliar_atendimento   # noqa: E402

FALHAS, PASSOS, CRIADOS = [], [], []


def checa(nome, ok, detalhe=""):
    PASSOS.append((nome, ok, detalhe))
    if not ok:
        FALHAS.append((nome, detalhe))
    print("   %s %-52s %s" % ("OK  " if ok else "ERRO", nome[:52],
                              str(detalhe)[:70]))


def cliente():
    web.app.config["TESTING"] = True
    return web.app.test_client()


def limpar():
    """Apaga TUDO o que este teste criou, inclusive o paciente.

    A versao anterior procurava o paciente a partir do atendimento — e o
    eixo 5 apaga um atendimento de proposito, para conferir o cascata. O
    paciente daquele atendimento ficava para sempre no banco de PRODUCAO: a
    Fase 9 encontrou cinco linhas "Integridade B" acumuladas de execucoes
    anteriores. Por isso o id do paciente e guardado na criacao, e nao
    procurado no fim.
    """
    con = sv.conectar()
    try:
        for codigo, paciente_id in CRIADOS:
            linha = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                                (codigo,)).fetchone()
            if linha:
                con.execute("DELETE FROM atendimento WHERE id=?", (linha[0],))
            if paciente_id:
                con.execute("DELETE FROM paciente WHERE id=?", (paciente_id,))
        con.commit()
    finally:
        con.close()


def montar_atendimento(c, nome="Verificação independente") -> str:
    """Monta um atendimento rico USANDO SO A INTERFACE."""
    r = c.post("/novo", data={"nome": nome, "farmaceutico": "Farm. V2",
                              "crf": "CRF-V2 999"})
    codigo = r.headers["Location"].split("/a/")[1].split("/")[0]
    con = sv.conectar()
    try:
        pid = con.execute("SELECT paciente_id FROM atendimento WHERE codigo=?",
                          (codigo,)).fetchone()
    finally:
        con.close()
    CRIADOS.append((codigo, pid[0] if pid else None))
    c.post("/a/%s/paciente" % codigo,
           data={"nome": nome, "data_nascimento": "1950-06-15", "sexo": "F",
                 "peso_kg": "64", "altura_cm": "157",
                 "farmaceutico": "Farm. V2", "crf": "CRF-V2 999"})

    con = sv.conectar()
    try:
        cond = busca.buscar_condicao(con, "renal")[0]
        alergia = busca.buscar_substancia(con, "dipirona")[0]
        item = con.execute(
            "SELECT ii.item_id FROM interacao_item ii JOIN substancia s "
            "ON s.id=ii.substancia_id ORDER BY s.n_produtos_ativos DESC "
            "LIMIT 1").fetchone()[0]
        escolhas = {}
        for termo in ("varfarina", "ibuprofeno", "losartana", "metformina"):
            achados = busca.buscar_medicamento(con, termo)
            escolhas[termo] = achados[0].chave if achados else ""
    finally:
        con.close()

    c.post("/a/%s/condicao" % codigo, data={"doenca_id": cond.id})
    c.post("/a/%s/alergia" % codigo,
           data={"substancia_id": alergia.substancia_id,
                 "reacao": "urticária", "gravidade": "GRAVE"})
    c.post("/a/%s/habitos" % codigo,
           data={"situacao_ALCOOL": "ATUAL", "frequencia_ALCOOL": "diário"})
    c.post("/a/%s/item" % codigo,
           data={"item_id": item, "frequencia": "DIARIO",
                 "horario_habitual": "08:15"})
    c.post("/a/%s/rotina" % codigo,
           data={"ACORDAR": "06:30", "CAFE_MANHA": "07:00", "ALMOCO": "12:00",
                 "JANTAR": "19:30", "DORMIR": "22:30"})

    plano = [("varfarina", "Varfarina 5 mg", "PRESCRITA", "5", "mg", 1,
              ["20:00"]),
             ("varfarina", "Varfarina 5 mg", "RELATADA", "5", "mg", 1,
              ["20:00"]),
             ("losartana", "Losartana 50 mg", "PRESCRITA", "50", "mg", 1,
              ["08:00"]),
             ("losartana", "Losartana 50 mg", "RELATADA", "100", "mg", 1,
              ["08:00"]),
             ("ibuprofeno", "Ibuprofeno 600 mg", "RELATADA", "600", "mg", 3,
              ["08:00", "14:00", "22:00"]),
             ("metformina", "Metformina 850 mg", "RELATADA", "850", "mg", 2,
              ["08:00", "20:00"])]
    for termo, rotulo, lista, dose, unidade, vezes, horas in plano:
        r = c.post("/a/%s/medicamento" % codigo,
                   data={"nome_relatado": rotulo, "escolha": escolhas[termo],
                         "lista": lista, "origem": "PRESCRITO"})
        grupo = r.headers["Location"].rstrip("/").split("/")[-1]
        c.post("/a/%s/posologia/%s" % (codigo, grupo),
               data=MultiDict([("dose_valor", dose), ("dose_unidade", unidade),
                               ("vezes_por_dia", str(vezes)),
                               ("via_administracao", "oral")]
                              + [("horario", h) for h in horas]))
    return codigo


# =====================================================================
# EIXO 1 — CONFRONTO: TELA x MOTOR
# =====================================================================
def eixo_1_confronto():
    print("\n1. CONFRONTO — a tela mostra exatamente o que o motor devolve\n")
    c = cliente()
    codigo = montar_atendimento(c, "Confronto tela x motor")

    con = sv.conectar()
    try:
        atendimento_id = sv.exigir_atendimento(con, codigo)["id"]
        # Chamada DIRETA ao motor, sem passar por servico nem por rota.
        direto = conciliar_atendimento(con, atendimento_id, persistir=False)
    finally:
        con.close()

    pagina = c.get("/a/%s/resultados" % codigo).data.decode("utf-8")
    texto = html.unescape(re.sub(r"<[^>]+>", " ", pagina))
    texto = re.sub(r"\s+", " ", texto)

    faltando = [a.titulo for a in direto.achados
                if re.sub(r"\s+", " ", a.titulo) not in texto]
    checa("1.1 todo achado do motor aparece na tela", not faltando,
          "%d achados, %d ausentes na página%s"
          % (len(direto.achados), len(faltando),
             ": " + faltando[0][:40] if faltando else ""))

    # Os numeros do painel tem de ser os do motor, nao uma recontagem.
    numeros = re.findall(r'class="valor">(\d+)</div>\s*<div class="rotulo">'
                         r'([^<]+)</div>', pagina)
    esperado = {"Crítico": direto.resumo["criticos"],
                "Alto": direto.resumo["altos"],
                "Moderado": direto.resumo["moderados"],
                "Baixo": direto.resumo["baixos"],
                "Informativo": direto.resumo["informativos"],
                "Divergências": direto.resumo["divergencias"],
                "Não avaliado": direto.resumo["nao_avaliado"]}
    divergentes = [(rotulo, valor, esperado[rotulo])
                   for valor, rotulo in numeros
                   if rotulo.strip() in esperado
                   and int(valor) != esperado[rotulo.strip()]]
    checa("1.2 os números do painel são os do motor", not divergentes,
          "%d painel(éis) conferido(s)%s" % (len(numeros), divergentes[:1]))

    # A prioridade exibida tem de ser a calculada pelo motor, achado a achado.
    erros = []
    for a in direto.achados:
        pagina_achado = c.get("/a/%s/achado?chave=%s"
                              % (codigo, a.grupo_chave)).data.decode("utf-8")
        limpo = re.sub(r"\s+", " ", html.unescape(
            re.sub(r"<[^>]+>", " ", pagina_achado)))
        from rotulos import (CONFIANCA, GRAVIDADE, PRIORIDADE,
                             STATUS_INFORMACAO, rotular)
        for rotulo, valor in (("prioridade", PRIORIDADE[a.prioridade]),
                              ("gravidade", rotular(GRAVIDADE,
                                                    a.gravidade_fonte)),
                              ("confiança", rotular(CONFIANCA,
                                                    a.confianca_sistema)),
                              ("status", rotular(STATUS_INFORMACAO,
                                                 a.status_informacao))):
            if valor not in limpo:
                erros.append("%s: %s ausente (%s)" % (a.grupo_chave, rotulo,
                                                      valor))
    checa("1.3 gravidade, confiança, prioridade e status batem em cada achado",
          not erros, "%d achados conferidos, %d divergência(s)%s"
          % (len(direto.achados), len(erros), ": " + erros[0] if erros else ""))

    # As divergencias da tela sao as do motor.
    pagina_conc = c.get("/a/%s/conciliacao" % codigo).data.decode("utf-8")
    limpo = re.sub(r"\s+", " ", html.unescape(
        re.sub(r"<[^>]+>", " ", pagina_conc)))
    ausentes = [p.nome_exibicao for p in direto.divergencias
                if p.nome_exibicao not in limpo]
    checa("1.4 toda divergência do motor aparece na conciliação",
          not ausentes, "%d divergência(s), %d ausente(s)"
          % (len(direto.divergencias), len(ausentes)))

    # O relatorio em texto tambem sai do mesmo resultado.
    txt = c.get("/a/%s/relatorio.txt" % codigo).data.decode("utf-8")
    checa("1.5 relatório em texto usa o mesmo resumo",
          ("Achados ......................... %d" % direto.resumo["achados"])
          in txt, "%d achados" % direto.resumo["achados"])

    # E o que NAO foi avaliado nao pode sumir da tela.
    motivos = {n.motivo for n in direto.nao_avaliado}
    from rotulos import MOTIVO_NAO_AVALIADO, rotular as rot2
    pagina_res = html.unescape(re.sub(r"<[^>]+>", " ",
                                      c.get("/a/%s/resultados" % codigo)
                                      .data.decode("utf-8")))
    pagina_res = re.sub(r"\s+", " ", pagina_res)
    sumidos = [m for m in motivos
               if rot2(MOTIVO_NAO_AVALIADO, m) not in pagina_res]
    checa("1.6 nada do 'não avaliado' desaparece na exibição", not sumidos,
          "%d motivo(s), %d sumido(s)" % (len(motivos), len(sumidos)))


# =====================================================================
# EIXO 2 — INSPECAO DIRETA DO BANCO
# =====================================================================
def eixo_2_banco():
    print("\n2. INSPEÇÃO DO BANCO — SQL próprio, coluna a coluna\n")
    c = cliente()
    codigo = montar_atendimento(c, "Inspeção do banco")
    con = sv.conectar()
    try:
        aid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                          (codigo,)).fetchone()[0]

        pac = con.execute(
            "SELECT p.nome, p.data_nascimento, p.sexo, p.peso_kg, p.altura_cm "
            "FROM paciente p JOIN atendimento a ON a.paciente_id=p.id "
            "WHERE a.id=?", (aid,)).fetchone()
        checa("2.1 o formulário do paciente gravou exatamente o que enviou",
              pac == ("Inspeção do banco", "1950-06-15", "F", 64.0, 157.0),
              str(pac))

        meds = con.execute(
            "SELECT lista, COUNT(*) FROM atendimento_medicamento "
            "WHERE atendimento_id=? GROUP BY lista ORDER BY lista",
            (aid,)).fetchall()
        checa("2.2 as listas foram gravadas como a tela pediu",
              dict(meds).get("PRESCRITA") == 2
              and dict(meds).get("RELATADA") >= 3, str(meds))

        # Posologia: o valor em branco tem de ficar NULL, nunca virar zero.
        nulos = con.execute(
            "SELECT COUNT(*) FROM posologia p JOIN atendimento_medicamento am "
            "ON am.id=p.atendimento_medicamento_id WHERE am.atendimento_id=? "
            "AND (p.duracao_dias = 0 OR p.intervalo_horas = 0)",
            (aid,)).fetchone()[0]
        checa("2.3 campo não informado ficou NULL, não virou zero", nulos == 0,
              "%d campo(s) com zero indevido" % nulos)

        horas = con.execute(
            "SELECT COUNT(*) FROM horario_administracao h JOIN posologia p "
            "ON p.id=h.posologia_id JOIN atendimento_medicamento am "
            "ON am.id=p.atendimento_medicamento_id WHERE am.atendimento_id=? "
            "AND h.definido_por <> 'FARMACEUTICO'", (aid,)).fetchone()[0]
        checa("2.4 horário digitado é marcado como definido pelo farmacêutico",
              horas == 0, "%d horário(s) com origem errada" % horas)

        cond = con.execute(
            "SELECT COUNT(*) FROM paciente_condicao pc JOIN atendimento a "
            "ON a.paciente_id=pc.paciente_id WHERE a.id=? AND pc.doenca_id "
            "IS NOT NULL", (aid,)).fetchone()[0]
        alerg = con.execute(
            "SELECT gravidade, reacao FROM paciente_alergia pa "
            "JOIN atendimento a ON a.paciente_id=pa.paciente_id "
            "WHERE a.id=?", (aid,)).fetchone()
        checa("2.5 condição e alergia gravadas com vínculo e gravidade",
              cond == 1 and alerg == ("GRAVE", "urticária"),
              "%d condição · alergia %s" % (cond, alerg))

        item = con.execute(
            "SELECT item_id, frequencia, horario_habitual FROM atendimento_item "
            "WHERE atendimento_id=?", (aid,)).fetchone()
        checa("2.6 item registrado com frequência e horário",
              item and item[1] == "DIARIO" and item[2] == "08:15", str(item))

        rotina = dict(con.execute(
            "SELECT evento, hora FROM rotina_paciente WHERE atendimento_id=?",
            (aid,)))
        checa("2.7 rotina gravada evento a evento",
              rotina.get("ACORDAR") == "06:30"
              and rotina.get("JANTAR") == "19:30" and len(rotina) == 5,
              "%d evento(s)" % len(rotina))
    finally:
        con.close()

    # Depois de ANALISAR pela interface: o que foi gravado.
    c.post("/a/%s/analisar" % codigo)
    con = sv.conectar()
    try:
        aid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                          (codigo,)).fetchone()[0]
        cid = con.execute("SELECT id FROM conciliacao WHERE atendimento_id=? "
                          "ORDER BY id DESC LIMIT 1", (aid,)).fetchone()[0]

        # A INTERFACE nunca escreve gravidade nem prioridade por conta propria:
        # toda linha de achado tem de ter vindo do motor, com justificativa.
        sem_justificativa = con.execute(
            "SELECT COUNT(*) FROM achado WHERE conciliacao_id=? AND "
            "(justificativa_prioridade IS NULL OR justificativa_prioridade='' "
            " OR metodo_deteccao IS NULL)", (cid,)).fetchone()[0]
        checa("2.8 nenhum achado gravado sem justificativa do motor",
              sem_justificativa == 0, "(%d)" % sem_justificativa)

        orfas = con.execute(
            "SELECT COUNT(*) FROM achado a WHERE a.conciliacao_id=? AND "
            "a.gravidade_fonte NOT IN ('NAO_DETERMINADA') AND "
            "a.gravidade_fonte IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM achado_evidencia e WHERE e.achado_id=a.id "
            " AND e.gravidade_declarada = a.gravidade_fonte)",
            (cid,)).fetchone()[0]
        checa("2.9 nenhuma gravidade exibida sem evidência que a declare",
              orfas == 0, "(%d)" % orfas)

        intenc = con.execute(
            "SELECT COUNT(*) FROM conciliacao_par WHERE conciliacao_id=? AND "
            "intencionalidade <> 'NAO_DETERMINADA'", (cid,)).fetchone()[0]
        checa("2.10 a aplicação não decidiu intencionalidade nenhuma",
              intenc == 0, "(%d)" % intenc)

        previsto = con.execute(
            "SELECT COUNT(*) FROM achado WHERE conciliacao_id=? AND "
            "(origem_achado <> 'REGRA' OR probabilidade_modelo IS NOT NULL)",
            (cid,)).fetchone()[0]
        checa("2.11 nenhum achado se apresenta como previsão de modelo",
              previsto == 0, "(%d) — não há ML no projeto" % previsto)
    finally:
        con.close()


# =====================================================================
# EIXO 3 — ARQUITETURA, LIDA NO CODIGO-FONTE
# =====================================================================
TABELAS_CLINICAS = [
    "interacao_substancia", "interacao_doenca", "interacao_item",
    "interacao_habito", "papel_farmacocinetico", "regra_administracao",
    "regra_separacao", "vw_interacao_liberada", "vw_regra_administracao_liberada",
    "vw_regra_separacao_liberada", "vw_interacao_doenca_liberada",
]


def eixo_3_arquitetura():
    print("\n3. ARQUITETURA — lida no código-fonte, não na execução\n")
    web_src = (RAIZ / "app" / "web.py").read_text(encoding="utf-8")

    encontradas = [t for t in TABELAS_CLINICAS if t in web_src]
    checa("3.1 a interface não consulta tabela de conhecimento clínico",
          not encontradas, "encontradas: %s" % ", ".join(encontradas)
          if encontradas else "nenhuma das %d" % len(TABELAS_CLINICAS))

    # Sintaxe de SQL de verdade, e nao a palavra solta. A primeira versao
    # deste teste procurava \bINSERT\b e casava com `sys.path.insert`:
    # reprovou a aplicacao por um erro do proprio teste.
    sql = re.findall(r"SELECT\s+[\w*(]+.*?\sFROM\s|INSERT\s+INTO\s|"
                     r"UPDATE\s+\w+\s+SET\s|DELETE\s+FROM\s",
                     web_src, re.IGNORECASE)
    checa("3.2 a interface não tem SQL nenhum", not sql,
          "%d comando(s) SQL em web.py%s" % (len(sql),
                                             ": " + sql[0][:40] if sql else ""))

    # Nenhum template pode decidir prioridade, gravidade ou confianca.
    calculos = []
    for tpl in (RAIZ / "app" / "templates").glob("*.html"):
        fonte = tpl.read_text(encoding="utf-8")
        for padrao in (r"if\s+\w*gravidade\w*\s*==\s*'MAIOR'",
                       r"prioridade\s*=\s*'", r"CRITICO'\s*if",
                       r"gravidade_fonte\s*=\s*"):
            if re.search(padrao, fonte):
                calculos.append("%s: %s" % (tpl.name, padrao))
    checa("3.3 nenhum template calcula prioridade ou gravidade",
          not calculos, "; ".join(calculos) if calculos
          else "%d templates lidos" % len(list(
              (RAIZ / "app" / "templates").glob("*.html"))))

    # A camada de servico nao pode reimplementar regra: ela CHAMA o motor.
    serv_src = (RAIZ / "app" / "servicos.py").read_text(encoding="utf-8")
    checa("3.4 os serviços chamam o motor em vez de reimplementá-lo",
          "conciliar_atendimento(" in serv_src
          and "montar_agenda(" in serv_src
          and not any(t in serv_src for t in TABELAS_CLINICAS),
          "importa e chama os dois motores; zero tabela clínica")

    # E a busca nao pode decidir nada clinico.
    busca_src = (RAIZ / "app" / "busca.py").read_text(encoding="utf-8")
    checa("3.5 a busca não lê tabela de interação nem de regra",
          not any(t in busca_src for t in TABELAS_CLINICAS),
          "consulta só substância, produto, apresentação, doença e item")

    # Os rotulos traduzem, nunca transformam.
    rot_src = (RAIZ / "app" / "rotulos.py").read_text(encoding="utf-8")
    perigoso = re.findall(r'"EXTRAIDO_AUTOMATICAMENTE":\s*"([^"]*)"', rot_src)
    checa("3.6 'extraído automaticamente' nunca é rotulado como confirmado",
          all("onfirmad" not in v for v in perigoso),
          perigoso[0][:52] if perigoso else "—")


# =====================================================================
# EIXO 4 — PERSISTENCIA E REANALISE
# =====================================================================
def eixo_4_persistencia():
    print("\n4. PERSISTÊNCIA — analisar duas vezes, e o que sobrevive\n")
    c = cliente()
    codigo = montar_atendimento(c, "Persistência e reanálise")

    c.post("/a/%s/analisar" % codigo)
    con = sv.conectar()
    try:
        aid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                          (codigo,)).fetchone()[0]
        cid1 = con.execute("SELECT id FROM conciliacao WHERE atendimento_id=? "
                           "ORDER BY id DESC LIMIT 1", (aid,)).fetchone()[0]
        n1 = con.execute("SELECT COUNT(*) FROM achado WHERE conciliacao_id=?",
                         (cid1,)).fetchone()[0]
        res = sv.resultado_atual(con, codigo)
        alvo = res.achados[0]
        divergencia = res.divergencias[0] if res.divergencias else None
    finally:
        con.close()

    # Anotacoes humanas, feitas pela INTERFACE.
    c.post("/a/%s/achado/revisar" % codigo,
           data={"chave": alvo.grupo_chave, "situacao": "REVISADO",
                 "profissional": "Farm. V2", "crf": "CRF-V2 999",
                 "observacao": "orientação repassada"})
    if divergencia:
        c.post("/a/%s/divergencia/registrar" % codigo,
               data={"chave": sv.chave_divergencia(divergencia),
                     "intencionalidade": "INTENCIONAL",
                     "profissional": "Farm. V2", "crf": "CRF-V2 999",
                     "observacao": "ajuste conhecido"})

    # Segunda analise: o resultado e recalculado e os ids mudam.
    c.post("/a/%s/analisar" % codigo)
    con = sv.conectar()
    try:
        cid2 = con.execute("SELECT id FROM conciliacao WHERE atendimento_id=? "
                           "ORDER BY id DESC LIMIT 1", (aid,)).fetchone()[0]
        n2 = con.execute("SELECT COUNT(*) FROM achado WHERE conciliacao_id=?",
                         (cid2,)).fetchone()[0]
        anotacoes = con.execute(
            "SELECT COUNT(*) FROM anotacao_profissional WHERE atendimento_id=?",
            (aid,)).fetchone()[0]
        checa("4.1 reanálise cria uma conciliação nova, não sobrescreve",
              cid2 != cid1 and n2 == n1, "conciliação %d -> %d, %d achados"
              % (cid1, cid2, n2))

        checa("4.2 a anotação do profissional sobrevive à reanálise",
              anotacoes == (2 if divergencia else 1),
              "%d anotação(ões) preservada(s)" % anotacoes)

        if divergencia:
            gravado = con.execute(
                "SELECT intencionalidade, avaliado_por FROM conciliacao_par "
                "WHERE conciliacao_id=? AND intencionalidade "
                "<> 'NAO_DETERMINADA'", (cid2,)).fetchone()
            checa("4.3 a intencionalidade foi reaplicada COM assinatura",
                  gravado == ("INTENCIONAL", "Farm. V2"), str(gravado))

        # A chave da anotacao e estavel: nao pode ser id de linha.
        chaves = [k for (k,) in con.execute(
            "SELECT chave FROM anotacao_profissional WHERE atendimento_id=?",
            (aid,))]
        checa("4.4 a chave da anotação é estável, não um id de linha",
              all(not k.isdigit() for k in chaves), chaves[:2])

        # O CHECK do esquema tem de recusar intencionalidade sem assinatura.
        try:
            con.execute(
                "INSERT INTO conciliacao_par (conciliacao_id, item_relatado_id,"
                " nome_exibicao, situacao, tipo_divergencia, intencionalidade) "
                "SELECT ?, id, 'x', 'DIVERGENCIA', 'SO_NO_RELATO', "
                "'NAO_INTENCIONAL' FROM atendimento_medicamento "
                "WHERE atendimento_id=? LIMIT 1", (cid2, aid))
            recusou = False
            con.rollback()
        except Exception:                       # noqa: BLE001
            recusou = True
            con.rollback()
        checa("4.5 o banco recusa intencionalidade sem profissional", recusou)
    finally:
        con.close()

    # A tela volta a mostrar a revisao depois de reanalisar.
    pagina = c.get("/a/%s/achado?chave=%s"
                   % (codigo, alvo.grupo_chave)).data.decode("utf-8")
    checa("4.6 a tela reencontra a revisão pela chave estável",
          "orientação repassada" in pagina and "Farm. V2" in pagina)


# =====================================================================
# EIXO 5 — INTEGRIDADE
# =====================================================================
def eixo_5_integridade():
    print("\n5. INTEGRIDADE — nada de órfão, nada de vazamento\n")
    c = cliente()
    a = montar_atendimento(c, "Integridade A")
    b = montar_atendimento(c, "Integridade B")
    c.post("/a/%s/analisar" % a)
    c.post("/a/%s/analisar" % b)

    con = sv.conectar()
    try:
        aid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                          (a,)).fetchone()[0]
        bid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                          (b,)).fetchone()[0]

        cruzados = con.execute(
            "SELECT COUNT(*) FROM achado ac JOIN conciliacao co "
            "ON co.id=ac.conciliacao_id WHERE co.atendimento_id=? AND "
            "ac.substancia_a_id IS NOT NULL AND ac.substancia_a_id NOT IN "
            "(SELECT substancia_id FROM atendimento_medicamento "
            " WHERE atendimento_id=? AND substancia_id IS NOT NULL)",
            (aid, aid)).fetchone()[0]
        checa("5.1 nenhum achado cita substância que não é do atendimento",
              cruzados == 0, "(%d)" % cruzados)

        pares_cruzados = con.execute(
            "SELECT COUNT(*) FROM conciliacao_par cp JOIN conciliacao co "
            "ON co.id=cp.conciliacao_id WHERE co.atendimento_id=? AND "
            "cp.item_relatado_id IS NOT NULL AND cp.item_relatado_id NOT IN "
            "(SELECT id FROM atendimento_medicamento WHERE atendimento_id=?)",
            (bid, bid)).fetchone()[0]
        checa("5.2 nenhum par aponta para item de outro atendimento",
              pares_cruzados == 0, "(%d)" % pares_cruzados)

        sem_evidencia = con.execute(
            "SELECT COUNT(*) FROM achado ac JOIN conciliacao co "
            "ON co.id=ac.conciliacao_id WHERE co.atendimento_id IN (?,?) "
            "AND ac.origem_afirmacao IS NULL", (aid, bid)).fetchone()[0]
        checa("5.3 todo achado gravado guarda a origem da afirmação",
              sem_evidencia == 0, "(%d)" % sem_evidencia)

        ev_orfa = con.execute(
            "SELECT COUNT(*) FROM achado_evidencia e WHERE NOT EXISTS "
            "(SELECT 1 FROM achado x WHERE x.id = e.achado_id)").fetchone()[0]
        checa("5.4 nenhuma evidência solta, sem achado", ev_orfa == 0,
              "(%d)" % ev_orfa)
    finally:
        con.close()

    # Remover um medicamento pela INTERFACE nao pode deixar restos.
    con = sv.conectar()
    try:
        grupo = sv.listar_medicamentos(con, a)[0]
        ids = list(grupo.ids)
    finally:
        con.close()
    c.post("/a/%s/medicamento/%s/remover" % (a, grupo.grupo_id))
    con = sv.conectar()
    try:
        marca = ",".join("?" * len(ids))
        pos_restantes = con.execute(
            "SELECT COUNT(*) FROM posologia WHERE atendimento_medicamento_id "
            "IN (%s)" % marca, ids).fetchone()[0]
        horas_orfas = con.execute(
            "SELECT COUNT(*) FROM horario_administracao h WHERE NOT EXISTS "
            "(SELECT 1 FROM posologia p WHERE p.id = h.posologia_id)"
        ).fetchone()[0]
        restos = pos_restantes + horas_orfas
        # O item tem de sumir mesmo DEPOIS de uma analise gravada. Sem
        # ON DELETE CASCADE em conciliacao_par, o banco recusava a exclusao
        # e o farmaceutico ficava preso ao primeiro resultado.
        ainda = con.execute("SELECT COUNT(*) FROM atendimento_medicamento "
                            "WHERE id IN (%s)" % marca, ids).fetchone()[0]
        restos += ainda
        checa("5.5 remover pela tela não deixa posologia nem horário órfãos",
              restos == 0, "(%d resto(s))" % restos)
    finally:
        con.close()

    # Apagar o atendimento tem de levar tudo junto.
    con = sv.conectar()
    try:
        bid = con.execute("SELECT id FROM atendimento WHERE codigo=?",
                          (b,)).fetchone()[0]
        con.execute("DELETE FROM atendimento WHERE id=?", (bid,))
        con.commit()
        sobrou = sum(con.execute(
            "SELECT COUNT(*) FROM %s WHERE atendimento_id=?" % tabela,
            (bid,)).fetchone()[0]
            for tabela in ("atendimento_medicamento", "atendimento_item",
                           "rotina_paciente", "conciliacao",
                           "anotacao_profissional"))
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        checa("5.6 apagar o atendimento leva tudo e não quebra referência",
              sobrou == 0 and not fk,
              "%d resto(s), %d violação(ões) de chave" % (sobrou, len(fk)))
    finally:
        con.close()


def main() -> int:
    print("=" * 78)
    print("VERIFICACAO 2 — INDEPENDENTE — APLICACAO DO FARMACEUTICO")
    print("=" * 78)
    try:
        for eixo in (eixo_1_confronto, eixo_2_banco, eixo_3_arquitetura,
                     eixo_4_persistencia, eixo_5_integridade):
            try:
                eixo()
            except Exception as exc:            # noqa: BLE001
                checa(eixo.__name__, False, "EXCEÇÃO: %r" % exc)
    finally:
        limpar()
    print("\n" + "=" * 78)
    print("%d verificação(ões) · %d ok · %d falha(s)"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS)))
    for nome, det in FALHAS:
        print("  FALHA: %s — %s" % (nome, det))
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
