# -*- coding: utf-8 -*-
"""
PRIORIDADE DE EXIBICAO DO ACHADO — tabela explicita, com justificativa por peso.

POR QUE ESTE ARQUIVO EXISTE SEPARADO
------------------------------------
Prioridade e a decisao mais contestavel do sistema inteiro: e ela que decide o
que o farmaceutico le primeiro num balcao com fila. Deixa-la espalhada dentro
do motor tornaria impossivel discutir um peso sem ler o motor todo. Aqui cada
regra e uma linha de dados com o motivo escrito ao lado, e o autoteste no fim
do arquivo prova que a tabela faz o que diz.

OS TRES EIXOS NAO SE MISTURAM
-----------------------------
    gravidade_fonte     o que a FONTE diz sobre o dano possivel
    confianca_sistema   o quanto o SISTEMA confia no que esta afirmando
    prioridade          em que ordem MOSTRAR

Um achado pode ser potencialmente grave e ter confianca baixa. A especificacao
exige que isso apareca de forma independente, e aparece: as duas primeiras sao
colunas proprias do achado; so a terceira e calculada aqui.

O QUE A PRIORIDADE **NAO** FAZ
------------------------------
Nao inventa gravidade. Quando a fonte nao gradua, o achado nao vira ALTO por
precaucao nem some por conveniencia: fica BAIXO, com
`status_informacao='NAO_DETERMINADO'` e revisao exigida, e e contado a parte
no resumo. Inflar seria mentir sobre a fonte; esconder seria pior.

Autoteste: python rules/_prioridade.py
"""
from __future__ import annotations

# Do mais urgente ao menos. A ordem e usada para comparar e para rebaixar.
ESCALA = ["CRITICO", "ALTO", "MODERADO", "BAIXO", "INFORMATIVO"]


def percentual_previsao(p) -> str:
    """A probabilidade de uma previsao, escrita sem prometer certeza.

    A calibracao isotonica SATURA. A faixa mais alta da validacao recebe
    exatamente 1,0 quando todos os pares daquela faixa estavam documentados —
    o que e uma frequencia observada num conjunto finito, nao uma certeza.
    Escrito como "100%", ao lado da frase "nao ha evidencia documental para
    este par", vira a contradicao mais forte que este sistema poderia
    produzir: o farmaceutico le certeza absoluta numa linha que existe
    justamente para dizer que nao ha fonte nenhuma.

    O numero exato continua visivel no painel de rastreabilidade, com quatro
    casas. Aqui sai o teto declarado. Achado pela inspecao visual da Fase 9.

    Uma unica definicao: o motor escreve a explicacao, a tela e o relatorio
    imprimem o valor, e os tres tem de dizer a mesma coisa.
    """
    if p is None:
        return "não informada"
    p = float(p)
    if p >= 0.995:
        return "acima de 99%"
    if p <= 0.005:
        return "abaixo de 1%"
    return "%.0f%%" % (100 * p)


def probabilidade_saturada(p) -> bool:
    """Verdadeiro quando o valor calibrado esta no teto (ou no piso) da
    tabela — e a tela precisa explicar o que isso significa."""
    return p is not None and (float(p) >= 0.995 or float(p) <= 0.005)


def _desce(prioridade: str, degraus: int = 1) -> str:
    i = min(len(ESCALA) - 1, ESCALA.index(prioridade) + degraus)
    return ESCALA[i]


def mais_grave(a: str, b: str) -> str:
    """Devolve a prioridade mais alta entre duas."""
    return ESCALA[min(ESCALA.index(a), ESCALA.index(b))]


