# -*- coding: utf-8 -*-
"""
TESTE DE PONTA A PONTA — um atendimento completo, do zero ao relatorio.

É o teste que demonstra que o projeto deixou de ser um conjunto de módulos e
passou a funcionar como sistema:

    Paciente → Anamnese → Medicamentos → Posologia → Rotina → Alimentos
             → Conciliação → Análise → Achados → Evidências → Relatório

Tudo pela INTERFACE, por requisições HTTP reais. Nenhum servico e chamado por
dentro para tomar atalho: se a tela nao consegue fazer, o teste falha.

FARMACOLOGIA REAL, PACIENTE SINTETICO. Os medicamentos, a interacao, a
contraindicacao e a interacao com item vem do banco; o que e inventado e a
pessoa — nome, rotina, horarios, o que ela relata.

O caso: idosa em uso de anticoagulante que se automedicou com
anti-inflamatorio. E o arquetipo de balcao mais citado na literatura de
conciliacao, e o banco tem a interacao documentada.

Ao final o teste GRAVA o relatorio em `docs/ATENDIMENTO_EXEMPLO.md`, para que
o resultado fique documentado e possa ser conferido sem rodar nada.

Uso: python tests/teste_ponta_a_ponta.py
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
for _p in ("app", "rules", "pipeline", "tests"):
    sys.path.insert(0, str(RAIZ / _p))

from werkzeug.datastructures import MultiDict   # noqa: E402

import busca                        # noqa: E402
import relatorio as rel             # noqa: E402
import servicos as sv               # noqa: E402
import web                          # noqa: E402

SAIDA = RAIZ / "docs" / "ATENDIMENTO_EXEMPLO.md"
PASSOS, FALHAS = [], []
CODIGO = None


def etapa(nome, ok, detalhe=""):
    PASSOS.append((nome, ok, detalhe))
    if not ok:
        FALHAS.append((nome, detalhe))
    print("  %s %-46s %s" % ("OK  " if ok else "ERRO", nome[:46],
                             str(detalhe)[:74]))


def main() -> int:
    global CODIGO
    web.app.config["TESTING"] = True
    c = web.app.test_client()

    print("=" * 78)
    print("PONTA A PONTA — um atendimento completo pela aplicação")
    print("=" * 78)

    # ---------------------------------------------------------------- dados
    con = sv.conectar()
    try:
        anticoag = busca.buscar_medicamento(con, "varfarina")[0]
        aine = busca.buscar_medicamento(con, "ibuprofeno")[0]
        anti_hipertensivo = busca.buscar_medicamento(con, "losartana")[0]
        alergia = busca.buscar_substancia(con, "dipirona")[0]
        condicao = busca.buscar_condicao(con, "hipertensão")[0]
        # Um item que o banco de fato cruza com o anticoagulante.
        item = con.execute(
            "SELECT i.id, i.nome FROM interacao_item ii "
            "JOIN item_nao_medicamentoso i ON i.id = ii.item_id "
            "WHERE ii.substancia_id = ? LIMIT 1",
            (anticoag.substancia_id,)).fetchone()
    finally:
        con.close()
    etapa("0. insumos reais localizados no banco",
          all([anticoag, aine, anti_hipertensivo, alergia, condicao, item]),
          "%s · %s · %s · item: %s" % (anticoag.rotulo, aine.rotulo,
                                       anti_hipertensivo.rotulo,
                                       item[1] if item else "—"))

    # ------------------------------------------------------------ 1 paciente
    r = c.post("/novo", data={"nome": "Dona Marlene (caso sintético)",
                              "farmaceutico": "Farm. Ana Souza",
                              "crf": "CRF-AM 12345"})
    CODIGO = r.headers["Location"].split("/a/")[1].split("/")[0]
    r = c.post("/a/%s/paciente" % CODIGO,
               data={"nome": "Dona Marlene (caso sintético)",
                     "data_nascimento": "1949-11-03", "sexo": "F",
                     "peso_kg": "62", "altura_cm": "155",
                     "observacao": "Trouxe receita de duas semanas atrás.",
                     "farmaceutico": "Farm. Ana Souza", "crf": "CRF-AM 12345"})
    etapa("1. paciente identificado", r.status_code == 302, CODIGO)

    # ------------------------------------------------------------ 2 anamnese
    c.post("/a/%s/condicao" % CODIGO, data={"doenca_id": condicao.id})
    c.post("/a/%s/alergia" % CODIGO,
           data={"substancia_id": alergia.substancia_id,
                 "reacao": "urticária e inchaço nos lábios",
                 "gravidade": "GRAVE"})
    c.post("/a/%s/habitos" % CODIGO,
           data={"situacao_ALCOOL": "ATUAL",
                 "frequencia_ALCOOL": "fim de semana",
                 "situacao_TABAGISMO": "NUNCA",
                 "situacao_CAFEINA": "ATUAL", "quantidade_CAFEINA": "3 xícaras",
                 "frequencia_CAFEINA": "diário"})
    pagina = c.get("/a/%s/anamnese" % CODIGO).data.decode("utf-8")
    etapa("2. anamnese registrada",
          condicao.nome in pagina and alergia.rotulo in pagina
          and "urticária" in pagina,
          "1 condição · 1 alergia · 3 hábitos")

    # ------------------------------------- 3 e 4 medicamentos com posologia
    plano = [
        (anticoag, "Varfarina 5 mg", "PRESCRITA", "PRESCRITO", "5", "mg", 1,
         ["20:00"], True),
        (anticoag, "Varfarina 5 mg", "RELATADA", "PRESCRITO", "5", "mg", 1,
         ["20:00"], True),
        (anti_hipertensivo, "Losartana 50 mg", "PRESCRITA", "PRESCRITO", "50",
         "mg", 2, ["08:00", "20:00"], True),
        (anti_hipertensivo, "Losartana 50 mg", "RELATADA", "PRESCRITO", "100",
         "mg", 1, ["08:00"], True),
        (aine, "Ibuprofeno 600 mg", "RELATADA", "AUTOMEDICACAO", "600", "mg",
         3, ["08:00", "14:00", "22:00"], False),
    ]
    grupos = []
    for escolha, rotulo, lista, origem, dose, un, vezes, horas, cont in plano:
        r = c.post("/a/%s/medicamento" % CODIGO,
                   data={"nome_relatado": rotulo, "escolha": escolha.chave,
                         "lista": lista, "origem": origem})
        grupo = r.headers["Location"].rstrip("/").split("/")[-1]
        grupos.append(grupo)
        campos = [("dose_valor", dose), ("dose_unidade", un),
                  ("vezes_por_dia", str(vezes)), ("via_administracao", "oral")]
        if cont:
            campos.append(("uso_continuo", "on"))
        campos += [("horario", h) for h in horas]
        c.post("/a/%s/posologia/%s" % (CODIGO, grupo), data=MultiDict(campos))

    # E o item que a paciente relata usar sem receita, sem reconhecimento.
    c.post("/a/%s/medicamento" % CODIGO,
           data={"nome_relatado": "um chá que a vizinha indicou",
                 "escolha": "", "lista": "RELATADA", "origem": "NAO_INFORMADO"})

    pagina = c.get("/a/%s/medicamentos" % CODIGO).data.decode("utf-8")
    etapa("3. medicamentos e posologias registrados",
          "Varfarina 5 mg" in pagina and "Ibuprofeno 600 mg" in pagina
          and "600 mg" in pagina and "não reconhecido" in pagina,
          "%d itens, 1 deles não reconhecido" % (len(plano) + 1))

    # -------------------------------------------------------------- 5 rotina
    r = c.post("/a/%s/rotina" % CODIGO,
               data={"ACORDAR": "06:30", "CAFE_MANHA": "07:00",
                     "ALMOCO": "12:00", "LANCHE_TARDE": "16:00",
                     "JANTAR": "19:30", "DORMIR": "22:30"})
    etapa("4. rotina do dia informada", r.status_code == 302,
          "acorda 06:30 · almoça 12:00 · dorme 22:30")

    # --------------------------------------------------------------- 6 itens
    c.post("/a/%s/item" % CODIGO,
           data={"item_id": item[0], "frequencia": "DIARIO",
                 "horario_habitual": "08:15"})
    pagina = c.get("/a/%s/itens" % CODIGO).data.decode("utf-8")
    etapa("5. alimento/planta/suplemento registrado", item[1] in pagina, item[1])

    # ---------------------------------------------------------- 7 conciliação
    pagina = c.get("/a/%s/conciliacao" % CODIGO).data.decode("utf-8")
    etapa("6. conciliação mostra as duas listas lado a lado",
          "Prescrito" in pagina and "Relatado pelo paciente" in pagina
          and "Dose diferente" in pagina,
          "divergência de dose da losartana visível")

    # ------------------------------------------------------------- 8 análise
    r = c.post("/a/%s/analisar" % CODIGO, follow_redirects=True)
    con = sv.conectar()
    try:
        res = sv.resultado_atual(con, CODIGO)
    finally:
        con.close()
    etapa("7. análise executada pelo motor",
          r.status_code == 200 and res.resumo["achados"] > 0,
          "%d achados · %d divergências · %d não avaliados"
          % (res.resumo["achados"], res.resumo["divergencias"],
             res.resumo["nao_avaliado"]))

    interacao = [a for a in res.achados if a.tipo == "FARMACO_FARMACO"
                 and "buprofeno" in (a.item_a + (a.item_b or ""))]
    etapa("8. a interação anticoagulante × anti-inflamatório foi detectada",
          bool(interacao),
          "%s — prioridade %s, gravidade %s"
          % (interacao[0].titulo[:44], interacao[0].prioridade,
             interacao[0].gravidade_fonte) if interacao else "não detectada")

    # --------------------------------------------------- 9 achado e evidência
    alvo = interacao[0] if interacao else res.achados[0]
    pagina = c.get("/a/%s/achado?chave=%s"
                   % (CODIGO, alvo.grupo_chave)).data.decode("utf-8")
    etapa("9. o achado abre com os seis eixos e a cadeia de evidência",
          all(x in pagina for x in ("Gravidade da fonte", "Confiança do sistema",
                                    "Prioridade de exibição",
                                    "Por que este achado apareceu",
                                    "Cadeia de detecção", "Origem no banco")),
          "%d evidência(s) de %d fonte(s)"
          % (len(alvo.evidencias), len({e.fonte for e in alvo.evidencias})))

    # ------------------------------------------------------------ 10 revisão
    c.post("/a/%s/achado/revisar" % CODIGO,
           data={"chave": alvo.grupo_chave, "situacao": "REVISADO",
                 "profissional": "Farm. Ana Souza", "crf": "CRF-AM 12345",
                 "observacao": "Orientada a suspender o anti-inflamatório por "
                               "conta própria e procurar o prescritor."})
    divergencia = next((p for p in res.divergencias
                        if p.tipo_divergencia == "DOSE_DIFERENTE"), None)
    if divergencia:
        c.post("/a/%s/divergencia/registrar" % CODIGO,
               data={"chave": sv.chave_divergencia(divergencia),
                     "intencionalidade": "NAO_INTENCIONAL",
                     "profissional": "Farm. Ana Souza", "crf": "CRF-AM 12345",
                     "observacao": "Paciente dobrou a dose por conta própria."})
    pagina = c.get("/a/%s/achado?chave=%s"
                   % (CODIGO, alvo.grupo_chave)).data.decode("utf-8")
    etapa("10. revisão do profissional registrada, com assinatura",
          "Farm. Ana Souza" in pagina and "suspender o anti-inflamatório"
          in pagina)

    # ---------------------------------------------------------- 11 relatório
    r = c.get("/a/%s/relatorio" % CODIGO)
    html_relatorio = r.data.decode("utf-8")
    txt = c.get("/a/%s/relatorio.txt" % CODIGO).data.decode("utf-8")
    etapa("11. relatório gerado, com tudo que a especificação pede",
          r.status_code == 200
          and all(x in html_relatorio for x in
                  ("Resumo", "Farmacoterapia", "Anamnese", "Achados",
                   "Divergências de conciliação", "O que o sistema não avaliou",
                   "Fontes usadas", "Revisão do profissional")),
          "%d caracteres em HTML, %d em texto"
          % (len(html_relatorio), len(txt)))

    r = c.post("/a/%s/concluir" % CODIGO, follow_redirects=True)
    etapa("12. atendimento concluído", "concluído" in r.data.decode("utf-8"))

    # ------------------------------------------------------- documentação
    con = sv.conectar()
    try:
        dados = rel.montar_relatorio(con, CODIGO)
        texto = rel.relatorio_em_texto(dados)
    finally:
        con.close()
    SAIDA.write_text(
        "# Atendimento de exemplo — saída real do sistema\n\n"
        "Gerado por `tests/teste_ponta_a_ponta.py`, que executa um atendimento\n"
        "completo **pela aplicação**, por requisições HTTP reais. A\n"
        "farmacologia vem do banco; a paciente é sintética.\n\n"
        "O caso: idosa em uso de anticoagulante que se automedicou com\n"
        "anti-inflamatório, e que relata dose diferente da prescrita para o\n"
        "anti-hipertensivo. Um dos itens não é reconhecido pelo cadastro, de\n"
        "propósito — para mostrar como o sistema declara o que não avaliou.\n\n"
        "```\n%s\n```\n" % texto, encoding="utf-8", newline="\r\n")
    etapa("13. resultado documentado em docs/ATENDIMENTO_EXEMPLO.md",
          SAIDA.exists() and SAIDA.stat().st_size > 2000,
          "%d bytes" % SAIDA.stat().st_size)

    # ------------------------------------------------------------- limpeza
    con = sv.conectar()
    try:
        linha = con.execute("SELECT id, paciente_id FROM atendimento "
                            "WHERE codigo=?", (CODIGO,)).fetchone()
        if linha:
            con.execute("DELETE FROM atendimento WHERE id=?", (linha[0],))
            con.execute("DELETE FROM paciente WHERE id=?", (linha[1],))
        con.commit()
    finally:
        con.close()

    print("\n" + "=" * 78)
    print("%d etapa(s) · %d ok · %d falha(s)"
          % (len(PASSOS), len(PASSOS) - len(FALHAS), len(FALHAS)))
    for nome, det in FALHAS:
        print("  FALHA: %s — %s" % (nome, det))
    if not FALHAS:
        print("\nO ATENDIMENTO COMPLETO FUNCIONOU DE PONTA A PONTA.")
        print("Relatório do caso: docs/ATENDIMENTO_EXEMPLO.md")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(main())
