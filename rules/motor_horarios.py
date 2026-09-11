# -*- coding: utf-8 -*-
"""
MOTOR DE HORARIOS E ADMINISTRACAO

Transforma a farmacoterapia de um atendimento em uma agenda verificavel e
aponta conflitos. Nao altera prescricao: organiza, detecta e apresenta.

CONTRATO PUBLICO (o que a Fase 6 vai consumir):

    montar_agenda(con, atendimento_id) -> Agenda

    Agenda.eventos       list[EventoAdministracao]  ordenados por hora
    Agenda.conflitos     list[Conflito]
    Agenda.nao_avaliado  list[NaoAvaliado]
    Agenda.rotina        dict[str, str]   evento da rotina -> 'HH:MM'

Nenhuma outra funcao deste modulo precisa ser chamada de fora. A interface
nao reimplementa regra: le estas tres listas.

PRINCIPIO: ausencia de dado nunca vira regra.
  - regra documentada .......... aplica
  - regra extraida por regex ... aplica, marcada EXTRAIDA_AUTOMATICAMENTE
  - regras conflitantes ........ nao escolhe; devolve as duas
  - intervalo desconhecido ..... diz que e desconhecido
  - sem informacao ............. entra em nao_avaliado, nunca em silencio

Nenhum intervalo padrao e inventado. '2 horas' e comum na pratica, mas
comum nao e fonte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

VERSAO_MOTOR = "horarios-1.0"

# --------------------------------------------------------------- vocabulario
# Classificacao do achado, exigida pela especificacao da Fase 4.
CONFIRMADO = "CONFLITO_CONFIRMADO"
POSSIVEL = "POSSIVEL_CONFLITO"
INSUFICIENTE = "INFORMACAO_INSUFICIENTE"
DESCONHECIDA = "REGRA_DESCONHECIDA"
SEM_CONFLITO = "SEM_CONFLITO_IDENTIFICADO"

# Quanto tempo, em minutos, ainda conta como "junto da refeicao" quando a
# fonte NAO declarou intervalo. Nao e um intervalo terapeutico inventado: e a
# janela de leitura da agenda, usada so para decidir se o horario esta
# proximo ou longe de uma refeicao. Declarada aqui para ficar auditavel.
JANELA_REFEICAO_MIN = 30

REFEICOES = {"CAFE_MANHA", "LANCHE_MANHA", "ALMOCO",
             "LANCHE_TARDE", "JANTAR", "CEIA"}

NOME_EVENTO = {
    "ACORDAR": "acordar", "DORMIR": "dormir",
    "CAFE_MANHA": "café da manhã", "LANCHE_MANHA": "lanche da manhã",
    "ALMOCO": "almoço", "LANCHE_TARDE": "lanche da tarde",
    "JANTAR": "jantar", "CEIA": "ceia",
    "TRABALHO_INICIO": "início do trabalho", "TRABALHO_FIM": "fim do trabalho",
    "ESCOLA_INICIO": "início da escola", "ESCOLA_FIM": "fim da escola",
    "DESLOCAMENTO": "deslocamento",
}


# ------------------------------------------------------------------ tempo
def para_minutos(hora: str) -> Optional[int]:
    """'06:30' -> 390. None quando a hora nao e utilizavel."""
    if not hora or ":" not in hora:
        return None
    try:
        h, m = hora.split(":")
        h, m = int(h), int(m)
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def para_hora(minutos: int) -> str:
    minutos %= 1440
    return "%02d:%02d" % (minutos // 60, minutos % 60)


def distancia_minutos(a: str, b: str) -> Optional[int]:
    """Menor distancia entre dois horarios, considerando a volta do dia.

    23:30 e 00:30 distam 60 minutos, nao 1380. Ignorar isso faria o motor
    perder conflitos entre a ultima tomada da noite e a primeira da manha.
    """
    ma, mb = para_minutos(a), para_minutos(b)
    if ma is None or mb is None:
        return None
    d = abs(ma - mb)
    return min(d, 1440 - d)


# ------------------------------------------------------------- estruturas
@dataclass
class SeparacaoAplicavel:
    """Uma regra de separacao que vale para este medicamento."""
    alvo_tipo: str                  # SUBSTANCIA | ITEM | CLASSE_ATC
    alvo_nome: str
    intervalo_horas: Optional[float]     # None = a fonte nao estabeleceu
    unidade_intervalo: str = "horas"
    sentido: str = "AMBOS"          # ANTES | DEPOIS | AMBOS
    motivo: str = ""
    fonte: str = ""
    confianca_extracao: str = ""
    orientacao: str = ""


@dataclass
class EventoAdministracao:
    """Uma tomada de um medicamento em um horario."""
    atendimento_medicamento_id: int
    medicamento: str
    substancia: Optional[str]
    dose_valor: Optional[float]
    dose_unidade: Optional[str]
    hora: Optional[str]
    origem_horario: str             # PACIENTE | FARMACEUTICO | SUGERIDO_PELO_SISTEMA
    via: Optional[str] = None
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    vezes_por_dia: Optional[int] = None
    intervalo_horas: Optional[float] = None
    uso_continuo: bool = False
    se_necessario: bool = False
    condicao_uso: Optional[str] = None
    relacao_alimento: str = "NAO_ESTABELECIDA"
    regra_administracao: Optional[str] = None
    orientacao: Optional[str] = None
    intervalo_refeicao_min: Optional[int] = None
    fonte_regra: Optional[str] = None
    confianca_extracao: Optional[str] = None
    separacoes: list = field(default_factory=list)
    status_informacao: str = "COMPLETA"


@dataclass
class Conflito:
    tipo: str
    classificacao: str
    itens: list
    justificativa: str
    horarios: list = field(default_factory=list)
    intervalo_exigido: Optional[float] = None
    intervalo_observado: Optional[float] = None
    fonte: Optional[str] = None
    confianca_extracao: Optional[str] = None


@dataclass
class NaoAvaliado:
    item: str
    motivo: str
    detalhe: str = ""


@dataclass
class Agenda:
    atendimento_id: int
    versao_motor: str
    eventos: list = field(default_factory=list)
    conflitos: list = field(default_factory=list)
    nao_avaliado: list = field(default_factory=list)
    rotina: dict = field(default_factory=dict)

    def resumo(self) -> dict:
        por_classe = {}
        for c in self.conflitos:
            por_classe[c.classificacao] = por_classe.get(c.classificacao, 0) + 1
        return {
            "eventos": len(self.eventos),
            "conflitos": len(self.conflitos),
            "por_classificacao": por_classe,
            "nao_avaliado": len(self.nao_avaliado),
        }


# ------------------------------------------------------------- leitura
def _rotina(con, atendimento_id: int) -> dict:
    return {e: h for e, h in con.execute(
        "SELECT evento, hora FROM rotina_paciente WHERE atendimento_id=?",
        (atendimento_id,))}


def _regras_administracao(con, substancia_id: int) -> list:
    return con.execute(
        "SELECT r.tipo, r.intervalo_refeicao_min, r.texto_orientacao, "
        "f.nome, r.confianca_extracao "
        "FROM vw_regra_administracao_liberada r JOIN fonte f ON f.id=r.fonte_id "
        "WHERE r.substancia_id=?", (substancia_id,)).fetchall()


def _separacoes(con, substancia_id: int) -> list:
    linhas = con.execute(
        "SELECT r.alvo_tipo, r.alvo_substancia_id, r.alvo_item_id, "
        "r.alvo_classe_atc, r.intervalo_horas, r.sentido, r.motivo, "
        "f.nome, r.confianca_extracao, r.orientacao_pt "
        "FROM vw_regra_separacao_liberada r JOIN fonte f ON f.id=r.fonte_id "
        "WHERE r.substancia_id=?", (substancia_id,)).fetchall()
    saida = []
    for (tipo, sid, iid, atc, horas, sentido, motivo, fonte,
         conf, orient) in linhas:
        if tipo == "SUBSTANCIA":
            nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                               (sid,)).fetchone()
        elif tipo == "ITEM":
            nome = con.execute(
                "SELECT nome FROM item_nao_medicamentoso WHERE id=?",
                (iid,)).fetchone()
        else:
            nome = con.execute("SELECT nome_pt FROM classe_atc WHERE codigo=?",
                               (atc,)).fetchone()
        saida.append(SeparacaoAplicavel(
            alvo_tipo=tipo, alvo_nome=(nome[0] if nome else "(desconhecido)"),
            intervalo_horas=horas, sentido=sentido, motivo=motivo,
            fonte=fonte, confianca_extracao=conf, orientacao=orient))
    return saida


# ------------------------------------------------- relacao com alimento
# Tipos que dizem algo sobre alimento. Os demais (agua, nao partir, sublingual)
# nao entram nesta decisao.
RELACAO_ALIMENTO = {
    "JEJUM": "JEJUM",
    "COM_ALIMENTO": "COM_ALIMENTO",
    "APOS_ALIMENTO": "APOS_ALIMENTO",
    "ANTES_ALIMENTO": "ANTES_ALIMENTO",
    "INDIFERENTE_ALIMENTO": "INDIFERENTE",
}


def _relacao_alimento(regras) -> tuple:
    """Devolve (relacao, regra, orientacao, minutos, fonte, confianca, conflito).

    Quando duas fontes discordam, NAO escolhe: devolve conflito e a relacao
    fica NAO_ESTABELECIDA. Escolher em silencio e o que a especificacao proibe.
    """
    alimentares = [r for r in regras if r[0] in RELACAO_ALIMENTO]
    if not alimentares:
        return ("NAO_ESTABELECIDA", None, None, None, None, None, None)
    tipos = {r[0] for r in alimentares}
    # 'indiferente' contra um tipo especifico nao e contradicao: a fonte
    # especifica manda, porque diz mais.
    especificos = tipos - {"INDIFERENTE_ALIMENTO"}
    if len(especificos) > 1:
        return ("NAO_ESTABELECIDA", None, None, None, None, None,
                sorted(especificos))
    escolhido = None
    for r in alimentares:
        if not especificos or r[0] in especificos:
            escolhido = r
            break
    tipo, minutos, orientacao, fonte, conf = escolhido
    return (RELACAO_ALIMENTO[tipo], tipo, orientacao, minutos, fonte, conf, None)


# ------------------------------------------------------------- sugestao
def _sugerir_horarios(vezes_por_dia, intervalo_horas, rotina) -> list:
    """Horarios propostos quando o paciente nao informou nenhum.

    Distribui dentro do periodo acordado da pessoa. E sugestao explicita,
    marcada como tal, e nunca substitui horario informado.
    """
    acordar = para_minutos(rotina.get("ACORDAR", "07:00")) or 420
    dormir = para_minutos(rotina.get("DORMIR", "22:00")) or 1320
    if dormir <= acordar:
        dormir = acordar + 900
    if intervalo_horas:
        passo = int(intervalo_horas * 60)
        n = max(1, int(round(24 * 60 / passo)))
    elif vezes_por_dia:
        n = vezes_por_dia
        passo = (dormir - acordar) // max(1, n - 1) if n > 1 else 0
    else:
        return []
    horas = []
    for i in range(n):
        horas.append(para_hora(acordar + i * passo))
    return horas[:12]


# ------------------------------------------------------------------ motor
def montar_agenda(con, atendimento_id: int) -> Agenda:
    """Ponto de entrada unico do motor de horarios."""
    agenda = Agenda(atendimento_id=atendimento_id, versao_motor=VERSAO_MOTOR)
    agenda.rotina = _rotina(con, atendimento_id)
    refeicoes = {e: h for e, h in agenda.rotina.items() if e in REFEICOES}

    medicamentos = con.execute(
        "SELECT am.id, am.nome_relatado, am.substancia_id, s.nome_dcb, "
        "am.reconhecimento "
        "FROM atendimento_medicamento am "
        "LEFT JOIN substancia s ON s.id = am.substancia_id "
        "WHERE am.atendimento_id=?", (atendimento_id,)).fetchall()

    if not medicamentos:
        agenda.nao_avaliado.append(NaoAvaliado(
            item="(atendimento sem medicamentos)",
            motivo="POSOLOGIA_NAO_INFORMADA",
            detalhe="Nenhum medicamento foi registrado neste atendimento."))
        return agenda

    por_evento_substancia = {}      # substancia_id -> [(hora, evento)]

    for am_id, nome_relatado, sid, nome_dcb, reconhecimento in medicamentos:
        if sid is None:
            agenda.nao_avaliado.append(NaoAvaliado(
                item=nome_relatado, motivo="SUBSTANCIA_NAO_RECONHECIDA",
                detalhe="Sem vínculo com substância: nenhuma regra pôde ser "
                        "aplicada a este item."))
            continue

        pos = con.execute(
            "SELECT dose_valor,dose_unidade,vezes_por_dia,intervalo_horas,"
            "via_administracao,duracao_dias,data_inicio,data_fim_prevista,"
            "uso_continuo,se_necessario,condicao_uso "
            "FROM posologia WHERE atendimento_medicamento_id=?",
            (am_id,)).fetchone()

        if pos is None:
            agenda.nao_avaliado.append(NaoAvaliado(
                item=nome_relatado, motivo="POSOLOGIA_NAO_INFORMADA",
                detalhe="Sem posologia estruturada: o horário não pôde ser "
                        "montado."))
            continue

        (dose, unidade, vezes, intervalo, via, duracao, inicio, fim,
         continuo, prn, condicao) = pos

        regras = _regras_administracao(con, sid)
        (relacao, regra_tipo, orientacao, minutos_ref, fonte_regra,
         confianca, conflito_regra) = _relacao_alimento(regras)
        separacoes = _separacoes(con, sid)

        if conflito_regra:
            agenda.conflitos.append(Conflito(
                tipo="REGRAS_DE_ALIMENTACAO_CONFLITANTES",
                classificacao=DESCONHECIDA,
                itens=[nome_relatado],
                justificativa="Fontes discordam sobre a relação com alimento "
                              "(%s). Nenhuma foi adotada; requer decisão do "
                              "farmacêutico." % " × ".join(conflito_regra)))

        horarios = [(h, o) for h, o in con.execute(
            "SELECT ha.hora, ha.definido_por FROM horario_administracao ha "
            "JOIN posologia p ON p.id = ha.posologia_id "
            "WHERE p.atendimento_medicamento_id=? ORDER BY ha.hora",
            (am_id,))]

        status = "COMPLETA"
        if not horarios:
            if prn:
                status = "SE_NECESSARIO_SEM_HORARIO_FIXO"
                agenda.eventos.append(EventoAdministracao(
                    atendimento_medicamento_id=am_id, medicamento=nome_relatado,
                    substancia=nome_dcb, dose_valor=dose, dose_unidade=unidade,
                    hora=None, origem_horario="PACIENTE", via=via,
                    data_inicio=inicio, data_fim=fim, vezes_por_dia=vezes,
                    intervalo_horas=intervalo, uso_continuo=bool(continuo),
                    se_necessario=True, condicao_uso=condicao,
                    relacao_alimento=relacao, regra_administracao=regra_tipo,
                    orientacao=orientacao, intervalo_refeicao_min=minutos_ref,
                    fonte_regra=fonte_regra, confianca_extracao=confianca,
                    separacoes=separacoes, status_informacao=status))
                continue
            sugeridos = _sugerir_horarios(vezes, intervalo, agenda.rotina)
            if not sugeridos:
                agenda.nao_avaliado.append(NaoAvaliado(
                    item=nome_relatado, motivo="HORARIO_NAO_INFORMADO",
                    detalhe="Sem horário e sem frequência: não há como montar "
                            "a agenda deste item."))
                continue
            horarios = [(h, "SUGERIDO_PELO_SISTEMA") for h in sugeridos]
            status = "HORARIO_SUGERIDO"

        # frequencia declarada x horarios informados
        if vezes and len(horarios) != vezes:
            agenda.conflitos.append(Conflito(
                tipo="FREQUENCIA_INCOMPATIVEL_COM_HORARIOS",
                classificacao=CONFIRMADO if horarios[0][1] != "SUGERIDO_PELO_SISTEMA"
                else INSUFICIENTE,
                itens=[nome_relatado],
                horarios=[h for h, _ in horarios],
                justificativa="Posologia declara %d tomada(s) por dia, mas há "
                              "%d horário(s) registrado(s)." %
                              (vezes, len(horarios))))

        # intervalo declarado x distancia real entre tomadas
        if intervalo and len(horarios) > 1:
            reais = []
            ordenados = sorted(para_minutos(h) for h, _ in horarios
                               if para_minutos(h) is not None)
            for i in range(len(ordenados) - 1):
                reais.append(ordenados[i + 1] - ordenados[i])
            if reais:
                menor = min(reais) / 60.0
                if menor + 0.01 < intervalo:
                    agenda.conflitos.append(Conflito(
                        tipo="INTERVALO_ENTRE_DOSES_MENOR_QUE_O_DECLARADO",
                        classificacao=CONFIRMADO,
                        itens=[nome_relatado],
                        horarios=[h for h, _ in horarios],
                        intervalo_exigido=intervalo,
                        intervalo_observado=round(menor, 2),
                        justificativa="A posologia declara intervalo de %g h, "
                                      "mas dois horários distam %.1f h." %
                                      (intervalo, menor)))

        for hora, definido_por in horarios:
            evento = EventoAdministracao(
                atendimento_medicamento_id=am_id, medicamento=nome_relatado,
                substancia=nome_dcb, dose_valor=dose, dose_unidade=unidade,
                hora=hora, origem_horario=definido_por, via=via,
                data_inicio=inicio, data_fim=fim, vezes_por_dia=vezes,
                intervalo_horas=intervalo, uso_continuo=bool(continuo),
                se_necessario=bool(prn), condicao_uso=condicao,
                relacao_alimento=relacao, regra_administracao=regra_tipo,
                orientacao=orientacao, intervalo_refeicao_min=minutos_ref,
                fonte_regra=fonte_regra, confianca_extracao=confianca,
                separacoes=separacoes, status_informacao=status)
            agenda.eventos.append(evento)
            por_evento_substancia.setdefault(sid, []).append((hora, evento))

            _checar_refeicao(agenda, evento, refeicoes, minutos_ref)
            _checar_rotina(agenda, evento, agenda.rotina)

        if dose is None:
            agenda.nao_avaliado.append(NaoAvaliado(
                item=nome_relatado, motivo="POSOLOGIA_NAO_INFORMADA",
                detalhe="Dose não informada: comum no balcão. A agenda foi "
                        "montada, mas a dose não pôde ser conferida."))

    _checar_duplicidade(agenda, por_evento_substancia, con)
    _checar_separacoes(agenda, por_evento_substancia, con, atendimento_id)
    agenda.eventos.sort(key=lambda e: (e.hora is None, e.hora or "", e.medicamento))
    return agenda


# ---------------------------------------------------------- verificacoes
def _checar_refeicao(agenda, evento, refeicoes, minutos_ref):
    """Confere o horario contra a rotina alimentar real do paciente."""
    if evento.relacao_alimento in ("NAO_ESTABELECIDA", "INDIFERENTE"):
        return
    if not refeicoes:
        agenda.nao_avaliado.append(NaoAvaliado(
            item=evento.medicamento, motivo="HORARIO_NAO_INFORMADO",
            detalhe="O medicamento tem regra de alimentação (%s), mas a rotina "
                    "de refeições do paciente não foi informada: não é "
                    "possível dizer se o horário a respeita."
                    % evento.relacao_alimento))
        return

    perto = None
    for nome, hora in refeicoes.items():
        d = distancia_minutos(evento.hora, hora)
        if d is not None and (perto is None or d < perto[1]):
            perto = (nome, d, hora)
    if perto is None:
        return
    nome_ref, dist, hora_ref = perto
    exigido = minutos_ref if minutos_ref else JANELA_REFEICAO_MIN
    legivel = NOME_EVENTO.get(nome_ref, nome_ref.lower())

    if evento.relacao_alimento == "JEJUM":
        if dist < exigido:
            agenda.conflitos.append(Conflito(
                tipo="JEJUM_PROXIMO_DE_REFEICAO",
                classificacao=CONFIRMADO if minutos_ref else POSSIVEL,
                itens=[evento.medicamento],
                horarios=[evento.hora, hora_ref],
                intervalo_exigido=exigido / 60.0,
                intervalo_observado=round(dist / 60.0, 2),
                justificativa="%s deve ser tomado em jejum, mas está %d min do "
                              "%s (%s).%s" %
                              (evento.medicamento, dist, legivel, hora_ref,
                               "" if minutos_ref else
                               " A fonte não declarou o intervalo exigido; "
                               "usada a janela de leitura de %d min."
                               % JANELA_REFEICAO_MIN),
                fonte=evento.fonte_regra,
                confianca_extracao=evento.confianca_extracao))
    elif evento.relacao_alimento in ("COM_ALIMENTO", "APOS_ALIMENTO",
                                     "ANTES_ALIMENTO"):
        if dist > max(exigido, JANELA_REFEICAO_MIN) + 30:
            agenda.conflitos.append(Conflito(
                tipo="ALIMENTO_EXIGIDO_SEM_REFEICAO_PROXIMA",
                classificacao=POSSIVEL,
                itens=[evento.medicamento],
                horarios=[evento.hora, hora_ref],
                intervalo_observado=round(dist / 60.0, 2),
                justificativa="%s deve ser tomado %s, mas a refeição mais "
                              "próxima (%s, %s) está a %d min." %
                              (evento.medicamento,
                               "junto do alimento" if evento.relacao_alimento
                               == "COM_ALIMENTO" else "perto da refeição",
                               legivel, hora_ref, dist),
                fonte=evento.fonte_regra,
                confianca_extracao=evento.confianca_extracao))


def _checar_rotina(agenda, evento, rotina):
    """Horario fora do periodo em que a pessoa esta acordada."""
    acordar, dormir = rotina.get("ACORDAR"), rotina.get("DORMIR")
    if not acordar or not dormir or not evento.hora:
        return
    ma, md = para_minutos(acordar), para_minutos(dormir)
    me = para_minutos(evento.hora)
    if None in (ma, md, me):
        return
    acordado = (ma <= me <= md) if ma < md else (me >= ma or me <= md)
    if not acordado:
        agenda.conflitos.append(Conflito(
            tipo="HORARIO_FORA_DA_ROTINA",
            classificacao=POSSIVEL,
            itens=[evento.medicamento],
            horarios=[evento.hora],
            justificativa="Tomada às %s, mas o paciente acorda às %s e dorme "
                          "às %s. Exige acordar para tomar ou mudar o horário."
                          % (evento.hora, acordar, dormir)))


def _checar_duplicidade(agenda, por_substancia, con):
    """Mesma substancia registrada mais de uma vez no atendimento."""
    for sid, pares in por_substancia.items():
        ids = {e.atendimento_medicamento_id for _, e in pares}
        if len(ids) > 1:
            nome = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                               (sid,)).fetchone()
            itens = sorted({e.medicamento for _, e in pares})
            agenda.conflitos.append(Conflito(
                tipo="DUPLICIDADE_DA_MESMA_SUBSTANCIA",
                classificacao=CONFIRMADO,
                itens=itens,
                justificativa="%s aparece em mais de um item da farmacoterapia "
                              "(%s). Pode ser duplicidade terapêutica ou "
                              "associação intencional." %
                              (nome[0] if nome else "substância", ", ".join(itens))))


def _alvos_presentes(con, atendimento_id, sep, por_substancia, nomes):
    """Onde o alvo da separacao aparece NESTE atendimento.

    Tres formas, e as tres importam:
      SUBSTANCIA  outro medicamento com a mesma substancia
      CLASSE_ATC  outro medicamento cuja substancia pertence a classe
                  (e assim que 'separar de antiacidos' vira conflito real:
                  antiacido e uma classe inteira, nao uma substancia)
      ITEM        suplemento, alimento ou cha que o paciente declarou usar
    """
    achados = []
    if sep.alvo_tipo == "SUBSTANCIA":
        sid = nomes.get(sep.alvo_nome)
        if sid is not None and sid in por_substancia:
            for hora, ev in por_substancia[sid]:
                achados.append((sep.alvo_nome, hora, ev))
        return achados

    if sep.alvo_tipo == "CLASSE_ATC":
        codigo = con.execute(
            "SELECT codigo FROM classe_atc WHERE nome_pt=? OR nome_en=? LIMIT 1",
            (sep.alvo_nome, sep.alvo_nome)).fetchone()
        if not codigo:
            return achados
        prefixo = codigo[0]
        for sid, pares in por_substancia.items():
            atc = con.execute("SELECT atc_codigo FROM substancia WHERE id=?",
                              (sid,)).fetchone()
            if atc and atc[0] and atc[0].startswith(prefixo):
                for hora, ev in pares:
                    achados.append((ev.medicamento, hora, ev))
        return achados

    # ITEM: o paciente declarou usar? (suplemento, cha, alimento)
    linhas = con.execute(
        "SELECT ai.nome_relatado, ai.horario_habitual FROM atendimento_item ai "
        "LEFT JOIN item_nao_medicamentoso i ON i.id = ai.item_id "
        "WHERE ai.atendimento_id=? AND (i.nome = ? OR ai.nome_relatado LIKE ?)",
        (atendimento_id, sep.alvo_nome, "%" + sep.alvo_nome + "%")).fetchall()
    for nome, horario in linhas:
        achados.append((nome, horario, None))
    return achados


def _checar_separacoes(agenda, por_substancia, con, atendimento_id):
    """Regras de separacao contra o que o paciente realmente usa."""
    nomes = {}
    for sid in por_substancia:
        r = con.execute("SELECT nome_dcb FROM substancia WHERE id=?",
                        (sid,)).fetchone()
        if r:
            nomes[r[0]] = sid

    vistos = set()
    for sid, pares in por_substancia.items():
        if not pares:
            continue
        origem = pares[0][1]
        for sep in origem.separacoes:
            alvos = _alvos_presentes(con, atendimento_id, sep,
                                     por_substancia, nomes)
            if not alvos:
                # O alvo nao esta na farmacoterapia registrada. Isso nao e
                # conflito nem lacuna: a orientacao ja acompanha o evento em
                # evento.separacoes, para a interface exibir como cuidado.
                continue

            for alvo_nome, hora_alvo, ev_alvo in alvos:
                if ev_alvo is not None and                         ev_alvo.atendimento_medicamento_id ==                         origem.atendimento_medicamento_id:
                    continue
                chave = (origem.atendimento_medicamento_id, alvo_nome,
                         sep.alvo_tipo)
                if chave in vistos:
                    continue
                vistos.add(chave)
                _conflito_alvo(agenda, pares, alvo_nome, hora_alvo, sep)


def _conflito_alvo(agenda, pares_origem, alvo_nome, hora_alvo, sep):
    """Compara os horarios do medicamento com os do alvo da separacao."""
    origem = pares_origem[0][1]

    if hora_alvo is None:
        agenda.nao_avaliado.append(NaoAvaliado(
            item="%s × %s" % (origem.medicamento, alvo_nome),
            motivo="HORARIO_NAO_INFORMADO",
            detalhe="Há regra de separação, mas o horário de %s não foi "
                    "informado: não é possível verificar o conflito. %s"
                    % (alvo_nome, sep.orientacao or "")))
        return

    menor = None
    hora_origem = None
    for ho, _ in pares_origem:
        d = distancia_minutos(ho, hora_alvo)
        if d is not None and (menor is None or d < menor):
            menor, hora_origem = d, ho
    if menor is None:
        return

    if sep.intervalo_horas is None:
        agenda.conflitos.append(Conflito(
            tipo="SEPARACAO_COM_INTERVALO_DESCONHECIDO",
            classificacao=DESCONHECIDA,
            itens=[origem.medicamento, alvo_nome],
            horarios=[hora_origem, hora_alvo],
            intervalo_observado=round(menor / 60.0, 2),
            justificativa="%s e %s devem ser separados (%s), mas o intervalo "
                          "não está estabelecido na fonte. Os horários atuais "
                          "distam %.1f h." % (origem.medicamento, alvo_nome,
                                              sep.motivo, menor / 60.0),
            fonte=sep.fonte, confianca_extracao=sep.confianca_extracao))
        agenda.nao_avaliado.append(NaoAvaliado(
            item="%s × %s" % (origem.medicamento, alvo_nome),
            motivo="REGRA_SEM_INTERVALO_ESTABELECIDO",
            detalhe="A fonte manda separar mas não publica o intervalo. "
                    "Nenhum valor foi presumido."))
        return

    exigido = sep.intervalo_horas * 60
    if menor + 0.5 < exigido:
        agenda.conflitos.append(Conflito(
            tipo="SEPARACAO_NAO_RESPEITADA",
            classificacao=CONFIRMADO,
            itens=[origem.medicamento, alvo_nome],
            horarios=[hora_origem, hora_alvo],
            intervalo_exigido=sep.intervalo_horas,
            intervalo_observado=round(menor / 60.0, 2),
            justificativa="%s e %s exigem %g h de separação (%s), mas estão a "
                          "%.1f h." % (origem.medicamento, alvo_nome,
                                       sep.intervalo_horas, sep.motivo,
                                       menor / 60.0),
            fonte=sep.fonte, confianca_extracao=sep.confianca_extracao))