# =====================================================================
# TABELA BASE — (modulo, chave) -> (prioridade, por que)
#
# `chave` e o subtipo, a relacao declarada pela fonte ou a gravidade dela,
# conforme o modulo. Cada linha diz POR QUE, e esse texto vai para o campo
# `justificativa_prioridade` do achado: o farmaceutico ve o motivo, nao so o
# rotulo.
# =====================================================================
BASE = {
    # ---- modulo 3: alergia. O unico que chega a CRITICO por regra. -------
    ("FARMACO_ALERGIA", "SUBSTANCIA_EXATA"): (
        "CRITICO",
        "O paciente declarou alergia a esta substância e ela está na "
        "farmacoterapia. É a única situação em que o dado do próprio paciente, "
        "e não uma fonte externa, sustenta o alerta."),
    ("FARMACO_ALERGIA", "MESMA_CLASSE_ATC"): (
        "ALTO",
        "A substância pertence à mesma classe ATC de uma alergia declarada. "
        "Reatividade cruzada é possível, não certa — por isso ALTO e não "
        "CRÍTICO, e o achado sai como POSSÍVEL."),
    ("FARMACO_ALERGIA", "ALERGIA_SEM_VINCULO"): (
        "INFORMATIVO",
        "A alergia foi registrada em texto livre e não pôde ser ligada a uma "
        "substância do cadastro. Sem esse vínculo o sistema não tem como "
        "comparar — declara a limitação em vez de simular uma verificação."),

    # ---- modulo 2 e 10: doenca, contraindicacao e precaucao --------------
    ("FARMACO_DOENCA", "CONTRAINDICADO"): (
        "ALTO",
        "A fonte declara contraindicação e a condição está presente no "
        "paciente. A relação é afirmada pela fonte, não deduzida."),
    ("FARMACO_DOENCA", "USAR_COM_CAUTELA"): (
        "MODERADO",
        "A fonte pede cautela, não proíbe. Tratar precaução como proibição "
        "produziria alerta que o próprio texto da bula não sustenta."),
    ("FARMACO_DOENCA", "AJUSTAR_DOSE"): (
        "MODERADO",
        "A fonte indica ajuste de dose na presença da condição: é conduta a "
        "conferir, não impedimento de uso."),
    ("FARMACO_DOENCA", "NAO_DETERMINADA"): (
        "INFORMATIVO",
        "Há relação registrada entre o medicamento e a condição, mas a fonte "
        "não diz qual. Sem direção, não há alerta — há uma pendência."),

    # ---- modulo 1: farmaco x farmaco, pela gravidade da fonte ------------
    ("FARMACO_FARMACO", "MAIOR"): (
        "ALTO",
        "Interação documentada e graduada como maior pela fonte."),
    ("FARMACO_FARMACO", "MODERADA"): (
        "MODERADO",
        "Interação documentada e graduada como moderada pela fonte."),
    ("FARMACO_FARMACO", "MENOR"): (
        "BAIXO",
        "Interação documentada e graduada como menor pela fonte."),
    ("FARMACO_FARMACO", "NAO_DETERMINADA"): (
        "BAIXO",
        "A interação está documentada, mas NENHUMA fonte do acervo graduou a "
        "gravidade deste par. Não sobe porque não há gravidade que sustente "
        "subir; não some porque a interação existe. Fica BAIXO, exige revisão "
        "e é contado à parte no resumo."),

    # ---- modulo 13: interacao PREVISTA por modelo (Fase 8) ---------------
    # Teto INFORMATIVO, e o teto e o ponto. Uma previsao nao tem gravidade de
    # fonte para sustentar prioridade nenhuma: o modelo estima a probabilidade
    # de o par ESTAR DOCUMENTADO, nao o tamanho do dano. Deixa-la competir por
    # ordem com interacao documentada seria exatamente misturar previsao com
    # fato. Ela aparece, em bloco proprio, embaixo — e nunca acima de um
    # achado que tem documento atras.
    ("FARMACO_FARMACO", "PREVISTA"): (
        "INFORMATIVO",
        "Nenhuma fonte do acervo afirma esta interação. A linha vem de um "
        "modelo estatístico, que estima a probabilidade de o par estar "
        "documentado em alguma base — não a gravidade nem o risco. Fica em "
        "INFORMATIVO por definição, não por cálculo: sem documento não há "
        "gravidade que sustente subir. Exige verificação antes de qualquer "
        "conduta."),

    # ---- modulo 7: CYP. Inferencia mecanistica, nunca documento. ---------
    ("FARMACO_CYP", "FORTE"): (
        "MODERADO",
        "Um dos medicamentos é inibidor ou indutor FORTE de uma enzima da qual "
        "o outro é substrato sensível (tabela de fármacos-índice da FDA). É "
        "inferência mecanística, não interação observada: por isso não passa "
        "de MODERADO por mais forte que seja o inibidor."),
    ("FARMACO_CYP", "MODERADA"): (
        "BAIXO",
        "Mesma inferência mecanística, com potência moderada declarada pela "
        "FDA. Inferência com potência menor não pode valer mais que "
        "interação documentada."),

    # ---- modulo 8: duplicidade ------------------------------------------
    ("DUPLICIDADE", "MESMA_SUBSTANCIA"): (
        "ALTO",
        "A mesma substância aparece em mais de um item da farmacoterapia. É a "
        "via mais comum de dose dobrada no balcão — frequentemente por marca e "
        "genérico do mesmo princípio ativo. Pode ser associação intencional, "
        "e por isso é alerta, não conclusão."),
    ("DUPLICIDADE", "MESMA_CLASSE_ATC4"): (
        "MODERADO",
        "Duas substâncias diferentes do mesmo 4º nível ATC: mesmo subgrupo "
        "químico-terapêutico, isto é, mesma finalidade — dois inibidores da "
        "bomba de prótons, dois inibidores da ECA, duas estatinas. O 4º nível "
        "é o nível certo para isto: o 5º identifica a própria substância e "
        "jamais agruparia duas substâncias diferentes. Somar efeito pode ser "
        "terapia combinada intencional, então o achado aponta e não decide."),

    # ---- modulos 4, 5 e 6: alimento, planta e suplemento -----------------
    # Mesma escala de gravidade dos demais; o que muda e o CONTEXTO, tratado
    # nos modificadores: item declarado pelo paciente x orientacao preventiva.
    ("ITEM", "MAIOR"):            ("ALTO", "Interação com o item graduada como maior pela fonte."),
    ("ITEM", "MODERADA"):         ("MODERADO", "Interação com o item graduada como moderada pela fonte."),
    ("ITEM", "MENOR"):            ("BAIXO", "Interação com o item graduada como menor pela fonte."),
    ("ITEM", "NAO_DETERMINADA"):  ("BAIXO", "Interação com o item registrada sem gravidade na fonte."),

    # ---- modulo de habito: alcool, tabaco, cafeina -----------------------
    ("FARMACO_HABITO", "MAIOR"):           ("ALTO", "Interação com hábito graduada como maior pela fonte."),
    ("FARMACO_HABITO", "MODERADA"):        ("MODERADO", "Interação com hábito graduada como moderada pela fonte."),
    ("FARMACO_HABITO", "MENOR"):           ("BAIXO", "Interação com hábito graduada como menor pela fonte."),
    ("FARMACO_HABITO", "NAO_DETERMINADA"): ("BAIXO", "Interação com hábito registrada sem gravidade na fonte."),

    # ---- modulo 9 e 11: horario, administracao, posologia ----------------
    # Vem do motor da Fase 4 e ja chega classificado por ele.
    ("CONFLITO_HORARIO", "CONFLITO_CONFIRMADO"): (
        "MODERADO",
        "O conflito de horário foi calculado sobre dado real do paciente e a "
        "fonte declarou o intervalo. É problema de administração, corrigível "
        "por orientação — não risco farmacológico direto."),
    ("CONFLITO_HORARIO", "POSSIVEL_CONFLITO"): (
        "BAIXO",
        "O conflito depende de janela de leitura ou de dado que o paciente não "
        "informou. Possível não é confirmado."),
    ("CONFLITO_HORARIO", "REGRA_DESCONHECIDA"): (
        "INFORMATIVO",
        "A fonte manda separar mas não publica o intervalo. Nenhum número foi "
        "presumido; o que existe é uma pendência a resolver com o paciente."),
    ("CONFLITO_HORARIO", "INFORMACAO_INSUFICIENTE"): (
        "INFORMATIVO",
        "Falta dado do paciente para verificar. Ausência de dado não vira "
        "alerta de gravidade."),
    ("REGRA_ADMINISTRACAO", "ORIENTACAO"): (
        "INFORMATIVO",
        "Orientação de como tomar, não problema detectado. Aparece para ser "
        "repassada ao paciente."),
    ("REGRA_ADMINISTRACAO", "FONTES_CONFLITANTES"): (
        "MODERADO",
        "Duas leituras de fonte discordam sobre a relação com alimento. O "
        "sistema não escolhe: mostra as duas e pede decisão."),
    ("POSOLOGIA", "FREQUENCIA_INCOMPATIVEL"): (
        "MODERADO",
        "A frequência declarada não bate com os horários informados. Pode ser "
        "erro de registro ou de uso — as duas merecem conferência."),
    ("POSOLOGIA", "INTERVALO_MENOR_QUE_O_DECLARADO"): (
        "MODERADO",
        "Duas tomadas estão mais próximas que o intervalo da própria "
        "posologia. É excesso de exposição em um dia normal de uso."),
    ("POSOLOGIA", "DOSE_NAO_INFORMADA"): (
        "INFORMATIVO",
        "Sem dose não há como conferir dose. Comum no balcão e declarado como "
        "limitação, não como alerta."),

    # ---- conciliacao propriamente dita -----------------------------------
    ("DIVERGENCIA_CONCILIACAO", "DESCONTINUADO_EM_USO"): (
        "ALTO",
        "O paciente relata continuar usando um medicamento cuja duração "
        "prevista já terminou, ou que consta como suspenso. É o erro de "
        "conciliação clássico e o de consequência mais direta."),
    ("DIVERGENCIA_CONCILIACAO", "SO_NA_PRESCRICAO"): (
        "MODERADO",
        "Está prescrito e o paciente não relatou usar. Pode ser omissão de "
        "uso, falha de adesão ou simples esquecimento no relato — o sistema "
        "não distingue e não deve fingir que distingue."),
    ("DIVERGENCIA_CONCILIACAO", "SO_NO_RELATO"): (
        "MODERADO",
        "O paciente usa e não consta da prescrição apresentada. Automedicação, "
        "prescrição de outro serviço ou item esquecido na lista."),
    ("DIVERGENCIA_CONCILIACAO", "DOSE_DIFERENTE"): (
        "MODERADO",
        "A dose prescrita e a relatada não coincidem. Diferença não é erro: "
        "pode ser ajuste posterior que a lista não acompanhou."),
    ("DIVERGENCIA_CONCILIACAO", "FREQUENCIA_DIFERENTE"): (
        "MODERADO",
        "A frequência prescrita e a relatada não coincidem."),
    ("DIVERGENCIA_CONCILIACAO", "VIA_DIFERENTE"): (
        "MODERADO",
        "A via prescrita e a relatada não coincidem."),
    ("DIVERGENCIA_CONCILIACAO", "HORARIO_DIFERENTE"): (
        "BAIXO",
        "Os horários diferem. É o tipo de divergência com maior chance de ser "
        "adaptação legítima do paciente à própria rotina."),
    ("DIVERGENCIA_CONCILIACAO", "POSOLOGIA_INSUFICIENTE"): (
        "INFORMATIVO",
        "Falta posologia em um dos lados: não há o que comparar. Declarado "
        "como informação insuficiente, nunca como divergência."),
    ("DIVERGENCIA_CONCILIACAO", "SEM_CORRESPONDENCIA"): (
        "INFORMATIVO",
        "O item não pôde ser ligado a nenhuma substância do cadastro, então "
        "não pôde ser conciliado com segurança."),
    ("DIVERGENCIA_CONCILIACAO", "DUPLICIDADE"): (
        "MODERADO",
        "O mesmo item aparece duas vezes na mesma lista."),

    # ---- modulo 12: informacao insuficiente ------------------------------
    ("INFORMACAO_INSUFICIENTE", "QUALQUER"): (
        "INFORMATIVO",
        "Falta informação para avaliar. A especificação proíbe transformar "
        "ausência de dado em alerta de gravidade alta — o sistema declara o "
        "que não conseguiu avaliar e para por aí."),
}

