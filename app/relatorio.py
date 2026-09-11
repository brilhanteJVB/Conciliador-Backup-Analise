# -*- coding: utf-8 -*-
"""
SERVICO DE RELATORIO — monta o documento do atendimento.

Nao calcula nada clinico: recebe o `ResultadoConciliacao` que o motor
produziu e o organiza para leitura. Se o relatorio precisar de um numero, ele
vem do `resumo` do motor, nunca de uma recontagem por fora — recontar seria
criar uma segunda implementacao, que e o que a especificacao proibe.

CONTRATO

    montar_relatorio(con, codigo) -> dict

O dicionario devolvido e o que o template `relatorio.html` renderiza, e e
tambem o que o teste de ponta a ponta inspeciona. Estrutura primeiro, texto
depois: quem quiser gerar PDF, texto puro ou JSON parte da mesma estrutura.

O QUE O RELATORIO NUNCA FAZ
---------------------------
  - nao apresenta previsao de modelo como se existisse (nao ha ML no projeto);
  - nao esconde o que nao foi avaliado;
  - nao transforma `EXTRAIDO_AUTOMATICAMENTE` em `CONFIRMADO`;
  - nao afirma conduta: o campo `conduta` de um achado e sugestao da fonte.
"""
from __future__ import annotations

import datetime as _dt
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "app"))

import rotulos as rot          # noqa: E402
import servicos as sv          # noqa: E402


def montar_relatorio(con, codigo: str) -> dict:
    at = sv.exigir_atendimento(con, codigo)
    res = sv.resultado_atual(con, codigo)
    anotacoes = sv.listar_anotacoes(con, codigo)

    # O relatorio e o que sai impresso e vai para o prontuario do paciente.
    # E o lugar onde misturar previsao com fato tem a consequencia mais
    # duradoura, entao a separacao e feita na origem: previsto nao entra na
    # secao de achados, tem secao propria no fim, e nao aparece na contagem
    # por prioridade.
    documentados = [a for a in res.achados if a.natureza != "PREVISTO"]
    previstos = [a for a in res.achados if a.natureza == "PREVISTO"]
    achados_por_prioridade = defaultdict(list)
    for a in documentados:
        achados_por_prioridade[a.prioridade].append(a)

    revisados = [(a, anotacoes[("ACHADO", a.grupo_chave)])
                 for a in res.achados
                 if ("ACHADO", a.grupo_chave) in anotacoes]

    divergencias = []
    for p in res.divergencias:
        chave = sv.chave_divergencia(p)
        divergencias.append({
            "par": p,
            "anotacao": anotacoes.get(("DIVERGENCIA", chave)),
            "chave": chave,
        })

    nao_avaliado = defaultdict(list)
    for n in res.nao_avaliado:
        nao_avaliado[n.motivo].append(n)

    fontes = defaultdict(int)
    for a in documentados:
        for e in a.evidencias:
            fontes[e.fonte] += 1

    return {
        "atendimento": at,
        "gerado_em": _dt.datetime.now().strftime("%d/%m/%Y às %H:%M"),
        "resumo": res.resumo,
        "medicamentos": sv.listar_medicamentos(con, codigo),
        "condicoes": sv.listar_condicoes(con, codigo),
        "alergias": sv.listar_alergias(con, codigo),
        "habitos": sv.listar_habitos(con, codigo),
        "itens": sv.listar_itens(con, codigo),
        "rotina": sv.listar_rotina(con, codigo),
        "achados": documentados,
        "achados_previstos": previstos,
        "achados_por_prioridade": dict(achados_por_prioridade),
        "achados_agrupados": res.achados_agrupados,
        "revisados": revisados,
        "divergencias": divergencias,
        "conciliados": res.conciliados,
        "nao_conciliados": res.nao_conciliados,
        "nao_avaliado": dict(nao_avaliado),
        "limitacoes": res.limitacoes,
        "indicadores": res.indicadores,
        "fontes": dict(sorted(fontes.items(), key=lambda x: -x[1])),
        "agenda": res.agenda,
        "versao_motor": res.versao_motor,
        "ordem_prioridade": rot.ORDEM_PRIORIDADE,
    }


