# -*- coding: utf-8 -*-
"""
MOTOR DE CONCILIACAO — o nucleo do sistema.

Recebe um atendimento e devolve os problemas relacionados a farmacoterapia que
merecem atencao, priorizados e explicados. Nao e "mostrar interacoes": e
identificar o que precisa ser conferido, dizer por que, e declarar o que nao
foi possivel avaliar.

CONTRATO PUBLICO (o que a Fase 6 vai consumir):

    conciliar_atendimento(con, atendimento_id, persistir=False)
        -> ResultadoConciliacao

    .resumo                dict   contagens estruturadas
    .achados               list[Achado]        so os representantes, ordenados
    .achados_agrupados     list[Achado]        os absorvidos, preservados
    .divergencias          list[ParConciliado] situacao <> CONCILIADO
    .conciliados           list[ParConciliado]
    .nao_conciliados       list[ParConciliado]
    .conflitos             list                conflitos crus da Fase 4
    .nao_avaliado          list[NaoAvaliado]
    .limitacoes            list[str]
    .indicadores           dict
    .agenda                Agenda              a estrutura inteira da Fase 4

Uma funcao publica. A interface le estas listas e desenha; **nao reimplementa
regra nenhuma**.

ARQUITETURA
-----------
    paciente -> contexto -> 12 modulos -> achados -> agrupamento ->
    prioridade -> ResultadoConciliacao

O motor de horarios da Fase 4 e CONSUMIDO, nao reimplementado: `montar_agenda`
continua dona de toda regra temporal, e este modulo traduz os conflitos dela
em achados. Regra de administracao pertence ao motor de administracao;
classificacao, contexto, agrupamento e prioridade pertencem a este.

O QUE O SISTEMA NAO FAZ
-----------------------
Detecta, compara, organiza, alerta, sugere e explica. **Nao** altera
prescricao, nao suspende, nao substitui, nao muda dose nem horario, e nao
afirma conduta definitiva. Todo campo `conduta` e sugestao vinda da fonte ou
do proprio texto do achado, e a decisao clinica continua com o profissional.

TRES SEPARACOES QUE O CODIGO INTEIRO RESPEITA
---------------------------------------------
1. gravidade da fonte  x  confianca do sistema  x  prioridade de exibicao
2. natureza da afirmacao  x  classificacao no paciente  x  status da informacao
3. situacao da divergencia (o sistema calcula)  x  intencionalidade (so
   profissional identificado decide, e o CHECK do esquema exige a assinatura)
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _prioridade as prio                                    # noqa: E402
from motor_horarios import montar_agenda                      # noqa: E402

VERSAO_MOTOR = "conciliacao-1.0"

# Listas que representam exposicao ATUAL do paciente. HISTORICO e ANTERIOR
# ficam de fora da analise farmacologica de propostio: sao memoria, nao uso.
LISTAS_ATIVAS = ("PRESCRITA", "RELATADA", "EM_USO")
LISTAS_PASSADAS = ("ANTERIOR", "HISTORICO")

# Tipo do item nao medicamentoso -> qual dos tres modulos o recebe.
MODULO_POR_TIPO_ITEM = {
    "ALIMENTO": "FARMACO_ALIMENTO", "BEBIDA": "FARMACO_ALIMENTO",
    "CHA": "FARMACO_PLANTA", "PLANTA_MEDICINAL": "FARMACO_PLANTA",
    "SUPLEMENTO": "FARMACO_SUPLEMENTO", "VITAMINA": "FARMACO_SUPLEMENTO",
    "MINERAL": "FARMACO_SUPLEMENTO",
}

NOME_HABITO = {"TABAGISMO": "tabagismo", "ALCOOL": "consumo de álcool",
               "CAFEINA": "consumo de cafeína", "ENERGETICO": "energéticos"}

ORDEM_GRAVIDADE = {"MAIOR": 0, "MODERADA": 1, "MENOR": 2, "NAO_DETERMINADA": 3}

# Conflitos da Fase 4 -> (modulo, chave da tabela de prioridade).
# DUPLICIDADE_DA_MESMA_SUBSTANCIA nao esta aqui de proposito: o motor de
# horarios nao conhece listas de conciliacao e marca duplicidade sempre que a
# mesma substancia se repete — inclusive quando ela se repete porque esta na
# prescricao E no relato, que e justamente um item CONCILIADO. O modulo 8
# deste arquivo refaz a verificacao com consciencia de lista.
DA_AGENDA = {
    "JEJUM_PROXIMO_DE_REFEICAO": "CONFLITO_HORARIO",
    "ALIMENTO_EXIGIDO_SEM_REFEICAO_PROXIMA": "CONFLITO_HORARIO",
    "SEPARACAO_NAO_RESPEITADA": "CONFLITO_HORARIO",
    "SEPARACAO_COM_INTERVALO_DESCONHECIDO": "CONFLITO_HORARIO",
    "HORARIO_FORA_DA_ROTINA": "CONFLITO_HORARIO",
    "FREQUENCIA_INCOMPATIVEL_COM_HORARIOS": "POSOLOGIA",
    "INTERVALO_ENTRE_DOSES_MENOR_QUE_O_DECLARADO": "POSOLOGIA",
    "REGRAS_DE_ALIMENTACAO_CONFLITANTES": "REGRA_ADMINISTRACAO",
}
CHAVE_POSOLOGIA = {
    "FREQUENCIA_INCOMPATIVEL_COM_HORARIOS": "FREQUENCIA_INCOMPATIVEL",
    "INTERVALO_ENTRE_DOSES_MENOR_QUE_O_DECLARADO": "INTERVALO_MENOR_QUE_O_DECLARADO",
}


# =====================================================================
# ESTRUTURAS
# =====================================================================
@dataclass
class Evidencia:
    """Uma fonte que sustenta (ou contradiz) o achado.

    Existe para que agrupar dois achados no mesmo alerta nunca signifique
    perder a evidencia do que foi absorvido.
    """
    papel: str                       # PRINCIPAL | CORROBORA | DIVERGE
    fonte: str
    origem_afirmacao: str            # 'tabela.id'
    tipo_fonte: Optional[str] = None
    confiabilidade_fonte: Optional[str] = None
    documento: Optional[str] = None
    trecho: Optional[str] = None
    gravidade_declarada: Optional[str] = None
    mecanismo: Optional[str] = None
    efeito_esperado: Optional[str] = None
    conduta: Optional[str] = None
    descricao_original: Optional[str] = None
    nivel_evidencia: Optional[str] = None
    metodo_extracao: Optional[str] = None
    confianca_extracao: Optional[str] = None


@dataclass
class Achado:
    """A unidade de saida do sistema.

    Os nomes seguem a especificacao: `tipo` e o modulo que produziu o achado,
    `subtipo` a especializacao dentro dele.

    `grupo_chave` identifica o PROBLEMA, nunca a linha que o revelou. Nenhuma
    chave pode conter id de `atendimento_medicamento`: chave presa a linha faz
    o mesmo problema virar dois grupos quando o paciente traz marca e generico
    do mesmo principio ativo, e faz o agrupamento depender de quem foi
    cadastrado primeiro. O teste de monotonicidade da verificacao 2 encontrou
    exatamente isso.
    """
    tipo: str                        # = modulo
    subtipo: str
    titulo: str
    item_a: str
    explicacao: str
    justificativa_prioridade: str
    grupo_chave: str

    atendimento_id: Optional[int] = None
    paciente: Optional[str] = None

    prioridade: str = "INFORMATIVO"
    classificacao: str = "CONFIRMADO"
    natureza: str = "DOCUMENTADO"

    substancia_a_id: Optional[int] = None
    item_b: Optional[str] = None
    substancia_b_id: Optional[int] = None
    alvo_tipo: str = "NENHUM"

    mecanismo: Optional[str] = None
    efeito_esperado: Optional[str] = None
    conduta: Optional[str] = None
    descricao_fonte: Optional[str] = None

    gravidade_fonte: Optional[str] = None
    nivel_evidencia: Optional[str] = None
    confianca_sistema: str = "MEDIA"
    confianca_extracao: str = "NAO_APLICAVEL"
    status_informacao: str = "DOCUMENTADO"
    origem_achado: str = "REGRA"
    metodo_deteccao: str = "REGRA_DETERMINISTICA"
    probabilidade_modelo: Optional[float] = None
    origem_afirmacao: str = ""
    fonte: Optional[str] = None
    documento: Optional[str] = None
    trecho: Optional[str] = None
    conflito_tipo: Optional[str] = None

    contexto_paciente: Optional[str] = None
    requer_revisao_profissional: int = 1

    status: str = "PRINCIPAL"
    agrupado_em: Optional[str] = None    # grupo_chave do representante
    evidencias: list = field(default_factory=list)

    def por_que_apareceu(self) -> str:
        """A cadeia de evidencia e regra, em uma frase por elo.

        E o que a especificacao pede em 'transparencia do raciocinio': nao o
        raciocinio interno, e sim os fatos e a regra que sustentam o achado.
        """
        elos = []
        if self.contexto_paciente:
            elos.append("Contexto do paciente: %s" % self.contexto_paciente)
        elos.append("Detecção: %s (módulo %s / %s)"
                    % (self.metodo_deteccao, self.tipo, self.subtipo))
        for e in self.evidencias:
            elos.append("Fonte %s (%s) — %s%s"
                        % (e.fonte, e.papel,
                           e.origem_afirmacao,
                           "; gravidade declarada: %s" % e.gravidade_declarada
                           if e.gravidade_declarada else ""))
        elos.append("Prioridade %s: %s" % (self.prioridade,
                                           self.justificativa_prioridade))
        return "\n".join(elos)


@dataclass
class ParConciliado:
    """Resultado do pareamento entre a lista prescrita e a relatada."""
    nome_exibicao: str
    situacao: str
    substancia_id: Optional[int] = None
    item_prescrito_id: Optional[int] = None
    item_relatado_id: Optional[int] = None
    tipo_divergencia: Optional[str] = None
    valor_prescrito: Optional[str] = None
    valor_relatado: Optional[str] = None
    detalhe: Optional[str] = None
    # O sistema calcula a SITUACAO. A INTENCAO e ato clinico assinado.
    intencionalidade: str = "NAO_DETERMINADA"


@dataclass
class NaoAvaliado:
    item: str
    motivo: str
    modulo: Optional[str] = None
    detalhe: str = ""


@dataclass
class ResultadoConciliacao:
    atendimento_id: int
    versao_motor: str
    paciente: Optional[str] = None
    resumo: dict = field(default_factory=dict)
    achados: list = field(default_factory=list)
    achados_agrupados: list = field(default_factory=list)
    pares: list = field(default_factory=list)
    conflitos: list = field(default_factory=list)
    nao_avaliado: list = field(default_factory=list)
    limitacoes: list = field(default_factory=list)
    indicadores: dict = field(default_factory=dict)
    agenda: object = None
    conciliacao_id: Optional[int] = None

    @property
    def divergencias(self):
        return [p for p in self.pares if p.situacao != "CONCILIADO"]

    @property
    def conciliados(self):
        return [p for p in self.pares if p.situacao == "CONCILIADO"]

    @property
    def nao_conciliados(self):
        return [p for p in self.pares
                if p.situacao in ("INFORMACAO_INSUFICIENTE", "REVISAO_NECESSARIA")]


# =====================================================================
# CONTEXTO DO PACIENTE
# =====================================================================
@dataclass
class Medicamento:
    am_id: int
    nome_relatado: str
    substancia_id: Optional[int]
    nome_dcb: Optional[str]
    origem: str
    lista: str
    reconhecimento: str
    atc: Optional[str] = None
    dose_valor: Optional[float] = None
    dose_unidade: Optional[str] = None
    vezes_por_dia: Optional[int] = None
    intervalo_horas: Optional[float] = None
    via: Optional[str] = None
    data_fim_prevista: Optional[str] = None
    uso_continuo: int = 0
    se_necessario: int = 0
    tem_posologia: bool = False
    horarios: tuple = ()

    @property
    def rotulo(self) -> str:
        if self.nome_dcb and self.nome_dcb.lower() not in self.nome_relatado.lower():
            return "%s (%s)" % (self.nome_relatado, self.nome_dcb)
        return self.nome_relatado

    def dose_texto(self) -> Optional[str]:
        if self.dose_valor is None:
            return None
        return "%g %s" % (self.dose_valor, self.dose_unidade or "")

    def frequencia_texto(self) -> Optional[str]:
        if self.vezes_por_dia:
            return "%dx/dia" % self.vezes_por_dia
        if self.intervalo_horas:
            return "a cada %g h" % self.intervalo_horas
        return None


@dataclass
class Contexto:
    con: object
    atendimento_id: int
    paciente_id: int
    paciente_nome: str
    idade: Optional[int]
    sexo: Optional[str]
    medicamentos: list = field(default_factory=list)
    condicoes: list = field(default_factory=list)     # (doenca_id, nome, livre)
    alergias: list = field(default_factory=list)
    habitos: dict = field(default_factory=dict)
    itens: list = field(default_factory=list)

    def ativos(self):
        return [m for m in self.medicamentos if m.lista in LISTAS_ATIVAS]

    def substancias_ativas(self) -> dict:
        """substancia_id -> [Medicamento]. Ignora o que nao foi reconhecido."""
        d = defaultdict(list)
        for m in self.ativos():
            if m.substancia_id:
                d[m.substancia_id].append(m)
        return d

    def frase_contexto(self, extra=None) -> str:
        partes = []
        if self.idade is not None:
            partes.append("%d anos" % self.idade)
        if self.sexo and self.sexo not in ("NAO_INFORMADO",):
            partes.append({"F": "sexo feminino", "M": "sexo masculino"}
                          .get(self.sexo, self.sexo))
        partes.append("%d medicamento(s) em uso" % len(self.ativos()))
        if self.condicoes:
            partes.append("condições: " + ", ".join(
                sorted({c[1] or c[2] for c in self.condicoes})))
        if extra:
            partes.append(extra)
        return "; ".join(p for p in partes if p)


def _idade(nascimento: Optional[str]) -> Optional[int]:
    if not nascimento:
        return None
    try:
        d = _dt.date.fromisoformat(nascimento[:10])
    except ValueError:
        return None
    hoje = _dt.date.today()
    return hoje.year - d.year - ((hoje.month, hoje.day) < (d.month, d.day))


def _carregar_contexto(con, atendimento_id: int) -> Optional[Contexto]:
    linha = con.execute(
        "SELECT p.id, p.nome, p.data_nascimento, p.sexo FROM atendimento a "
        "JOIN paciente p ON p.id = a.paciente_id WHERE a.id=?",
        (atendimento_id,)).fetchone()
    if linha is None:
        return None
    pid, nome, nasc, sexo = linha
    ctx = Contexto(con=con, atendimento_id=atendimento_id, paciente_id=pid,
                   paciente_nome=nome, idade=_idade(nasc), sexo=sexo)

    for (am_id, nome_rel, sid, dcb, origem, lista, rec, atc, dose, unid,
         vezes, intervalo, via, fim, continuo, prn, pos_id) in con.execute(
            "SELECT am.id, am.nome_relatado, am.substancia_id, s.nome_dcb, "
            "am.origem, am.lista, am.reconhecimento, s.atc_codigo, "
            "po.dose_valor, po.dose_unidade, po.vezes_por_dia, "
            "po.intervalo_horas, po.via_administracao, po.data_fim_prevista, "
            "po.uso_continuo, po.se_necessario, po.id "
            "FROM atendimento_medicamento am "
            "LEFT JOIN substancia s ON s.id = am.substancia_id "
            "LEFT JOIN posologia po ON po.atendimento_medicamento_id = am.id "
            "WHERE am.atendimento_id=? ORDER BY am.id", (atendimento_id,)):
        horarios = ()
        if pos_id:
            horarios = tuple(h for (h,) in con.execute(
                "SELECT hora FROM horario_administracao WHERE posologia_id=? "
                "ORDER BY hora", (pos_id,)))
        ctx.medicamentos.append(Medicamento(
            am_id=am_id, nome_relatado=nome_rel, substancia_id=sid,
            nome_dcb=dcb, origem=origem, lista=lista, reconhecimento=rec,
            atc=atc, dose_valor=dose, dose_unidade=unid, vezes_por_dia=vezes,
            intervalo_horas=intervalo, via=via, data_fim_prevista=fim,
            uso_continuo=continuo or 0, se_necessario=prn or 0,
            tem_posologia=pos_id is not None, horarios=horarios))

    ctx.condicoes = list(con.execute(
        "SELECT pc.doenca_id, d.nome, pc.descricao_livre FROM paciente_condicao pc "
        "LEFT JOIN doenca d ON d.id = pc.doenca_id WHERE pc.paciente_id=?",
        (pid,)))
    ctx.alergias = list(con.execute(
        "SELECT pa.substancia_id, s.nome_dcb, s.atc_codigo, pa.descricao_livre, "
        "pa.reacao, pa.gravidade FROM paciente_alergia pa "
        "LEFT JOIN substancia s ON s.id = pa.substancia_id WHERE pa.paciente_id=?",
        (pid,)))
    ctx.habitos = {h: (sit, qtd, freq) for h, sit, qtd, freq in con.execute(
        "SELECT habito, situacao, quantidade, frequencia FROM paciente_habito "
        "WHERE paciente_id=?", (pid,))}
    ctx.itens = list(con.execute(
        "SELECT ai.item_id, i.nome, i.tipo, ai.nome_relatado, ai.frequencia, "
        "ai.horario_habitual FROM atendimento_item ai "
        "LEFT JOIN item_nao_medicamentoso i ON i.id = ai.item_id "
        "WHERE ai.atendimento_id=?", (atendimento_id,)))
    return ctx


# =====================================================================
# AJUDANTES DE MONTAGEM
# =====================================================================
def _fonte_info(con, fonte_id: int) -> tuple:
    r = con.execute("SELECT nome, tipo, confiabilidade FROM fonte WHERE id=?",
                    (fonte_id,)).fetchone()
    return r if r else ("(fonte desconhecida)", None, None)


def _evidencia_da_tabela(con, tabela: str, id_alvo: int) -> tuple:
    """(nivel_evidencia, metodo_extracao, documento, trecho) da tabela evidencia."""
    r = con.execute(
        "SELECT nivel_evidencia, metodo_extracao, documento, trecho FROM evidencia "
        "WHERE tabela_alvo=? AND id_alvo=? LIMIT 1", (tabela, id_alvo)).fetchone()
    return r if r else (None, None, None, None)


def _confianca_extracao(metodo: str, status_revisao: str) -> str:
    if status_revisao == "APROVADO":
        return "REVISADA"
    if metodo in ("CARGA_DIRETA", "CURADORIA_HUMANA"):
        return "CARGA_DIRETA"
    if metodo in ("REGEX", "NLP"):
        return "EXTRAIDA_AUTOMATICAMENTE"
    return "NAO_APLICAVEL"


def _status_informacao(confianca_extracao: str, natureza: str) -> str:
    """Traduz o par (como foi lido, o que se sabe) para o vocabulario da
    especificacao. PREVISTO e EXTRAIDO_AUTOMATICAMENTE nunca viram
    DOCUMENTADO ou REVISADO por este caminho."""
    if natureza == "PREVISTO":
        return "PREVISTO"
    if confianca_extracao == "REVISADA":
        return "REVISADO"
    if confianca_extracao == "EXTRAIDA_AUTOMATICAMENTE":
        return "EXTRAIDO_AUTOMATICAMENTE"
    if natureza in ("POSSIVEL", "PROVAVEL"):
        return "EXTRAIDO_AUTOMATICAMENTE" if confianca_extracao == \
            "EXTRAIDA_AUTOMATICAMENTE" else "DOCUMENTADO"
    if natureza == "DESCONHECIDO":
        return "NAO_DETERMINADO"
    return "DOCUMENTADO"


def _finalizar(ach: Achado, *, chave_prioridade: str, anafilaxia=False,
               item_declarado=True) -> Achado:
    """Calcula confianca e prioridade e fecha o achado.

    Ponto unico: nenhum modulo escreve prioridade na mao.
    """
    ach.confianca_sistema = prio.melhor_confianca(
        [prio.confianca(e.confianca_extracao or ach.confianca_extracao,
                        e.nivel_evidencia, e.confiabilidade_fonte, ach.natureza)
         for e in ach.evidencias] or
        [prio.confianca(ach.confianca_extracao, ach.nivel_evidencia,
                        None, ach.natureza)])
    ach.prioridade, ach.justificativa_prioridade = prio.calcular(
        ach.tipo, chave_prioridade,
        confianca_sistema=ach.confianca_sistema,
        classificacao=ach.classificacao,
        anafilaxia=anafilaxia, item_declarado=item_declarado)
    ach.status_informacao = _status_informacao(ach.confianca_extracao,
                                               ach.natureza)
    if ach.natureza == "DOCUMENTADO" and not ach.nivel_evidencia:
        ach.nivel_evidencia = "NAO_AVALIADA"
    # Revisao profissional: exigida sempre, exceto no que e pura orientacao
    # de administracao ja repassavel como esta.
    ach.requer_revisao_profissional = 0 if (
        ach.tipo == "REGRA_ADMINISTRACAO" and ach.subtipo == "ORIENTACAO"
        and ach.confianca_sistema != "BAIXA") else 1
    return ach


# =====================================================================
# MODULO 1 — FARMACO x FARMACO
# =====================================================================
def _modulo_farmaco_farmaco(ctx: Contexto, achados: list, nao_aval: list):
    con = ctx.con
    subs = ctx.substancias_ativas()
    ids = sorted(subs)

    # Cobertura: a substancia esta no mapa de interacoes do sistema?
    for sid in ids:
        n = con.execute(
            "SELECT COUNT(*) FROM interacao_substancia WHERE substancia_a_id=? "
            "OR substancia_b_id=?", (sid, sid)).fetchone()[0]
        if n == 0:
            nao_aval.append(NaoAvaliado(
                item=subs[sid][0].rotulo, motivo="SUBSTANCIA_SEM_COBERTURA",
                modulo="FARMACO_FARMACO",
                detalhe="Nenhuma fonte do acervo registra interação para esta "
                        "substância. Ausência de alerta aqui NÃO é ausência de "
                        "risco: é ausência de dado."))

    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            linhas = list(con.execute(
                "SELECT i.id, i.tipo, i.mecanismo, i.efeito_esperado, "
                "i.descricao_original, i.gravidade, i.conduta, i.fonte_id, "
                "i.status_revisao FROM vw_interacao_liberada i "
                "WHERE i.substancia_a_id=? AND i.substancia_b_id=?", (a, b)))
            nome_a = subs[a][0].rotulo
            nome_b = subs[b][0].rotulo
            if not linhas:
                nao_aval.append(NaoAvaliado(
                    item="%s × %s" % (nome_a, nome_b),
                    motivo="SEM_INTERACAO_CONHECIDA", modulo="FARMACO_FARMACO",
                    detalhe="O par foi verificado e nenhuma fonte do acervo "
                            "registra interação entre os dois. Isso não afirma "
                            "que a associação é segura."))
                continue
            ach = _achado_interacao(ctx, a, b, nome_a, nome_b, linhas)
            achados.append(ach)
            if ach.gravidade_fonte == "NAO_DETERMINADA":
                nao_aval.append(NaoAvaliado(
                    item="%s × %s" % (nome_a, nome_b),
                    motivo="GRAVIDADE_NAO_GRADUADA_NA_FONTE",
                    modulo="FARMACO_FARMACO",
                    detalhe="A interação está documentada, mas nenhuma das %d "
                            "fonte(s) que a afirmam graduou a gravidade. O "
                            "sistema não gradua no lugar delas."
                            % len(ach.evidencias)))


def _achado_interacao(ctx, a, b, nome_a, nome_b, linhas) -> Achado:
    """Um achado por PAR, uma evidencia por FONTE.

    Duas fontes afirmando o mesmo par nao viram dois alertas — viram um alerta
    com duas evidencias. Se elas discordarem da gravidade, o achado sai
    CONFLITANTE e nenhuma das duas e escolhida em silencio.
    """
    con = ctx.con
    ach = Achado(
        tipo="FARMACO_FARMACO", subtipo="INTERACAO_DOCUMENTADA",
        titulo="Interação entre %s e %s" % (nome_a, nome_b),
        item_a=nome_a, item_b=nome_b, substancia_a_id=a, substancia_b_id=b,
        alvo_tipo="SUBSTANCIA", grupo_chave="PAR:%d-%d" % (a, b),
        explicacao="", justificativa_prioridade="",
        atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
        metodo_deteccao="CRUZAMENTO_DE_PARES_NA_FARMACOTERAPIA",
        contexto_paciente=ctx.frase_contexto(
            "os dois itens estão na farmacoterapia atual"))

    graves, textos, originais, condutas, mecanismos = [], [], [], [], []
    for (iid, tipo, mecanismo, efeito, original, gravidade, conduta,
         fonte_id, status_rev) in linhas:
        nome_f, tipo_f, conf_f = _fonte_info(con, fonte_id)
        nivel, metodo, doc, trecho = _evidencia_da_tabela(
            con, "interacao_substancia", iid)
        ce = _confianca_extracao(metodo, status_rev)
        ach.evidencias.append(Evidencia(
            papel="PRINCIPAL", fonte=nome_f, tipo_fonte=tipo_f,
            confiabilidade_fonte=conf_f,
            origem_afirmacao="interacao_substancia.%d" % iid,
            documento=doc, trecho=trecho, gravidade_declarada=gravidade,
            mecanismo=mecanismo, efeito_esperado=efeito, conduta=conduta,
            descricao_original=original, nivel_evidencia=nivel,
            metodo_extracao=metodo, confianca_extracao=ce))
        graves.append(gravidade)
        if efeito:
            textos.append(efeito)
        if original:
            originais.append(original)
        if conduta:
            condutas.append(conduta)
        if mecanismo:
            mecanismos.append(mecanismo)
        if tipo and tipo != "NAO_DETERMINADO" and not ach.subtipo.startswith("INTER"):
            pass
        if tipo == "FARMACOCINETICA":
            ach.subtipo = "INTERACAO_FARMACOCINETICA"
        elif tipo == "FARMACODINAMICA" and ach.subtipo != "INTERACAO_FARMACOCINETICA":
            ach.subtipo = "INTERACAO_FARMACODINAMICA"

    declaradas = {g for g in graves if g != "NAO_DETERMINADA"}
    if len(declaradas) > 1:
        # Duas fontes graduam diferente. O sistema NAO escolhe: declara o
        # conflito e adota a MAIS GRAVE para ordenar, porque escolher a mais
        # branda em silencio seria a unica opcao com risco assimetrico.
        ach.natureza = "CONFLITANTE"
        ach.conflito_tipo = "GRAVIDADE"
        ach.classificacao = "CONFLITO_ENTRE_FONTES"
        for e in ach.evidencias:
            if e.gravidade_declarada != "NAO_DETERMINADA":
                e.papel = "DIVERGE"
        ach.gravidade_fonte = sorted(declaradas, key=lambda g: ORDEM_GRAVIDADE[g])[0]
    elif declaradas:
        ach.gravidade_fonte = declaradas.pop()
    else:
        ach.gravidade_fonte = "NAO_DETERMINADA"

    ach.efeito_esperado = textos[0] if textos else None
    ach.descricao_fonte = originais[0] if originais else None
    ach.mecanismo = mecanismos[0] if mecanismos else None
    ach.conduta = condutas[0] if condutas else None
    ach.nivel_evidencia = next((e.nivel_evidencia for e in ach.evidencias
                                if e.nivel_evidencia), "NAO_AVALIADA")
    ach.confianca_extracao = min(
        (e.confianca_extracao for e in ach.evidencias),
        key=lambda c: ["REVISADA", "CARGA_DIRETA", "EXTRAIDA_AUTOMATICAMENTE",
                       "CALCULADO", "NAO_APLICAVEL"].index(c))
    ach.fonte = " / ".join(sorted({e.fonte for e in ach.evidencias}))
    ach.origem_afirmacao = ach.evidencias[0].origem_afirmacao
    ach.documento = ach.evidencias[0].documento
    ach.trecho = ach.evidencias[0].trecho

    partes = ["%s e %s estão na farmacoterapia atual do paciente."
              % (nome_a, nome_b)]
    partes.append("%d fonte(s) do acervo registram interação entre os dois: %s."
                  % (len(ach.evidencias), ach.fonte))
    if ach.natureza == "CONFLITANTE":
        partes.append("AS FONTES DISCORDAM da gravidade (%s). Nenhuma foi "
                      "adotada como verdadeira; a ordenação usa a mais grave e "
                      "as duas leituras aparecem na evidência."
                      % " × ".join("%s: %s" % (e.fonte, e.gravidade_declarada)
                                   for e in ach.evidencias
                                   if e.papel == "DIVERGE"))
    if ach.gravidade_fonte == "NAO_DETERMINADA":
        partes.append("NENHUMA fonte graduou a gravidade deste par. O sistema "
                      "não atribui gravidade por conta própria.")
    if not ach.efeito_esperado and not ach.descricao_fonte:
        partes.append("A fonte que registra este par não publica descrição do "
                      "efeito — a ausência de texto é da fonte, não uma falha "
                      "de leitura.")
    ach.explicacao = " ".join(partes)

    chave = ("NAO_DETERMINADA" if ach.gravidade_fonte == "NAO_DETERMINADA"
             else ach.gravidade_fonte)
    _finalizar(ach, chave_prioridade=chave)
    if ach.gravidade_fonte == "NAO_DETERMINADA":
        ach.status_informacao = "NAO_DETERMINADO"
    return ach


# =====================================================================
# MODULO 13 — INTERACAO PREVISTA POR MODELO  (Fase 8)
# =====================================================================
# COMO ESTE MODULO NAO QUEBRA A ARQUITETURA
# -----------------------------------------
# Ele NAO importa nada de `ml/`, nao carrega scikit-learn e nao roda modelo
# nenhum. O modelo escreve em `predicao`; o motor le uma VIEW, do mesmo jeito
# que le `vw_interacao_liberada`. A camada de regras continua sem dependencia
# de ML, e o executavel da Fase 10 continua sem precisar de sklearn para
# conciliar.
#
# AS QUATRO TRAVAS ESTAO NA VIEW, NAO AQUI
# ----------------------------------------
# `vw_predicao_liberada` so devolve linha quando o modelo esta ATIVO e
# HOMOLOGADO, declarou `limiar_alerta`, a probabilidade calibrada atinge esse
# limiar, e **o par nao tem interacao documentada**. A ultima e a garantia
# estrutural de que previsao nunca substitui, contradiz nem duplica evidencia:
# onde ha documento, o achado vem do documento e a previsao nem aparece.
#
# Hoje nenhum modelo esta ativo (D-041), a view devolve zero linhas e este
# modulo nao produz nada — o comportamento em producao e identico ao de antes
# de existir ML. Isso e o desejado, e o teste de regressao trava.

def _ha_modelo_ativo(con) -> bool:
    return con.execute(
        "SELECT COUNT(*) FROM modelo WHERE ativo=1 AND status='HOMOLOGADO' "
        "AND limiar_alerta IS NOT NULL").fetchone()[0] > 0


def _modulo_interacao_prevista(ctx: Contexto, achados: list, nao_aval: list):
    con = ctx.con
    if not _ha_modelo_ativo(con):
        return              # sem modelo homologado o modulo inteiro se cala

    subs = ctx.substancias_ativas()
    ids = sorted(subs)
    documentados = set()
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if con.execute("SELECT 1 FROM vw_interacao_liberada WHERE "
                           "substancia_a_id=? AND substancia_b_id=? LIMIT 1",
                           (a, b)).fetchone():
                documentados.add((a, b))
                continue
            linha = con.execute(
                "SELECT predicao_id, probabilidade, probabilidade_calibrada, "
                "probabilidade_exibida, explicacao_json, criado_em, "
                "status_predicao, revisado_por, modelo_nome, modelo_versao, "
                "algoritmo, n_features, limiar_alerta, limitacoes, "
                "versao_dados, semente FROM vw_predicao_liberada "
                "WHERE substancia_a_id=? AND substancia_b_id=?", (a, b)
            ).fetchone()
            nome_a, nome_b = subs[a][0].rotulo, subs[b][0].rotulo
            if linha is None:
                # O par nao foi pontuado por este modelo. Declarar e obrigatorio:
                # o farmaceutico precisa saber que a ausencia de linha prevista
                # nao e o modelo dizendo "nao interage".
                nao_aval.append(NaoAvaliado(
                    item="%s × %s" % (nome_a, nome_b),
                    motivo="PAR_NAO_PONTUADO_PELO_MODELO",
                    modulo="FARMACO_FARMACO",
                    detalhe="O modelo ativo não pontuou este par, ou a "
                            "probabilidade ficou abaixo do limiar de alerta. "
                            "Isso NÃO é o modelo afirmando que não há "
                            "interação."))
                continue
            achados.append(_achado_previsto(ctx, a, b, nome_a, nome_b, linha))


def _achado_previsto(ctx, a, b, nome_a, nome_b, r) -> Achado:
    """Monta o achado PREVISTO com a rastreabilidade inteira.

    Sem `Evidencia`, e de proposito: previsao NAO TEM evidencia documental, e a
    ausencia tem de aparecer. `achado_evidencia` continua sendo o que o nome
    diz — fontes. A rastreabilidade vai por `origem_afirmacao='predicao.<id>'`,
    de onde se chega a modelo, versao, semente, versao dos dados,
    probabilidade, explicacao e data.
    """
    (pid, prob, prob_cal, prob_exib, expl_json, criado_em, status_pred,
     revisado_por, modelo, versao, algoritmo, n_feat, limiar, limitacoes,
     versao_dados, semente) = r

    fatores = _fatores_em_portugues(expl_json)
    partes = [
        "NÃO HÁ INTERAÇÃO DOCUMENTADA entre %s e %s em nenhuma fonte do "
        "acervo." % (nome_a, nome_b),
        "Esta linha é uma PREVISÃO estatística: o modelo estima "
        "probabilidade %s de que o par esteja documentado em alguma base — "
        "não estima gravidade nem risco."
        % prio.percentual_previsao(prob_exib),
        "Modelo %s versão %s (%s, %d atributos), limiar de alerta %.2f, "
        "semente %s, dados %s." % (modelo, versao, algoritmo, n_feat, limiar,
                                   semente, versao_dados),
    ]
    if fatores:
        partes.append("O que o modelo pesou: %s." % "; ".join(fatores))
        partes.append("Esses fatores descrevem o que o MODELO VIU, não um "
                      "mecanismo farmacológico.")
    if status_pred != "NAO_REVISADA":
        partes.append("Previsão %s por %s."
                      % ("aceita" if status_pred == "REVISADA_ACEITA"
                         else "recusada", revisado_por))
    partes.append("Requer verificação em fonte antes de qualquer conduta.")

    ach = Achado(
        tipo="FARMACO_FARMACO", subtipo="INTERACAO_PREVISTA",
        titulo="Possível interação prevista entre %s e %s" % (nome_a, nome_b),
        item_a=nome_a, item_b=nome_b, substancia_a_id=a, substancia_b_id=b,
        alvo_tipo="SUBSTANCIA",
        # Chave PREVISTA:, distinta de PAR: — um par previsto e um par
        # documentado nunca se agrupam no mesmo alerta.
        grupo_chave="PREVISTA:%d-%d" % (a, b),
        explicacao=" ".join(partes), justificativa_prioridade="",
        atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
        classificacao="POSSIVEL",
        natureza="PREVISTO",
        gravidade_fonte=None,          # o modelo nao gradua. Nunca.
        nivel_evidencia=None,          # previsao nao tem nivel de evidencia
        confianca_extracao="CALCULADO",
        origem_achado="MODELO",
        probabilidade_modelo=float(prob_exib),
        origem_afirmacao="predicao.%d" % pid,
        metodo_deteccao="MODELO_%s_%s" % (modelo, versao),
        fonte=None, documento=None, trecho=None,
        contexto_paciente="%s e %s em uso concomitante" % (nome_a, nome_b),
    )
    return _finalizar(ach, chave_prioridade="PREVISTA")


def _fatores_em_portugues(expl_json: Optional[str], k: int = 3) -> list:
    """Le a contribuicao aproximada gravada com a previsao.

    Formato tolerante de proposito: se o JSON mudar de forma, o achado sai sem
    a lista de fatores em vez de quebrar a conciliacao inteira.
    """
    if not expl_json:
        return []
    try:
        itens = json.loads(expl_json)
    except (ValueError, TypeError):
        return []
    saida = []
    for it in itens[:k]:
        if not isinstance(it, dict) or "atributo" not in it:
            continue
        nome = str(it["atributo"])
        efeito = it.get("efeito")
        sentido = ("aumentou" if isinstance(efeito, (int, float)) and efeito > 0
                   else "reduziu")
        saida.append("%s (%s a estimativa)" % (nome, sentido))
    return saida


# =====================================================================
# MODULO 2 e 10 — FARMACO x DOENCA / CONTRAINDICACAO
# =====================================================================
def _modulo_farmaco_doenca(ctx: Contexto, achados: list, nao_aval: list):
    con = ctx.con
    subs = ctx.substancias_ativas()
    condicoes = [(did, nome) for did, nome, _livre in ctx.condicoes if did]

    for _did, _nome, livre in ctx.condicoes:
        if _did is None and livre:
            nao_aval.append(NaoAvaliado(
                item=livre, motivo="CONDICAO_NAO_RECONHECIDA",
                modulo="FARMACO_DOENCA",
                detalhe="Condição registrada em texto livre, sem vínculo com o "
                        "cadastro de doenças. Nenhum medicamento pôde ser "
                        "verificado contra ela."))
    if not condicoes:
        return

    for sid, meds in subs.items():
        tem_alguma = con.execute(
            "SELECT COUNT(*) FROM interacao_doenca WHERE substancia_id=?",
            (sid,)).fetchone()[0]
        if not tem_alguma:
            nao_aval.append(NaoAvaliado(
                item=meds[0].rotulo, motivo="SUBSTANCIA_SEM_COBERTURA",
                modulo="FARMACO_DOENCA",
                detalhe="Nenhuma bula do acervo registra contraindicação desta "
                        "substância. A cobertura do módulo é de 102 substâncias."))
            continue
        for did, nome_doenca in condicoes:
            linhas = list(con.execute(
                "SELECT id, relacao, justificativa, trecho_origem, gravidade, "
                "fonte_id, status_revisao FROM vw_interacao_doenca_liberada "
                "WHERE substancia_id=? AND doenca_id=?", (sid, did)))
            for (iid, relacao, justif, trecho, gravidade, fonte_id,
                 status_rev) in linhas:
                if relacao == "INDICADO":
                    continue        # e o tratamento, nao um problema
                nome_f, tipo_f, conf_f = _fonte_info(con, fonte_id)
                nivel, metodo, doc, _t = _evidencia_da_tabela(
                    con, "interacao_doenca", iid)
                ce = _confianca_extracao(metodo, status_rev)
                titulo = ("Contraindicação" if relacao == "CONTRAINDICADO"
                          else "Precaução") + " — %s na presença de %s" % (
                              meds[0].rotulo, nome_doenca)
                ach = Achado(
                    tipo="FARMACO_DOENCA", subtipo=relacao, titulo=titulo,
                    item_a=meds[0].rotulo, item_b=nome_doenca,
                    substancia_a_id=sid, alvo_tipo="DOENCA",
                    grupo_chave="DOENCA:%d-%d" % (sid, did),
                    gravidade_fonte=gravidade, nivel_evidencia=nivel,
                    confianca_extracao=ce, natureza="POSSIVEL"
                    if ce == "EXTRAIDA_AUTOMATICAMENTE" else "DOCUMENTADO",
                    metodo_deteccao="CONDICAO_DECLARADA_x_CONTRAINDICACAO_DA_BULA",
                    fonte=nome_f, documento=doc, trecho=trecho,
                    origem_afirmacao="interacao_doenca.%d" % iid,
                    atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
                    contexto_paciente=ctx.frase_contexto(
                        "o paciente declarou %s" % nome_doenca),
                    explicacao="", justificativa_prioridade="")
                ach.evidencias.append(Evidencia(
                    papel="PRINCIPAL", fonte=nome_f, tipo_fonte=tipo_f,
                    confiabilidade_fonte=conf_f,
                    origem_afirmacao="interacao_doenca.%d" % iid,
                    documento=doc, trecho=trecho, gravidade_declarada=gravidade,
                    nivel_evidencia=nivel, metodo_extracao=metodo,
                    confianca_extracao=ce))
                ach.explicacao = (
                    "O paciente declarou %s. A bula de %s, registrada na "
                    "ANVISA, %s nessa condição. O trecho literal que sustenta "
                    "a leitura está na evidência.%s"
                    % (nome_doenca, meds[0].rotulo,
                       "declara contraindicação" if relacao == "CONTRAINDICADO"
                       else "pede cautela",
                       " A leitura foi feita por expressão regular e ainda NÃO "
                       "passou por revisão farmacêutica."
                       if ce == "EXTRAIDA_AUTOMATICAMENTE" else ""))
                achados.append(_finalizar(ach, chave_prioridade=relacao))


# =====================================================================
# MODULO 3 — FARMACO x ALERGIA
# =====================================================================
def _modulo_alergia(ctx: Contexto, achados: list, nao_aval: list):
    subs = ctx.substancias_ativas()
    for (a_sid, a_nome, a_atc, livre, reacao, gravidade) in ctx.alergias:
        anafilaxia = gravidade == "ANAFILAXIA"
        if a_sid is None:
            nao_aval.append(NaoAvaliado(
                item=livre or "(alergia sem descrição)",
                motivo="ALERGIA_NAO_RECONHECIDA", modulo="FARMACO_ALERGIA",
                detalhe="A alergia foi registrada em texto livre e não pôde ser "
                        "ligada a uma substância do cadastro: nenhum "
                        "medicamento foi verificado contra ela."))
            ach = Achado(
                tipo="FARMACO_ALERGIA", subtipo="ALERGIA_SEM_VINCULO",
                titulo="Alergia declarada não verificável: %s" % (livre or "?"),
                item_a=livre or "(alergia sem descrição)", alvo_tipo="ALERGIA",
                grupo_chave="ALERGIA_LIVRE:%s" % (livre or "?"),
                classificacao="INFORMACAO_INSUFICIENTE", natureza="DESCONHECIDO",
                confianca_extracao="NAO_APLICAVEL",
                metodo_deteccao="LEITURA_DA_ANAMNESE",
                origem_afirmacao="paciente_alergia.livre",
                atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
                contexto_paciente=ctx.frase_contexto(),
                explicacao="O paciente relatou alergia a %r, mas o texto não "
                           "casa com nenhuma substância do cadastro. O sistema "
                           "não verificou a farmacoterapia contra esta alergia "
                           "e declara isso em vez de omitir." % (livre or ""),
                justificativa_prioridade="")
            achados.append(_finalizar(ach, chave_prioridade="ALERGIA_SEM_VINCULO"))
            continue

        for sid, meds in subs.items():
            m = meds[0]
            if sid == a_sid:
                subtipo, alvo = "SUBSTANCIA_EXATA", a_nome
                explic = ("O paciente declarou alergia a %s e %s está na "
                          "farmacoterapia: é a mesma substância." % (a_nome, m.rotulo))
                natureza = "DOCUMENTADO"
            elif (a_atc and m.atc and len(a_atc) >= 5 and len(m.atc) >= 5
                  and a_atc[:5] == m.atc[:5]):
                subtipo, alvo = "MESMA_CLASSE_ATC", a_nome
                explic = ("O paciente declarou alergia a %s. %s pertence à "
                          "mesma classe ATC de 4º nível (%s). Reatividade "
                          "cruzada é POSSÍVEL — a classificação ATC agrupa por "
                          "química e finalidade, não é uma tabela de "
                          "reatividade cruzada, e nenhuma fonte do acervo "
                          "estabelece essa relação."
                          % (a_nome, m.rotulo, a_atc[:5]))
                natureza = "POSSIVEL"
            else:
                continue
            ach = Achado(
                tipo="FARMACO_ALERGIA", subtipo=subtipo,
                titulo="Alergia declarada a %s × %s em uso" % (alvo, m.rotulo),
                item_a=m.rotulo, item_b=alvo, substancia_a_id=sid,
                substancia_b_id=a_sid, alvo_tipo="ALERGIA",
                grupo_chave="ALERGIA:%d-%d" % (sid, a_sid),
                natureza=natureza, nivel_evidencia="NAO_AVALIADA",
                confianca_extracao="CALCULADO",
                metodo_deteccao="ALERGIA_DA_ANAMNESE_x_FARMACOTERAPIA",
                origem_afirmacao="paciente_alergia.%d" % a_sid,
                fonte="Anamnese do paciente",
                atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
                contexto_paciente=ctx.frase_contexto(
                    "alergia relatada: %s%s%s" % (
                        a_nome, "; reação: %s" % reacao if reacao else "",
                        "; gravidade: %s" % gravidade if gravidade else "")),
                explicacao=explic, justificativa_prioridade="",
                conduta="Confirmar a alergia com o paciente antes de qualquer "
                        "dispensação. A decisão é do profissional.")
            ach.evidencias.append(Evidencia(
                papel="PRINCIPAL", fonte="Anamnese do paciente",
                tipo_fonte="CURADORIA", confiabilidade_fonte="ALTA",
                origem_afirmacao="paciente_alergia.%d" % a_sid,
                trecho=reacao, nivel_evidencia="NAO_AVALIADA",
                metodo_extracao="CURADORIA_HUMANA",
                confianca_extracao="CALCULADO"))
            achados.append(_finalizar(ach, chave_prioridade=subtipo,
                                      anafilaxia=anafilaxia))


# =====================================================================
# MODULOS 4, 5 e 6 — ALIMENTO, PLANTA E SUPLEMENTO
# =====================================================================
def _modulo_item(ctx: Contexto, achados: list, nao_aval: list):
    con = ctx.con
    subs = ctx.substancias_ativas()
    declarados = {}
    for item_id, nome_item, tipo_item, nome_rel, freq, horario in ctx.itens:
        if item_id is None:
            nao_aval.append(NaoAvaliado(
                item=nome_rel, motivo="ITEM_NAO_RECONHECIDO",
                modulo="FARMACO_ALIMENTO",
                detalhe="Item relatado pelo paciente sem vínculo com o cadastro "
                        "de itens não medicamentosos: não foi verificado."))
            continue
        declarados[item_id] = (nome_item or nome_rel, freq, horario)

    for sid, meds in subs.items():
        m = meds[0]
        for (iid, item_id, nome_item, tipo_item, mecanismo, efeito, original,
             gravidade, conduta, fonte_id, status_rev) in con.execute(
                "SELECT ii.id, ii.item_id, i.nome, i.tipo, ii.mecanismo, "
                "ii.efeito_esperado, ii.descricao_original, ii.gravidade, "
                "ii.conduta, ii.fonte_id, ii.status_revisao "
                "FROM vw_interacao_item_liberada ii "
                "JOIN item_nao_medicamentoso i ON i.id = ii.item_id "
                "WHERE ii.substancia_id=?", (sid,)):
            modulo = MODULO_POR_TIPO_ITEM.get(tipo_item, "FARMACO_ALIMENTO")
            declarado = item_id in declarados
            nome_f, tipo_f, conf_f = _fonte_info(con, fonte_id)
            nivel, metodo, doc, trecho = _evidencia_da_tabela(
                con, "interacao_item", iid)
            ce = _confianca_extracao(metodo, status_rev)
            ach = Achado(
                tipo=modulo,
                subtipo="ITEM_EM_USO" if declarado else "ORIENTACAO_PREVENTIVA",
                titulo="%s × %s" % (m.rotulo, nome_item),
                item_a=m.rotulo, item_b=nome_item, substancia_a_id=sid,
                alvo_tipo="ITEM", grupo_chave="ITEM:%d-%d" % (sid, item_id),
                gravidade_fonte=gravidade, nivel_evidencia=nivel,
                confianca_extracao=ce, natureza="DOCUMENTADO",
                mecanismo=mecanismo, efeito_esperado=efeito,
                descricao_fonte=original, conduta=conduta,
                metodo_deteccao="ITEM_DECLARADO_x_INTERACAO" if declarado
                else "COBERTURA_DE_ITEM_SEM_RELATO_DO_PACIENTE",
                fonte=nome_f, documento=doc, trecho=trecho,
                origem_afirmacao="interacao_item.%d" % iid,
                atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
                contexto_paciente=ctx.frase_contexto(
                    "o paciente declarou usar %s (%s)"
                    % (declarados[item_id][0], declarados[item_id][1] or
                       "frequência não informada") if declarado
                    else "o paciente NÃO declarou usar %s" % nome_item),
                explicacao="", justificativa_prioridade="")
            ach.evidencias.append(Evidencia(
                papel="PRINCIPAL", fonte=nome_f, tipo_fonte=tipo_f,
                confiabilidade_fonte=conf_f,
                origem_afirmacao="interacao_item.%d" % iid, documento=doc,
                trecho=trecho, gravidade_declarada=gravidade,
                mecanismo=mecanismo, efeito_esperado=efeito, conduta=conduta,
                descricao_original=original, nivel_evidencia=nivel,
                metodo_extracao=metodo, confianca_extracao=ce))
            ach.explicacao = (
                "%s interage com %s segundo %s.%s"
                % (m.rotulo, nome_item, nome_f,
                   " O paciente declarou usar este item, então a interação é "
                   "atual." if declarado else
                   " O paciente NÃO declarou usar este item: isto é orientação "
                   "preventiva a repassar, não alerta sobre uso atual."))
            achados.append(_finalizar(
                ach, chave_prioridade=gravidade, item_declarado=declarado))


# =====================================================================
# MODULO 7 — FARMACO x HABITO
# =====================================================================
def _modulo_habito(ctx: Contexto, achados: list, nao_aval: list):
    con = ctx.con
    subs = ctx.substancias_ativas()
    habitos_com_regra = {h for (h,) in con.execute(
        "SELECT DISTINCT habito FROM interacao_habito")}
    for h in sorted(habitos_com_regra):
        sit = ctx.habitos.get(h, (None,))[0]
        if sit is None or sit == "NAO_INFORMADO":
            nao_aval.append(NaoAvaliado(
                item=NOME_HABITO.get(h, h), motivo="HABITO_NAO_INFORMADO",
                modulo="FARMACO_HABITO",
                detalhe="O paciente não informou se tem o hábito de %s. O "
                        "acervo tem regras para ele, e elas não puderam ser "
                        "aplicadas." % NOME_HABITO.get(h, h)))

    for sid, meds in subs.items():
        m = meds[0]
        for (iid, habito, mecanismo, efeito, gravidade, conduta, cessacao,
             fonte_id, status_rev) in con.execute(
                "SELECT id, habito, mecanismo, efeito_esperado, gravidade, "
                "conduta, alerta_cessacao, fonte_id, status_revisao "
                "FROM vw_interacao_habito_liberada WHERE substancia_id=?", (sid,)):
            sit = ctx.habitos.get(habito, (None, None, None))[0]
            if sit not in ("ATUAL", "EX"):
                continue
            nome_f, tipo_f, conf_f = _fonte_info(con, fonte_id)
            nivel, metodo, doc, trecho = _evidencia_da_tabela(
                con, "interacao_habito", iid)
            ce = _confianca_extracao(metodo, status_rev)
            atual = sit == "ATUAL"
            ach = Achado(
                tipo="FARMACO_HABITO",
                subtipo="HABITO_ATUAL" if atual else "HABITO_ANTERIOR",
                titulo="%s × %s" % (m.rotulo, NOME_HABITO.get(habito, habito)),
                item_a=m.rotulo, item_b=NOME_HABITO.get(habito, habito),
                substancia_a_id=sid, alvo_tipo="HABITO",
                grupo_chave="HABITO:%d-%s" % (sid, habito),
                gravidade_fonte=gravidade, nivel_evidencia=nivel,
                confianca_extracao=ce, natureza="DOCUMENTADO",
                classificacao="CONFIRMADO" if atual else "POSSIVEL",
                mecanismo=mecanismo, efeito_esperado=efeito,
                conduta=conduta or cessacao,
                metodo_deteccao="HABITO_DA_ANAMNESE_x_INTERACAO",
                fonte=nome_f, documento=doc, trecho=trecho,
                origem_afirmacao="interacao_habito.%d" % iid,
                atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
                contexto_paciente=ctx.frase_contexto(
                    "hábito %s: %s" % (NOME_HABITO.get(habito, habito), sit)),
                explicacao="", justificativa_prioridade="")
            ach.evidencias.append(Evidencia(
                papel="PRINCIPAL", fonte=nome_f, tipo_fonte=tipo_f,
                confiabilidade_fonte=conf_f,
                origem_afirmacao="interacao_habito.%d" % iid, documento=doc,
                trecho=trecho, gravidade_declarada=gravidade,
                mecanismo=mecanismo, efeito_esperado=efeito,
                conduta=conduta, nivel_evidencia=nivel, metodo_extracao=metodo,
                confianca_extracao=ce))
            ach.explicacao = (
                "O paciente declarou %s como %s e usa %s. %s%s"
                % (NOME_HABITO.get(habito, habito), sit.lower(), m.rotulo,
                   nome_f + " registra interação entre os dois.",
                   " Como o hábito é anterior, o achado fica como possível."
                   if not atual else ""))
            achados.append(_finalizar(
                ach, chave_prioridade=gravidade if atual else "NAO_DETERMINADA"))


# =====================================================================
# MODULO 7b — FARMACO x CYP (inferencia mecanistica)
# =====================================================================
def _modulo_cyp(ctx: Contexto, achados: list, nao_aval: list):
    """Inibidor/indutor de uma enzima x substrato da MESMA enzima.

    Isto NAO e interacao documentada: e deducao a partir de dois fatos
    documentados. Sai sempre com natureza POSSIVEL e nunca acima de MODERADO.
    Quando o par ja tem interacao documentada, o agrupamento transforma este
    achado em evidencia que EXPLICA o mecanismo do outro.
    """
    con = ctx.con
    subs = ctx.substancias_ativas()
    ids = sorted(subs)
    if len(ids) < 2:
        return
    papeis = defaultdict(list)
    marca = ",".join("?" * len(ids))
    for sid, sistema, papel, potencia, fonte_id, pid in con.execute(
            "SELECT substancia_id, sistema, papel, potencia, fonte_id, id "
            "FROM papel_farmacocinetico WHERE substancia_id IN (%s)" % marca, ids):
        papeis[sid].append((sistema, papel, potencia, fonte_id, pid))

    for a in ids:
        for b in ids:
            if a == b:
                continue
            for sistema, papel, potencia, fonte_id, pid in papeis.get(a, []):
                if papel not in ("INIBIDOR", "INDUTOR"):
                    continue
                for sis2, papel2, pot2, fonte2, pid2 in papeis.get(b, []):
                    if sis2 != sistema or papel2 != "SUBSTRATO":
                        continue
                    par = (min(a, b), max(a, b))
                    nome_a, nome_b = subs[a][0].rotulo, subs[b][0].rotulo
                    nome_f, tipo_f, conf_f = _fonte_info(con, fonte_id)
                    efeito = ("A exposição a %s tende a AUMENTAR." % nome_b
                              if papel == "INIBIDOR"
                              else "A exposição a %s tende a DIMINUIR." % nome_b)
                    ach = Achado(
                        tipo="FARMACO_CYP", subtipo="%s_%s" % (papel, sistema),
                        titulo="Possível interação por %s: %s (%s %s) × %s "
                               "(substrato)" % (sistema, nome_a, papel.lower(),
                                                potencia.lower(), nome_b),
                        item_a=nome_a, item_b=nome_b, substancia_a_id=a,
                        substancia_b_id=b, alvo_tipo="ENZIMA",
                        grupo_chave="PAR:%d-%d" % par,
                        natureza="POSSIVEL", classificacao="POSSIVEL",
                        gravidade_fonte="NAO_DETERMINADA",
                        nivel_evidencia="TEORICA", confianca_extracao="CARGA_DIRETA",
                        mecanismo="%s é %s %s de %s; %s é substrato de %s."
                                  % (nome_a, papel.lower(), potencia.lower(),
                                     sistema, nome_b, sistema),
                        efeito_esperado=efeito,
                        metodo_deteccao="INFERENCIA_MECANISTICA_POR_ENZIMA",
                        fonte=nome_f, origem_afirmacao="papel_farmacocinetico.%d" % pid,
                        atendimento_id=ctx.atendimento_id,
                        paciente=ctx.paciente_nome,
                        contexto_paciente=ctx.frase_contexto(
                            "os dois estão na farmacoterapia atual"),
                        explicacao=(
                            "Nenhuma fonte afirma esta interação diretamente. O "
                            "sistema a DEDUZIU de dois fatos publicados pela "
                            "FDA: %s é %s %s de %s, e %s é substrato dessa "
                            "mesma enzima. Dedução não é observação — o achado "
                            "sai como POSSÍVEL e exige confirmação."
                            % (nome_a, papel.lower(), potencia.lower(), sistema,
                               nome_b)),
                        justificativa_prioridade="")
                    for origem, ident in (("papel_farmacocinetico.%d" % pid, fonte_id),
                                          ("papel_farmacocinetico.%d" % pid2, fonte2)):
                        f_nome, f_tipo, f_conf = _fonte_info(con, ident)
                        nivel, metodo, doc, trecho = _evidencia_da_tabela(
                            con, "papel_farmacocinetico",
                            int(origem.split(".")[1]))
                        ach.evidencias.append(Evidencia(
                            papel="PRINCIPAL", fonte=f_nome, tipo_fonte=f_tipo,
                            confiabilidade_fonte=f_conf, origem_afirmacao=origem,
                            documento=doc, trecho=trecho,
                            nivel_evidencia=nivel, metodo_extracao=metodo,
                            confianca_extracao="CARGA_DIRETA"))
                    achados.append(_finalizar(ach, chave_prioridade=potencia))


# =====================================================================
# MODULO 8 — DUPLICIDADE TERAPEUTICA
# =====================================================================
def _modulo_duplicidade(ctx: Contexto, achados: list, nao_aval: list):
    """Duplicidade com consciencia de lista.

    A mesma substancia na prescricao E no relato NAO e duplicidade: e um item
    conciliado, e contar como duplicidade seria transformar o acerto da
    conciliacao em alerta. Duplicidade e a mesma substancia repetida DENTRO da
    mesma lista, ou duas substancias distintas do mesmo 5o nivel ATC.
    """
    por_lista = defaultdict(lambda: defaultdict(list))
    for m in ctx.ativos():
        if m.substancia_id:
            por_lista[m.lista][m.substancia_id].append(m)

    vistos = set()
    for lista, mapa in por_lista.items():
        for sid, meds in mapa.items():
            if len(meds) < 2 or sid in vistos:
                continue
            vistos.add(sid)
            nomes = sorted({m.rotulo for m in meds})
            ach = Achado(
                tipo="DUPLICIDADE", subtipo="MESMA_SUBSTANCIA",
                titulo="Duplicidade: %s aparece %d vezes na lista %s"
                       % (meds[0].nome_dcb or meds[0].nome_relatado,
                          len(meds), lista),
                item_a=nomes[0], item_b=", ".join(nomes[1:]),
                substancia_a_id=sid, alvo_tipo="SUBSTANCIA",
                grupo_chave="DUP:%d" % sid, natureza="DOCUMENTADO",
                nivel_evidencia="NAO_AVALIADA", confianca_extracao="CALCULADO",
                metodo_deteccao="CONTAGEM_DE_SUBSTANCIA_NA_MESMA_LISTA",
                fonte="Farmacoterapia do atendimento",
                origem_afirmacao="atendimento_medicamento.%s"
                                 % ",".join(str(m.am_id) for m in meds),
                atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
                contexto_paciente=ctx.frase_contexto(),
                explicacao="%s aparece em %d itens da lista %s (%s). Pode ser "
                           "marca e genérico do mesmo princípio ativo, ou "
                           "associação intencional — o sistema aponta, não "
                           "decide." % (meds[0].nome_dcb or nomes[0], len(meds),
                                        lista, ", ".join(nomes)),
                justificativa_prioridade="",
                conduta="Conferir com o paciente se as duas apresentações estão "
                        "realmente em uso simultâneo.")
            achados.append(_finalizar(ach, chave_prioridade="MESMA_SUBSTANCIA"))

    # Classe ATC de 4o NIVEL (5 caracteres): substancias distintas, mesmo
    # subgrupo quimico-terapeutico. O 5o nivel NAO serve aqui: ele identifica
    # a propria substancia, e medindo no banco ha ZERO grupos de 5o nivel com
    # duas substancias diferentes — a regra escrita no 5o nivel seria letra
    # morta. No 4o nivel ha 248 grupos, e sao os clinicamente certos: dois
    # inibidores da bomba de protons, dois inibidores da ECA, duas estatinas.
    por_atc = defaultdict(list)
    for m in ctx.ativos():
        if m.substancia_id and m.atc and len(m.atc) >= 5:
            por_atc[m.atc[:5]].append(m)
    for atc, meds in por_atc.items():
        distintas = {m.substancia_id for m in meds}
        if len(distintas) < 2:
            continue
        nomes = sorted({m.rotulo for m in meds})
        nome_classe = ctx.con.execute(
            "SELECT nome_pt FROM classe_atc WHERE codigo=?", (atc,)).fetchone()
        ach = Achado(
            tipo="DUPLICIDADE", subtipo="MESMA_CLASSE_ATC4",
            titulo="Duplicidade terapêutica: %s" % ", ".join(nomes),
            item_a=nomes[0], item_b=", ".join(nomes[1:]),
            alvo_tipo="CLASSE_ATC",
            grupo_chave="DUPATC:%s" % atc, natureza="DOCUMENTADO",
            nivel_evidencia="RESPALDADA", confianca_extracao="CARGA_DIRETA",
            metodo_deteccao="AGRUPAMENTO_POR_5o_NIVEL_ATC",
            fonte="WHO - ATC/DDD",
            origem_afirmacao="classe_atc.%s" % atc,
            atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
            contexto_paciente=ctx.frase_contexto(),
            explicacao="%s pertencem ao mesmo 4º nível da classificação ATC "
                       "(%s — %s), ou seja, ao mesmo subgrupo "
                       "químico-terapêutico. Terapia combinada da mesma classe "
                       "pode ser intencional. O sistema guarda UM código ATC "
                       "por substância; substâncias com mais de uma indicação "
                       "podem ficar fora deste agrupamento."
                       % (" e ".join(nomes), atc,
                          nome_classe[0] if nome_classe else atc),
            justificativa_prioridade="")
        achados.append(_finalizar(ach, chave_prioridade="MESMA_CLASSE_ATC4"))


# =====================================================================
# MODULOS 9 e 11 — o que vem do motor da Fase 4
# =====================================================================
def _da_agenda(ctx: Contexto, agenda, achados: list, nao_aval: list):
    """Converte a saida do motor de horarios em achados.

    Nao reimplementa nenhuma regra temporal: le `agenda.conflitos`,
    `agenda.eventos` e `agenda.nao_avaliado` e traduz.
    """
    for c in agenda.conflitos:
        modulo = DA_AGENDA.get(c.tipo)
        if modulo is None:
            continue        # DUPLICIDADE_DA_MESMA_SUBSTANCIA: modulo 8 refaz
        if modulo == "POSOLOGIA":
            chave = CHAVE_POSOLOGIA[c.tipo]
            natureza, conflito_tipo, classificacao = "DOCUMENTADO", None, (
                "CONFIRMADO" if c.classificacao == "CONFLITO_CONFIRMADO"
                else "INFORMACAO_INSUFICIENTE")
        elif modulo == "REGRA_ADMINISTRACAO":
            chave = "FONTES_CONFLITANTES"
            natureza, conflito_tipo = "CONFLITANTE", "RELACAO_ALIMENTO"
            classificacao = "CONFLITO_ENTRE_FONTES"
        else:
            chave = c.classificacao
            natureza = ("DOCUMENTADO" if c.classificacao == "CONFLITO_CONFIRMADO"
                        else "POSSIVEL" if c.classificacao == "POSSIVEL_CONFLITO"
                        else "DESCONHECIDO")
            conflito_tipo = None
            classificacao = {"CONFLITO_CONFIRMADO": "CONFIRMADO",
                             "POSSIVEL_CONFLITO": "POSSIVEL",
                             "REGRA_DESCONHECIDA": "REGRA_DESCONHECIDA",
                             "INFORMACAO_INSUFICIENTE": "INFORMACAO_INSUFICIENTE"
                             }.get(c.classificacao, "POSSIVEL")
        ce = c.confianca_extracao or "CALCULADO"
        if ce == "REVISADA":
            ce_norm = "REVISADA"
        elif ce == "CARGA_DIRETA":
            ce_norm = "CARGA_DIRETA"
        elif ce == "EXTRAIDA_AUTOMATICAMENTE":
            ce_norm = "EXTRAIDA_AUTOMATICAMENTE"
        else:
            ce_norm = "CALCULADO"
        detalhe = []
        if c.intervalo_exigido is not None:
            detalhe.append("intervalo exigido %g h" % c.intervalo_exigido)
        if c.intervalo_observado is not None:
            detalhe.append("observado %g h" % c.intervalo_observado)
        ach = Achado(
            tipo=modulo, subtipo=c.tipo,
            titulo="%s — %s" % (c.tipo.replace("_", " ").capitalize(),
                                " × ".join(c.itens)),
            item_a=c.itens[0] if c.itens else "(item)",
            item_b=" × ".join(c.itens[1:]) if len(c.itens) > 1 else None,
            alvo_tipo="POSOLOGIA" if modulo == "POSOLOGIA" else "SUBSTANCIA",
            grupo_chave="AGENDA:%s:%s" % (c.tipo, "|".join(sorted(c.itens))),
            natureza=natureza, classificacao=classificacao,
            conflito_tipo=conflito_tipo,
            gravidade_fonte="NAO_DETERMINADA",
            nivel_evidencia="NAO_AVALIADA" if natureza == "DOCUMENTADO" else None,
            confianca_extracao=ce_norm,
            metodo_deteccao="MOTOR_DE_HORARIOS_DA_FASE_4",
            fonte=c.fonte or "Motor de horários (cálculo sobre dados do paciente)",
            origem_afirmacao="agenda.conflito:%s" % c.tipo,
            atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
            contexto_paciente=ctx.frase_contexto(
                "horários envolvidos: %s" % ", ".join(c.horarios)
                if c.horarios else None),
            explicacao=c.justificativa + (
                " (%s)" % "; ".join(detalhe) if detalhe else ""),
            justificativa_prioridade="")
        ach.evidencias.append(Evidencia(
            papel="PRINCIPAL",
            fonte=c.fonte or "Motor de horários",
            origem_afirmacao="agenda.conflito:%s" % c.tipo,
            trecho=c.justificativa,
            nivel_evidencia="NAO_AVALIADA",
            metodo_extracao="CARGA_DIRETA",
            confianca_extracao=ce_norm))
        achados.append(_finalizar(ach, chave_prioridade=chave))

    for na in agenda.nao_avaliado:
        nao_aval.append(NaoAvaliado(item=na.item, motivo=na.motivo,
                                    modulo="CONFLITO_HORARIO",
                                    detalhe=na.detalhe))

    # Orientacoes de administracao: nao sao problema, sao o que repassar.
    # Uma por SUBSTANCIA. Marca e generico do mesmo principio ativo dariam
    # dois cartoes identicos de "como tomar", que e exatamente a duplicidade
    # visual que a especificacao manda evitar.
    por_substancia = {m.am_id: m.substancia_id for m in ctx.medicamentos}
    vistos = set()
    for ev in agenda.eventos:
        chave_adm = (por_substancia.get(ev.atendimento_medicamento_id)
                     or ("am:%d" % ev.atendimento_medicamento_id))
        if not ev.orientacao or chave_adm in vistos:
            continue
        vistos.add(chave_adm)
        ce = ev.confianca_extracao or "CALCULADO"
        ce_norm = ("EXTRAIDA_AUTOMATICAMENTE"
                   if ce == "EXTRAIDA_AUTOMATICAMENTE"
                   else "CARGA_DIRETA" if ce == "CARGA_DIRETA"
                   else "REVISADA" if ce == "REVISADA" else "CALCULADO")
        ach = Achado(
            tipo="REGRA_ADMINISTRACAO", subtipo="ORIENTACAO",
            titulo="Como tomar: %s" % ev.medicamento,
            item_a=ev.medicamento, alvo_tipo="NENHUM",
            substancia_a_id=por_substancia.get(ev.atendimento_medicamento_id),
            grupo_chave="ADM:%s" % chave_adm,
            natureza="DOCUMENTADO", nivel_evidencia="NAO_AVALIADA",
            confianca_extracao=ce_norm, conduta=ev.orientacao,
            metodo_deteccao="REGRA_DE_ADMINISTRACAO_DA_FONTE",
            fonte=ev.fonte_regra,
            origem_afirmacao="regra_administracao/%s" % (ev.regra_administracao or "-"),
            atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
            contexto_paciente=ctx.frase_contexto(),
            explicacao="A fonte %s estabelece uma regra de administração (%s) "
                       "para %s. É orientação a repassar ao paciente, não "
                       "problema detectado."
                       % (ev.fonte_regra, ev.regra_administracao, ev.medicamento),
            justificativa_prioridade="")
        ach.evidencias.append(Evidencia(
            papel="PRINCIPAL", fonte=ev.fonte_regra or "(fonte não informada)",
            origem_afirmacao=ach.origem_afirmacao, trecho=ev.orientacao,
            nivel_evidencia="NAO_AVALIADA", confianca_extracao=ce_norm))
        achados.append(_finalizar(ach, chave_prioridade="ORIENTACAO"))

    # Dose ausente: comum no balcao e declarado, nunca silenciado.
    for m in ctx.ativos():
        if m.tem_posologia and m.dose_valor is None:
            ach = Achado(
                tipo="POSOLOGIA", subtipo="DOSE_NAO_INFORMADA",
                titulo="Dose não informada: %s" % m.rotulo,
                item_a=m.rotulo, substancia_a_id=m.substancia_id,
                alvo_tipo="POSOLOGIA",
                grupo_chave="DOSE:%s" % (m.substancia_id or m.nome_relatado),
                natureza="DESCONHECIDO",
                classificacao="INFORMACAO_INSUFICIENTE",
                confianca_extracao="CALCULADO",
                metodo_deteccao="LEITURA_DA_POSOLOGIA",
                fonte="Anamnese do paciente",
                origem_afirmacao="posologia.am%d" % m.am_id,
                atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
                contexto_paciente=ctx.frase_contexto(),
                explicacao="A dose de %s não foi informada. É comum no balcão — "
                           "o paciente muitas vezes não sabe. A agenda foi "
                           "montada, mas a dose não pôde ser conferida."
                           % m.rotulo,
                justificativa_prioridade="")
            achados.append(_finalizar(ach, chave_prioridade="DOSE_NAO_INFORMADA"))
            nao_aval.append(NaoAvaliado(
                item=m.rotulo, motivo="DOSE_NAO_INFORMADA", modulo="POSOLOGIA",
                detalhe="Sem dose registrada, nenhuma verificação de dose foi "
                        "feita para este item."))


# =====================================================================
# CONCILIACAO PROPRIAMENTE DITA
# =====================================================================
def _texto_horarios(m: Medicamento) -> Optional[str]:
    return ", ".join(m.horarios) if m.horarios else None


def _reconciliar(ctx: Contexto, achados: list, nao_aval: list) -> list:
    """Pareia a lista PRESCRITA com a RELATADA/EM_USO.

    Diferenca nao e erro. O sistema classifica a SITUACAO e nunca a INTENCAO.
    """
    pares = []
    prescritos = [m for m in ctx.medicamentos if m.lista == "PRESCRITA"]
    relatados = [m for m in ctx.medicamentos if m.lista in ("RELATADA", "EM_USO")]
    passados = [m for m in ctx.medicamentos if m.lista in LISTAS_PASSADAS]

    for m in ctx.medicamentos:
        if m.substancia_id is None:
            pares.append(ParConciliado(
                nome_exibicao=m.nome_relatado, situacao="REVISAO_NECESSARIA",
                tipo_divergencia="SEM_CORRESPONDENCIA",
                item_prescrito_id=m.am_id if m.lista == "PRESCRITA" else None,
                item_relatado_id=m.am_id if m.lista != "PRESCRITA" else None,
                detalhe="O item não pôde ser ligado a nenhuma substância do "
                        "cadastro (%s), então não pôde ser conciliado com "
                        "segurança." % m.reconhecimento))
            _achado_divergencia(ctx, pares[-1], achados)

    if not prescritos:
        # Sem prescricao apresentada nao existe divergencia a apurar: existe
        # ausencia de uma das listas. Dizer "so no relato" para tudo seria
        # inventar 20 divergencias num atendimento de balcao comum.
        nao_aval.append(NaoAvaliado(
            item="(lista prescrita)", motivo="SEM_CORRESPONDENCIA_ENTRE_LISTAS",
            modulo="DIVERGENCIA_CONCILIACAO",
            detalhe="Nenhum medicamento foi registrado na lista PRESCRITA. Sem "
                    "as duas listas não há conciliação a fazer: o que existe é "
                    "a farmacoterapia relatada, analisada normalmente pelos "
                    "demais módulos."))
        return pares

    por_sub_pres = defaultdict(list)
    por_sub_rel = defaultdict(list)
    for m in prescritos:
        if m.substancia_id:
            por_sub_pres[m.substancia_id].append(m)
    for m in relatados:
        if m.substancia_id:
            por_sub_rel[m.substancia_id].append(m)
    subs_passadas = {m.substancia_id for m in passados if m.substancia_id}

    for sid in sorted(set(por_sub_pres) | set(por_sub_rel)):
        p = por_sub_pres.get(sid, [])
        r = por_sub_rel.get(sid, [])
        nome = (p or r)[0].nome_dcb or (p or r)[0].nome_relatado

        if p and not r:
            pares.append(ParConciliado(
                nome_exibicao=nome, situacao="DIVERGENCIA", substancia_id=sid,
                item_prescrito_id=p[0].am_id,
                tipo_divergencia="SO_NA_PRESCRICAO",
                valor_prescrito=p[0].rotulo,
                detalhe="Consta da prescrição e o paciente não relatou usar."))
            _achado_divergencia(ctx, pares[-1], achados)
            continue
        if r and not p:
            pares.append(ParConciliado(
                nome_exibicao=nome, situacao="DIVERGENCIA", substancia_id=sid,
                item_relatado_id=r[0].am_id, tipo_divergencia="SO_NO_RELATO",
                valor_relatado=r[0].rotulo,
                detalhe="O paciente relata usar e não consta da prescrição "
                        "apresentada (origem declarada: %s)." % r[0].origem))
            _achado_divergencia(ctx, pares[-1], achados)
            continue

        mp, mr = p[0], r[0]
        if sid in subs_passadas:
            pares.append(ParConciliado(
                nome_exibicao=nome, situacao="DIVERGENCIA", substancia_id=sid,
                item_prescrito_id=mp.am_id, item_relatado_id=mr.am_id,
                tipo_divergencia="DESCONTINUADO_EM_USO",
                detalhe="A substância consta também de lista de uso anterior e "
                        "o paciente relata continuar usando."))
            _achado_divergencia(ctx, pares[-1], achados)
            continue

        if not mp.tem_posologia or not mr.tem_posologia:
            pares.append(ParConciliado(
                nome_exibicao=nome, situacao="INFORMACAO_INSUFICIENTE",
                substancia_id=sid, item_prescrito_id=mp.am_id,
                item_relatado_id=mr.am_id,
                tipo_divergencia="POSOLOGIA_INSUFICIENTE",
                detalhe="Falta posologia estruturada em um dos lados: não há o "
                        "que comparar. Ausência não é divergência."))
            _achado_divergencia(ctx, pares[-1], achados)
            continue

        diferencas = []
        for rotulo, tipo, va, vb in (
                ("dose", "DOSE_DIFERENTE", mp.dose_texto(), mr.dose_texto()),
                ("frequência", "FREQUENCIA_DIFERENTE",
                 mp.frequencia_texto(), mr.frequencia_texto()),
                ("via", "VIA_DIFERENTE", mp.via, mr.via),
                ("horário", "HORARIO_DIFERENTE",
                 _texto_horarios(mp), _texto_horarios(mr))):
            if va is None or vb is None:
                continue
            if str(va).strip().lower() != str(vb).strip().lower():
                diferencas.append((rotulo, tipo, va, vb))

        if not diferencas:
            pares.append(ParConciliado(
                nome_exibicao=nome, situacao="CONCILIADO", substancia_id=sid,
                item_prescrito_id=mp.am_id, item_relatado_id=mr.am_id,
                detalhe="Prescrição e relato coincidem em dose, frequência, via "
                        "e horário — no que foi informado dos dois lados."))
            continue

        for rotulo, tipo, va, vb in diferencas:
            pares.append(ParConciliado(
                nome_exibicao=nome, situacao="DIVERGENCIA", substancia_id=sid,
                item_prescrito_id=mp.am_id, item_relatado_id=mr.am_id,
                tipo_divergencia=tipo, valor_prescrito=str(va),
                valor_relatado=str(vb),
                detalhe="A %s prescrita (%s) difere da relatada (%s). Diferença "
                        "não é erro: pode ser ajuste posterior. A "
                        "intencionalidade só pode ser decidida por um "
                        "profissional." % (rotulo, va, vb)))
            _achado_divergencia(ctx, pares[-1], achados)

    return pares


def _achado_divergencia(ctx: Contexto, par: ParConciliado, achados: list):
    chave = par.tipo_divergencia or "SEM_CORRESPONDENCIA"
    classificacao = ("INFORMACAO_INSUFICIENTE"
                     if par.situacao in ("INFORMACAO_INSUFICIENTE",
                                         "REVISAO_NECESSARIA")
                     else "CONFIRMADO")
    ach = Achado(
        tipo="DIVERGENCIA_CONCILIACAO", subtipo=chave,
        titulo="Divergência de conciliação: %s (%s)"
               % (par.nome_exibicao, chave.replace("_", " ").lower()),
        item_a=par.nome_exibicao,
        item_b=("prescrito: %s | relatado: %s" % (par.valor_prescrito,
                                                  par.valor_relatado)
                if par.valor_prescrito or par.valor_relatado else None),
        substancia_a_id=par.substancia_id, alvo_tipo="LISTA",
        grupo_chave="DIV:%s:%s" % (chave, par.substancia_id or par.nome_exibicao),
        natureza="DESCONHECIDO" if classificacao == "INFORMACAO_INSUFICIENTE"
                 else "DOCUMENTADO",
        classificacao=classificacao,
        nivel_evidencia="NAO_AVALIADA",
        confianca_extracao="CALCULADO",
        metodo_deteccao="DIFF_ENTRE_LISTA_PRESCRITA_E_RELATADA",
        fonte="Listas do atendimento",
        origem_afirmacao="conciliacao_par.%s" % chave,
        atendimento_id=ctx.atendimento_id, paciente=ctx.paciente_nome,
        contexto_paciente=ctx.frase_contexto(),
        explicacao=(par.detalhe or "") + " O sistema classifica a situação; a "
                   "intencionalidade permanece NÃO DETERMINADA até que um "
                   "profissional identificado a registre.",
        justificativa_prioridade="")
    ach.evidencias.append(Evidencia(
        papel="PRINCIPAL", fonte="Listas do atendimento",
        origem_afirmacao=ach.origem_afirmacao, trecho=par.detalhe,
        nivel_evidencia="NAO_AVALIADA", confianca_extracao="CALCULADO"))
    achados.append(_finalizar(ach, chave_prioridade=chave))


# =====================================================================
# AGRUPAMENTO E DEDUPLICACAO
# =====================================================================
_ORDEM = {p: i for i, p in enumerate(prio.ESCALA)}
_ORDEM_CONF = {"ALTA": 0, "MEDIA": 1, "BAIXA": 2}


def _agrupar(achados: list) -> tuple:
    """Um problema, um alerta — e nenhuma evidencia perdida.

    Achados que compartilham `grupo_chave` viram um so na lista principal. O
    escolhido recebe as evidencias dos demais (papel CORROBORA, ou DIVERGE
    quando a gravidade declarada diverge). Os absorvidos continuam existindo,
    com status AGRUPADO, e sao devolvidos a parte: reduzir alerta nunca pode
    apagar registro.
    """
    grupos = defaultdict(list)
    for a in achados:
        grupos[a.grupo_chave].append(a)

    principais, agrupados = [], []
    for chave, lista in grupos.items():
        if len(lista) == 1:
            principais.append(lista[0])
            continue
        # Representante: mais urgente; empate -> mais confiavel; empate ->
        # mais evidencias; empate -> titulo, para ser deterministico.
        lista.sort(key=lambda a: (_ORDEM[a.prioridade],
                                  _ORDEM_CONF.get(a.confianca_sistema, 3),
                                  -len(a.evidencias), a.titulo))
        rep, resto = lista[0], lista[1:]
        graves = {e.gravidade_declarada for a in lista for e in a.evidencias
                  if e.gravidade_declarada
                  and e.gravidade_declarada != "NAO_DETERMINADA"}
        for outro in resto:
            outro.status = "AGRUPADO"
            outro.agrupado_em = chave
            for e in outro.evidencias:
                if any(x.origem_afirmacao == e.origem_afirmacao
                       for x in rep.evidencias):
                    continue
                copia = Evidencia(**{**e.__dict__})
                copia.papel = ("DIVERGE" if (len(graves) > 1 and
                                             e.gravidade_declarada in graves)
                               else "CORROBORA")
                rep.evidencias.append(copia)
            agrupados.append(outro)
        rep.explicacao += (
            " Este achado agrupa %d detecção(ões) do mesmo problema por "
            "caminhos diferentes (%s); todas as evidências foram preservadas."
            % (len(resto), ", ".join(sorted({o.metodo_deteccao for o in resto}))))
        principais.append(rep)

    principais.sort(key=lambda a: (_ORDEM[a.prioridade],
                                   _ORDEM_CONF.get(a.confianca_sistema, 3),
                                   a.tipo, a.titulo))
    return principais, agrupados


# =====================================================================
# LIMITACOES E MODULOS SEM FONTE
# =====================================================================
def _declarar_modulos_sem_fonte(ctx: Contexto, nao_aval: list, limitacoes: list):
    """O que o sistema NAO avalia, dito antes que alguem pergunte."""
    con = ctx.con
    if not con.execute("SELECT COUNT(*) FROM substancia_reacao_adversa"
                       ).fetchone()[0]:
        nao_aval.append(NaoAvaliado(
            item="(módulo de reação adversa)", motivo="MODULO_SEM_FONTE_NO_ACERVO",
            modulo="REACAO_ADVERSA",
            detalhe="A camada de reação adversa (VigiMed) ainda não foi "
                    "carregada. Nenhum achado de reação adversa foi produzido "
                    "para este atendimento."))
        limitacoes.append(
            "Reação adversa não é avaliada: a base do VigiMed ainda não foi "
            "carregada (prevista para fase posterior, ver DECISIONS D-005).")
    nao_aval.append(NaoAvaliado(
        item="(módulo de medicamento × exame laboratorial)",
        motivo="MODULO_SEM_FONTE_NO_ACERVO", modulo="INFORMACAO_INSUFICIENTE",
        detalhe="Não existe fonte de interferência em exame laboratorial no "
                "acervo. O módulo está fora do escopo desta versão e é "
                "declarado, não silenciado."))
    if ctx.idade is not None and ctx.idade >= 65:
        nao_aval.append(NaoAvaliado(
            item="(critério de medicamento inadequado para idoso)",
            motivo="MODULO_SEM_FONTE_NO_ACERVO", modulo="INFORMACAO_INSUFICIENTE",
            detalhe="O paciente tem %d anos, mas nenhum instrumento de "
                    "inadequação em idoso (Beers, STOPP/START) está carregado. "
                    "A idade aparece no contexto dos achados e NÃO alterou "
                    "nenhuma prioridade." % ctx.idade))
        limitacoes.append(
            "Paciente com 65 anos ou mais e nenhum critério de inadequação "
            "geriátrica carregado: a idade não influencia a priorização.")


# =====================================================================
# PERSISTENCIA
# =====================================================================
def _persistir(con, res: ResultadoConciliacao) -> int:
    cur = con.execute(
        "INSERT INTO conciliacao (atendimento_id, versao_motor, n_medicamentos, "
        "n_achados, n_criticos, n_altos, n_moderados, n_baixos, n_informativos, "
        "n_divergencias, n_informacao_insuficiente, n_nao_avaliado, "
        "n_conciliados, n_nao_conciliados, requer_revisao_profissional) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (res.atendimento_id, res.versao_motor, res.resumo["medicamentos"],
         res.resumo["achados"], res.resumo["criticos"], res.resumo["altos"],
         res.resumo["moderados"], res.resumo["baixos"],
         res.resumo["informativos"], res.resumo["divergencias"],
         res.resumo["informacao_insuficiente"], res.resumo["nao_avaliado"],
         res.resumo["conciliados"], res.resumo["nao_conciliados"],
         1 if res.resumo["requer_revisao_profissional"] else 0))
    cid = cur.lastrowid

    ids_por_chave = {}
    for a in res.achados:
        ids_por_chave[a.grupo_chave] = _gravar_achado(con, cid, a, None)
    for a in res.achados_agrupados:
        _gravar_achado(con, cid, a, ids_por_chave.get(a.agrupado_em))

    for p in res.pares:
        con.execute(
            "INSERT INTO conciliacao_par (conciliacao_id, item_prescrito_id, "
            "item_relatado_id, substancia_id, nome_exibicao, situacao, "
            "tipo_divergencia, valor_prescrito, valor_relatado, detalhe, "
            "intencionalidade) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (cid, p.item_prescrito_id, p.item_relatado_id, p.substancia_id,
             p.nome_exibicao, p.situacao, p.tipo_divergencia, p.valor_prescrito,
             p.valor_relatado, p.detalhe, p.intencionalidade))
    for na in res.nao_avaliado:
        con.execute(
            "INSERT INTO nao_avaliado (conciliacao_id, item, motivo, modulo, "
            "detalhe) VALUES (?,?,?,?,?)",
            (cid, na.item, na.motivo, na.modulo, na.detalhe))
    return cid


def _gravar_achado(con, cid: int, a: Achado, agrupado_em: Optional[int]) -> int:
    cur = con.execute(
        "INSERT INTO achado (conciliacao_id, modulo, subtipo, prioridade, "
        "classificacao, natureza, item_a, substancia_a_id, item_b, "
        "substancia_b_id, alvo_tipo, titulo, mecanismo, efeito_esperado, "
        "conduta, descricao_fonte, explicacao, gravidade_fonte, nivel_evidencia, "
        "confianca_sistema, confianca_extracao, status_informacao, "
        "origem_achado, metodo_deteccao, probabilidade_modelo, origem_afirmacao, "
        "fonte, documento, trecho, conflito_tipo, contexto_paciente, "
        "justificativa_prioridade, requer_revisao_profissional, grupo_chave, "
        "status, agrupado_em) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, a.tipo, a.subtipo, a.prioridade, a.classificacao, a.natureza,
         a.item_a, a.substancia_a_id, a.item_b, a.substancia_b_id, a.alvo_tipo,
         a.titulo, a.mecanismo, a.efeito_esperado, a.conduta, a.descricao_fonte,
         a.explicacao, a.gravidade_fonte, a.nivel_evidencia, a.confianca_sistema,
         a.confianca_extracao, a.status_informacao, a.origem_achado,
         a.metodo_deteccao, a.probabilidade_modelo, a.origem_afirmacao, a.fonte,
         a.documento, a.trecho, a.conflito_tipo, a.contexto_paciente,
         a.justificativa_prioridade, a.requer_revisao_profissional,
         a.grupo_chave, a.status, agrupado_em))
    aid = cur.lastrowid
    for e in a.evidencias:
        con.execute(
            "INSERT OR IGNORE INTO achado_evidencia (achado_id, papel, fonte, "
            "tipo_fonte, confiabilidade_fonte, documento, trecho, "
            "origem_afirmacao, gravidade_declarada, mecanismo, efeito_esperado, "
            "conduta, descricao_original, nivel_evidencia, metodo_extracao, "
            "confianca_extracao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, e.papel, e.fonte, e.tipo_fonte, e.confiabilidade_fonte,
             e.documento, e.trecho, e.origem_afirmacao, e.gravidade_declarada,
             e.mecanismo, e.efeito_esperado, e.conduta, e.descricao_original,
             e.nivel_evidencia, e.metodo_extracao, e.confianca_extracao))
    return aid


# =====================================================================
# API PUBLICA
# =====================================================================
def conciliar_atendimento(con, atendimento_id: int,
                          persistir: bool = False) -> ResultadoConciliacao:
    """Ponto de entrada unico do motor de conciliacao.

    `persistir=True` grava conciliacao, achados, evidencias, pares e itens nao
    avaliados. Por padrao NAO grava: como a agenda da Fase 4, o resultado e
    recalculado por leitura, de modo que mudar o dado do paciente muda o
    resultado junto.
    """
    ctx = _carregar_contexto(con, atendimento_id)
    res = ResultadoConciliacao(atendimento_id=atendimento_id,
                               versao_motor=VERSAO_MOTOR)
    if ctx is None:
        res.limitacoes.append("Atendimento %d não encontrado." % atendimento_id)
        res.resumo = _resumo_vazio()
        return res
    res.paciente = ctx.paciente_nome

    achados, nao_aval, limitacoes = [], [], []

    agenda = montar_agenda(con, atendimento_id)
    res.agenda = agenda
    res.conflitos = list(agenda.conflitos)

    _modulo_farmaco_farmaco(ctx, achados, nao_aval)
    _modulo_interacao_prevista(ctx, achados, nao_aval)
    _modulo_farmaco_doenca(ctx, achados, nao_aval)
    _modulo_alergia(ctx, achados, nao_aval)
    _modulo_item(ctx, achados, nao_aval)
    _modulo_habito(ctx, achados, nao_aval)
    _modulo_cyp(ctx, achados, nao_aval)
    _modulo_duplicidade(ctx, achados, nao_aval)
    _da_agenda(ctx, agenda, achados, nao_aval)
    res.pares = _reconciliar(ctx, achados, nao_aval)

    for m in ctx.medicamentos:
        if m.substancia_id is None:
            nao_aval.append(NaoAvaliado(
                item=m.nome_relatado, motivo="SUBSTANCIA_NAO_RECONHECIDA",
                modulo="INFORMACAO_INSUFICIENTE",
                detalhe="Sem vínculo com substância (%s): NENHUM dos 12 módulos "
                        "pôde avaliar este item." % m.reconhecimento))

    _declarar_modulos_sem_fonte(ctx, nao_aval, limitacoes)

    res.achados, res.achados_agrupados = _agrupar(achados)
    res.nao_avaliado = nao_aval
    res.limitacoes = limitacoes + _limitacoes(ctx, res)
    res.resumo = _montar_resumo(ctx, res)
    res.indicadores = _indicadores(ctx, res)

    if persistir:
        res.conciliacao_id = _persistir(con, res)
    return res


def _resumo_vazio() -> dict:
    return {k: 0 for k in (
        "medicamentos", "achados", "criticos", "altos", "moderados", "baixos",
        "informativos", "divergencias", "informacao_insuficiente",
        "nao_avaliado", "conciliados", "nao_conciliados")} | {
        "requer_revisao_profissional": False}


def _montar_resumo(ctx: Contexto, res: ResultadoConciliacao) -> dict:
    # PREVISTO nao entra na contagem por prioridade. Somar previsao com
    # achado documentado no mesmo indicador e a forma mais silenciosa de
    # misturar os dois: o farmaceutico leria "3 informativos" sem saber que
    # um deles nao tem documento nenhum atras. Vai contado a parte.
    documentados = [a for a in res.achados if a.natureza != "PREVISTO"]
    previstos = [a for a in res.achados if a.natureza == "PREVISTO"]
    conta = defaultdict(int)
    for a in documentados:
        conta[a.prioridade] += 1
    insuf = sum(1 for a in documentados
                if a.classificacao == "INFORMACAO_INSUFICIENTE"
                or a.status_informacao in ("INFORMACAO_INSUFICIENTE",
                                           "NAO_DETERMINADO"))
    return {
        "medicamentos": len(ctx.ativos()),
        "medicamentos_reconhecidos": sum(1 for m in ctx.ativos()
                                         if m.substancia_id),
        "achados": len(documentados),
        "achados_previstos": len(previstos),
        "criticos": conta["CRITICO"],
        "altos": conta["ALTO"],
        "moderados": conta["MODERADO"],
        "baixos": conta["BAIXO"],
        "informativos": conta["INFORMATIVO"],
        "divergencias": len(res.divergencias),
        "informacao_insuficiente": insuf,
        "nao_avaliado": len(res.nao_avaliado),
        "conciliados": len(res.conciliados),
        "nao_conciliados": len(res.nao_conciliados),
        "agrupados": len(res.achados_agrupados),
        "requer_revisao_profissional": any(
            a.requer_revisao_profissional for a in res.achados),
    }


def _indicadores(ctx: Contexto, res: ResultadoConciliacao) -> dict:
    por_tipo, por_natureza, por_status, por_confianca = (
        defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int))
    for a in res.achados:
        por_tipo[a.tipo] += 1
        por_natureza[a.natureza] += 1
        por_status[a.status_informacao] += 1
        por_confianca[a.confianca_sistema] += 1
    return {
        "por_tipo": dict(por_tipo),
        "por_natureza": dict(por_natureza),
        "por_status_informacao": dict(por_status),
        "por_confianca_sistema": dict(por_confianca),
        "com_evidencia": sum(1 for a in res.achados if a.evidencias),
        "sem_evidencia": sum(1 for a in res.achados if not a.evidencias),
        "com_duas_ou_mais_fontes": sum(
            1 for a in res.achados if len({e.fonte for e in a.evidencias}) > 1),
        "com_conflito_de_fonte": sum(1 for a in res.achados if a.conflito_tipo),
        "extraidos_automaticamente": sum(
            1 for a in res.achados
            if a.status_informacao == "EXTRAIDO_AUTOMATICAMENTE"),
        "revisados": sum(1 for a in res.achados
                         if a.status_informacao == "REVISADO"),
        "previstos_por_modelo": sum(1 for a in res.achados
                                    if a.origem_achado != "REGRA"),
        "deduplicados": len(res.achados_agrupados),
        "nao_avaliado_por_motivo": _contar(res.nao_avaliado, "motivo"),
        "divergencias_por_tipo": _contar(res.divergencias, "tipo_divergencia"),
    }


def _contar(itens, campo) -> dict:
    c = defaultdict(int)
    for i in itens:
        c[getattr(i, campo) or "(sem tipo)"] += 1
    return dict(c)


def _limitacoes(ctx: Contexto, res: ResultadoConciliacao) -> list:
    lim = []
    nao_rec = [m for m in ctx.ativos() if m.substancia_id is None]
    if nao_rec:
        lim.append("%d medicamento(s) não reconhecidos: nenhum módulo os "
                   "avaliou (%s)." % (len(nao_rec),
                                      ", ".join(m.nome_relatado for m in nao_rec)))
    sem_cob = [n for n in res.nao_avaliado
               if n.motivo == "SUBSTANCIA_SEM_COBERTURA"]
    if sem_cob:
        lim.append("%d verificação(ões) de cobertura falharam por ausência de "
                   "dado na fonte, não por erro do sistema." % len(sem_cob))
    nd = [a for a in res.achados if a.gravidade_fonte == "NAO_DETERMINADA"
          and a.tipo in ("FARMACO_FARMACO",)]
    if nd:
        lim.append("%d interação(ões) documentadas sem gravidade graduada em "
                   "NENHUMA fonte do acervo. Ficam em prioridade baixa por "
                   "honestidade, não por serem pouco importantes." % len(nd))
    auto = [a for a in res.achados
            if a.status_informacao == "EXTRAIDO_AUTOMATICAMENTE"]
    if auto:
        lim.append("%d achado(s) vêm de extração automática ainda não revisada "
                   "por farmacêutico." % len(auto))
    if not ctx.condicoes:
        lim.append("Nenhuma condição clínica registrada: o módulo "
                   "medicamento × doença não teve o que verificar.")
    if not ctx.alergias:
        lim.append("Nenhuma alergia registrada: o módulo de alergia não teve o "
                   "que verificar.")
    return lim