# Modulos de item que compartilham a mesma linha da tabela.
MODULOS_ITEM = ("FARMACO_ALIMENTO", "FARMACO_PLANTA", "FARMACO_SUPLEMENTO")


def _chave_base(modulo: str) -> str:
    return "ITEM" if modulo in MODULOS_ITEM else modulo


# =====================================================================
# MODIFICADORES DE CONTEXTO
#
# So entram aqui fatores que o BANCO realmente tem e que a fonte sustenta.
# Idade e um exemplo do que ficou de FORA de proposito: sem instrumento
# carregado (Beers, STOPP/START), o sistema nao tem base para dizer que um
# fármaco e inadequado no idoso. A idade entra no texto de contexto do
# achado, para o farmaceutico ver, e NAO mexe na prioridade. A lacuna esta
# registrada em docs/novas_fontes.md, Lacuna 2.
# =====================================================================
def calcular(modulo: str, chave: str, *, confianca_sistema: str = "MEDIA",
             classificacao: str = "CONFIRMADO", anafilaxia: bool = False,
             item_declarado: bool = True) -> tuple:
    """Devolve (prioridade, justificativa).

    Os modificadores sao aplicados na ordem abaixo, e cada um acrescenta a
    sua frase a justificativa — o farmaceutico ve o caminho inteiro, nao so
    o resultado.
    """
    entrada = BASE.get((_chave_base(modulo), chave))
    if entrada is None:
        # Nunca inventa: o que a tabela nao cobre e informativo e declarado.
        return ("INFORMATIVO",
                "Combinação (%s / %s) não prevista na tabela de prioridade. "
                "O sistema não arbitra o que não sabe classificar: exibe como "
                "informativo e pede revisão." % (modulo, chave))
    prioridade, porque = entrada
    partes = [porque]

    # 1. Anafilaxia declarada pelo paciente sobrepoe tudo.
    if anafilaxia and modulo == "FARMACO_ALERGIA":
        prioridade = "CRITICO"
        partes.append("O paciente relatou anafilaxia como reação: nenhuma "
                      "outra consideração rebaixa este achado.")
        return prioridade, " ".join(partes)

    # 2. Informacao insuficiente nunca vira alerta grave.
    if classificacao == "INFORMACAO_INSUFICIENTE" and prioridade != "INFORMATIVO":
        prioridade = "INFORMATIVO"
        partes.append("Rebaixado a informativo porque falta dado do paciente "
                      "para confirmar o achado.")

    # 3. Item que o paciente NAO declarou usar vira orientacao preventiva.
    elif modulo in MODULOS_ITEM and not item_declarado:
        prioridade = "INFORMATIVO"
        partes.append("O paciente não declarou usar este item. Vira orientação "
                      "preventiva a repassar, não alerta sobre uso atual.")

    # 4. Confianca baixa desce um degrau — menos na alergia, que e dado do
    #    proprio paciente e nao depende de fonte externa nenhuma.
    elif confianca_sistema == "BAIXA" and modulo != "FARMACO_ALERGIA":
        antes = prioridade
        prioridade = _desce(prioridade)
        if prioridade != antes:
            partes.append("Rebaixado de %s para %s porque a confiança do "
                          "sistema nesta afirmação é BAIXA (extração não "
                          "revisada ou fonte de procedência fraca). A "
                          "gravidade da fonte não mudou: continua exibida "
                          "separadamente." % (antes, prioridade))

    return prioridade, " ".join(partes)