def relatorio_em_texto(dados: dict) -> str:
    """Versao em texto puro do mesmo relatorio.

    Serve para o teste de ponta a ponta inspecionar sem HTML, e para quem
    quiser colar o resultado num prontuario que nao aceita formatacao.
    """
    at = dados["atendimento"]
    r = dados["resumo"]
    L = []

    def linha(txt=""):
        L.append(txt)

    linha("=" * 72)
    linha("CONCILIAÇÃO MEDICAMENTOSA — atendimento %s" % at["codigo"])
    linha("=" * 72)
    linha("Paciente: %s%s" % (at["nome"],
                              "  ·  %d anos" % at["idade"] if at["idade"]
                              is not None else ""))
    linha("Sexo: %s" % rot.rotular(rot.SEXO, at["sexo"]))
    linha("Farmacêutico: %s%s" % (at["farmaceutico"] or "não informado",
                                  "  ·  %s" % at["crf"] if at["crf"] else ""))
    linha("Iniciado em: %s   ·   Relatório gerado em: %s"
          % (at["iniciado_em"], dados["gerado_em"]))
    linha("Motor: %s" % dados["versao_motor"])
    linha()

    linha("RESUMO")
    linha("  Medicamentos analisados ......... %d" % r["medicamentos"])
    linha("  Achados ......................... %d" % r["achados"])
    linha("    críticos ...................... %d" % r["criticos"])
    linha("    altos ......................... %d" % r["altos"])
    linha("    moderados ..................... %d" % r["moderados"])
    linha("    baixos ........................ %d" % r["baixos"])
    linha("    informativos .................. %d" % r["informativos"])
    linha("  Divergências de conciliação ..... %d" % r["divergencias"])
    linha("  Informações insuficientes ....... %d" % r["informacao_insuficiente"])
    linha("  Itens não avaliados ............. %d" % r["nao_avaliado"])
    linha("  Revisão profissional necessária . %s"
          % ("SIM" if r["requer_revisao_profissional"] else "NÃO"))
    linha()

    linha("FARMACOTERAPIA")
    for g in dados["medicamentos"]:
        marca = "" if g.reconhecido else "   [NÃO RECONHECIDO]"
        linha("  · %s (%s)%s" % (g.nome_relatado,
                                 dict(sv.LISTAS).get(g.lista, g.lista), marca))
        linha("      %s" % g.resumo_posologia())
        if g.substancias:
            linha("      princípio ativo: %s"
                  % ", ".join(n for _i, n in g.substancias))
    linha()

    if dados["condicoes"]:
        linha("CONDIÇÕES CLÍNICAS")
        for c in dados["condicoes"]:
            linha("  · %s" % (c["nome"] or c["descricao_livre"]))
        linha()
    if dados["alergias"]:
        linha("ALERGIAS")
        for a in dados["alergias"]:
            linha("  · %s%s" % (a["substancia"] or a["descricao_livre"],
                                "  (%s)" % a["reacao"] if a["reacao"] else ""))
        linha()

    linha("ACHADOS")
    if not dados["achados"]:
        linha("  Nenhum achado. Isso NÃO significa ausência de risco: veja a "
              "seção do que não foi avaliado.")
    for p in rot.ORDEM_PRIORIDADE:
        lista = dados["achados_por_prioridade"].get(p, [])
        if not lista:
            continue
        linha()
        linha("  --- %s (%d) ---" % (rot.PRIORIDADE[p].upper(), len(lista)))
        for a in lista:
            linha("  · %s" % a.titulo)
            linha("      módulo: %s" % rot.rotular(rot.MODULO, a.tipo))
            linha("      gravidade da fonte: %s   |   confiança do sistema: %s"
                  % (rot.rotular(rot.GRAVIDADE, a.gravidade_fonte),
                     rot.rotular(rot.CONFIANCA, a.confianca_sistema)))
            linha("      situação da informação: %s"
                  % rot.rotular(rot.STATUS_INFORMACAO, a.status_informacao))
            if a.efeito_esperado:
                linha("      efeito esperado: %s" % a.efeito_esperado)
            if a.mecanismo:
                linha("      mecanismo: %s" % a.mecanismo)
            if a.conduta:
                linha("      sugestão da fonte: %s" % a.conduta)
            linha("      por que apareceu: %s" % a.explicacao)
            if a.fonte:
                linha("      fonte: %s" % a.fonte)
    linha()

    if dados["achados_previstos"]:
        linha("PREVISTO POR MODELO — NAO E INTERACAO DOCUMENTADA")
        linha("  Nenhuma fonte do acervo afirma os pares abaixo. Sao")
        linha("  estimativas estatisticas da probabilidade de o par ESTAR")
        linha("  DOCUMENTADO em alguma base — nao da gravidade e nao do risco.")
        linha("  Nao entram na contagem por prioridade. Exigem verificacao em")
        linha("  fonte antes de qualquer conduta.")
        for a in dados["achados_previstos"]:
            linha()
            linha("  · %s" % a.titulo)
            linha("      evidência documental: NENHUMA")
            linha("      probabilidade estimada: %s"
                  % rot.percentual_previsao(a.probabilidade_modelo))
            linha("      modelo: %s" % a.metodo_deteccao)
            linha("      rastreabilidade: %s" % a.origem_afirmacao)
            linha("      confiança do sistema: %s"
                  % rot.rotular(rot.CONFIANCA, a.confianca_sistema))
            linha("      %s" % a.explicacao)
        linha()

    if dados["divergencias"]:
        linha("DIVERGÊNCIAS DE CONCILIAÇÃO")
        for d in dados["divergencias"]:
            p = d["par"]
            linha("  · %s — %s" % (p.nome_exibicao,
                                   rot.rotular(rot.TIPO_DIVERGENCIA,
                                               p.tipo_divergencia)))
            if p.valor_prescrito or p.valor_relatado:
                linha("      prescrito: %s   |   relatado: %s"
                      % (p.valor_prescrito or "—", p.valor_relatado or "—"))
            linha("      intencionalidade: %s"
                  % rot.rotular(rot.INTENCIONALIDADE, p.intencionalidade))
            if d["anotacao"]:
                an = d["anotacao"]
                linha("      registrado por %s em %s%s"
                      % (an["profissional"], an["registrado_em"],
                         ": %s" % an["observacao"] if an["observacao"] else ""))
        linha()

    linha("O QUE O SISTEMA NÃO AVALIOU")
    if not dados["nao_avaliado"]:
        linha("  (nada declarado)")
    for motivo, itens in dados["nao_avaliado"].items():
        linha("  · %s (%d)" % (rot.rotular(rot.MOTIVO_NAO_AVALIADO, motivo),
                               len(itens)))
        for n in itens[:6]:
            linha("      – %s" % n.item)
        if len(itens) > 6:
            linha("      – ... e mais %d" % (len(itens) - 6))
    linha()

    if dados["limitacoes"]:
        linha("LIMITAÇÕES DESTA ANÁLISE")
        for lim in dados["limitacoes"]:
            linha("  · %s" % lim)
        linha()

    if dados["revisados"]:
        linha("REVISÃO DO PROFISSIONAL")
        for a, an in dados["revisados"]:
            linha("  · %s — %s por %s em %s"
                  % (a.titulo, an["situacao"].lower().replace("_", " "),
                     an["profissional"], an["registrado_em"]))
            if an["observacao"]:
                linha("      %s" % an["observacao"])
        linha()

    linha("FONTES USADAS NESTE RELATÓRIO")
    for fonte, n in dados["fontes"].items():
        linha("  · %s — %d evidência(s)" % (fonte, n))
    linha()
    linha("-" * 72)
    linha("Este relatório é apoio à decisão. Nenhuma conduta foi alterada "
          "automaticamente;")
    linha("toda decisão terapêutica permanece com o profissional.")
    return "\n".join(L)