def confianca(confianca_extracao: str, nivel_evidencia: str,
              confiabilidade_fonte: str, natureza: str) -> str:
    """ALTA / MEDIA / BAIXA — o quanto o SISTEMA confia no que afirma.

    Distinta da gravidade em todos os sentidos: mede a qualidade do caminho
    que trouxe a afirmacao ate aqui, nunca o tamanho do dano.
    """
    if natureza in ("PREVISTO", "POSSIVEL"):
        return "BAIXA"
    if confianca_extracao == "EXTRAIDA_AUTOMATICAMENTE":
        return "BAIXA"
    if (confiabilidade_fonte or "").upper() == "BAIXA":
        return "BAIXA"
    if (confianca_extracao in ("REVISADA", "CURADORIA_HUMANA")
            and nivel_evidencia == "RESPALDADA"):
        return "ALTA"
    if (confianca_extracao in ("CARGA_DIRETA", "CALCULADO")
            and (confiabilidade_fonte or "").upper() == "ALTA"
            and nivel_evidencia == "RESPALDADA"):
        return "ALTA"
    return "MEDIA"


def melhor_confianca(valores) -> str:
    """A melhor confianca entre varias evidencias do mesmo achado.

    Duas fontes sustentando a mesma afirmacao nao pioram a confianca: vale a
    melhor delas, e as outras continuam listadas como evidencia.
    """
    ordem = ["ALTA", "MEDIA", "BAIXA"]
    vistos = [v for v in valores if v in ordem]
    if not vistos:
        return "BAIXA"
    return ordem[min(ordem.index(v) for v in vistos)]


# =====================================================================
# AUTOTESTE
# =====================================================================
if __name__ == "__main__":
    import sys

    falhas = []

    def checa(nome, obtido, esperado):
        if obtido != esperado:
            falhas.append("%s: obtido %r, esperado %r" % (nome, obtido, esperado))
            print("   ERRO %-52s %s (esperado %s)" % (nome, obtido, esperado))
        else:
            print("   OK   %-52s %s" % (nome, obtido))

    print("autoteste de _prioridade.py\n")
    print("-- tabela base --")
    checa("alergia exata", calcular("FARMACO_ALERGIA", "SUBSTANCIA_EXATA",
                                    confianca_sistema="ALTA")[0], "CRITICO")
    checa("alergia por classe", calcular("FARMACO_ALERGIA", "MESMA_CLASSE_ATC",
                                         confianca_sistema="MEDIA")[0], "ALTO")
    checa("contraindicacao", calcular("FARMACO_DOENCA", "CONTRAINDICADO",
                                      confianca_sistema="MEDIA")[0], "ALTO")
    checa("interacao maior", calcular("FARMACO_FARMACO", "MAIOR",
                                      confianca_sistema="MEDIA")[0], "ALTO")
    checa("interacao sem gravidade", calcular("FARMACO_FARMACO", "NAO_DETERMINADA",
                                              confianca_sistema="MEDIA")[0], "BAIXO")
    checa("duplicidade de substancia", calcular("DUPLICIDADE", "MESMA_SUBSTANCIA",
                                                confianca_sistema="ALTA")[0], "ALTO")
    checa("duplicidade terapeutica (ATC 4)",
          calcular("DUPLICIDADE", "MESMA_CLASSE_ATC4",
                   confianca_sistema="ALTA")[0], "MODERADO")
    checa("CYP forte e so inferencia", calcular("FARMACO_CYP", "FORTE",
                                                confianca_sistema="MEDIA")[0], "MODERADO")

    print("\n-- a especificacao exige: informacao insuficiente NAO vira alerta grave --")
    checa("interacao maior mas sem dado",
          calcular("FARMACO_FARMACO", "MAIOR", confianca_sistema="ALTA",
                   classificacao="INFORMACAO_INSUFICIENTE")[0], "INFORMATIVO")
    checa("divergencia sem posologia",
          calcular("DIVERGENCIA_CONCILIACAO", "POSOLOGIA_INSUFICIENTE")[0],
          "INFORMATIVO")

    print("\n-- confianca baixa desce um degrau, mas nunca na alergia --")
    checa("contraindicacao com confianca baixa",
          calcular("FARMACO_DOENCA", "CONTRAINDICADO",
                   confianca_sistema="BAIXA")[0], "MODERADO")
    checa("alergia exata com confianca baixa",
          calcular("FARMACO_ALERGIA", "SUBSTANCIA_EXATA",
                   confianca_sistema="BAIXA")[0], "CRITICO")

    print("\n-- anafilaxia sobrepoe --")
    checa("classe ATC + anafilaxia",
          calcular("FARMACO_ALERGIA", "MESMA_CLASSE_ATC", anafilaxia=True)[0],
          "CRITICO")

    print("\n-- item nao declarado vira orientacao preventiva --")
    checa("toranja MAIOR, paciente nao declarou",
          calcular("FARMACO_ALIMENTO", "MAIOR", confianca_sistema="MEDIA",
                   item_declarado=False)[0], "INFORMATIVO")
    checa("toranja MAIOR, paciente declarou",
          calcular("FARMACO_ALIMENTO", "MAIOR", confianca_sistema="MEDIA",
                   item_declarado=True)[0], "ALTO")

    print("\n-- combinacao desconhecida nao e arbitrada --")
    p, j = calcular("MODULO_QUE_NAO_EXISTE", "CHAVE_QUALQUER")
    checa("modulo inexistente", p, "INFORMATIVO")
    checa("justificativa diz que nao sabe", "não arbitra" in j, True)

    print("\n-- toda entrada da tabela tem justificativa nao vazia --")
    vazias = [k for k, (p, j) in BASE.items() if not j or len(j) < 30]
    checa("entradas sem justificativa", vazias, [])
    checa("toda prioridade esta na escala",
          sorted({p for p, _ in BASE.values()} - set(ESCALA)), [])

    print("\n-- confianca do sistema --")
    checa("regex nao revisada", confianca("EXTRAIDA_AUTOMATICAMENTE",
                                          "RESPALDADA", "ALTA", "DOCUMENTADO"),
          "BAIXA")
    checa("carga direta de fonte alta", confianca("CARGA_DIRETA", "RESPALDADA",
                                                  "ALTA", "DOCUMENTADO"), "ALTA")
    checa("carga direta, evidencia limitada",
          confianca("CARGA_DIRETA", "LIMITADA", "ALTA", "DOCUMENTADO"), "MEDIA")
    checa("inferencia mecanistica", confianca("CARGA_DIRETA", "RESPALDADA",
                                              "ALTA", "POSSIVEL"), "BAIXA")
    checa("melhor entre duas fontes",
          melhor_confianca(["BAIXA", "ALTA", "MEDIA"]), "ALTA")

    print("\n%s" % ("FALHOU — %d" % len(falhas) if falhas
                    else "todos os testes passaram"))
    sys.exit(1 if falhas else 0)
