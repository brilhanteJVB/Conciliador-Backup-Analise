# -*- coding: utf-8 -*-
"""
ROTULOS EM PORTUGUES — o vocabulario do banco traduzido para a tela.

Isto e camada de INTERFACE, nao de regra: aqui so mora a palavra que o
farmaceutico le. Nenhuma decisao clinica acontece neste arquivo, e nenhum
valor e transformado em outro — `EXTRAIDO_AUTOMATICAMENTE` vira "extraído
automaticamente, sem revisão", e **nunca** vira "confirmado".

O sistema inteiro fala portugues do Brasil. Nomenclatura cientifica e
preservada (`CYP3A4` continua `CYP3A4`), mas o que a descreve sai em
portugues.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rules"))

# Uma definicao so, partilhada com o motor: a probabilidade de uma previsao e
# escrita do mesmo jeito na explicacao do achado, na tela e no relatorio. Ver
# `rules/_prioridade.percentual_previsao` para o motivo do teto.
from _prioridade import (percentual_previsao,           # noqa: E402,F401
                         probabilidade_saturada)

# --------------------------------------------------------------- prioridade
PRIORIDADE = {
    "CRITICO": "Crítico", "ALTO": "Alto", "MODERADO": "Moderado",
    "BAIXO": "Baixo", "INFORMATIVO": "Informativo",
}
ORDEM_PRIORIDADE = ["CRITICO", "ALTO", "MODERADO", "BAIXO", "INFORMATIVO"]

PRIORIDADE_EXPLICACAO = {
    "CRITICO": "Exige conferência antes de qualquer dispensação.",
    "ALTO": "Precisa da atenção do farmacêutico neste atendimento.",
    "MODERADO": "Vale conferir com o paciente.",
    "BAIXO": "Registrado para conhecimento; risco menor ou pouco sustentado.",
    "INFORMATIVO": "Não é problema detectado — é informação a repassar.",
}

# ---------------------------------------------------------------- gravidade
GRAVIDADE = {
    "MAIOR": "Maior", "MODERADA": "Moderada", "MENOR": "Menor",
    "NAO_DETERMINADA": "Não graduada pela fonte", None: "Não se aplica",
}

# ----------------------------------------------------------------- confianca
CONFIANCA = {"ALTA": "Alta", "MEDIA": "Média", "BAIXA": "Baixa"}

CONFIANCA_EXPLICACAO = {
    "ALTA": "Afirmação revisada, ou carga direta de fonte de alta "
            "confiabilidade com evidência respaldada.",
    "MEDIA": "Carga direta de fonte confiável, mas com evidência limitada.",
    "BAIXA": "Extração automática não revisada, fonte de procedência frágil, "
             "ou inferência mecanística.",
}

# --------------------------------------------------- status e natureza
STATUS_INFORMACAO = {
    "DOCUMENTADO": "Documentado",
    "EXTRAIDO_AUTOMATICAMENTE": "Extraído automaticamente — sem revisão",
    "REVISADO": "Revisado por farmacêutico",
    "INFORMACAO_INSUFICIENTE": "Informação insuficiente",
    "NAO_DETERMINADO": "Não determinado pela fonte",
    "PREVISTO": "Previsto por modelo",
}

STATUS_EXPLICACAO = {
    "DOCUMENTADO": "A fonte afirma isto diretamente.",
    "EXTRAIDO_AUTOMATICAMENTE": "A informação foi lida de um texto por "
                                "expressão regular e AINDA NÃO passou por "
                                "revisão farmacêutica. Confira o trecho de "
                                "origem antes de usar.",
    "REVISADO": "Um farmacêutico conferiu e aprovou esta afirmação.",
    "INFORMACAO_INSUFICIENTE": "Há dados do paciente e do medicamento, mas "
                               "não o bastante para concluir.",
    "NAO_DETERMINADO": "A fonte não estabelece este aspecto. Não é falha de "
                       "leitura: o dado não existe na origem.",
    "PREVISTO": "Resultado de modelo preditivo, não de evidência publicada. "
                "Nenhuma fonte do acervo afirma isto. O número é a "
                "probabilidade estimada de o par ESTAR DOCUMENTADO em alguma "
                "base — não a gravidade e não o risco.",
}

# Situação da previsão em si, distinta da situação da informação do achado:
# uma previsão pode ter sido lida e julgada por um farmacêutico sem por isso
# virar evidência documental.
STATUS_PREDICAO = {
    "NAO_REVISADA": "ainda não revisada por farmacêutico",
    "REVISADA_ACEITA": "revisada e considerada plausível",
    "REVISADA_RECUSADA": "revisada e recusada",
}

NATUREZA = {
    "DOCUMENTADO": "Documentado em fonte", "PROVAVEL": "Provável",
    "POSSIVEL": "Possível", "PREVISTO": "Previsto por modelo",
    "DESCONHECIDO": "Desconhecido", "CONFLITANTE": "Fontes em conflito",
}

CLASSIFICACAO = {
    "CONFIRMADO": "Confirmado neste paciente",
    "POSSIVEL": "Possível neste paciente",
    "INFORMACAO_INSUFICIENTE": "Falta dado para confirmar",
    "REGRA_DESCONHECIDA": "Regra sem parâmetro na fonte",
    "CONFLITO_ENTRE_FONTES": "As fontes discordam",
}

CONFIANCA_EXTRACAO = {
    "REVISADA": "Revisada por pessoa",
    "CARGA_DIRETA": "Lida de campo estruturado da fonte",
    "EXTRAIDA_AUTOMATICAMENTE": "Extraída de texto por expressão regular",
    "CALCULADO": "Calculada sobre os dados deste atendimento",
    "NAO_APLICAVEL": "Não se aplica",
}

NIVEL_EVIDENCIA = {
    "RESPALDADA": "Respaldada", "LIMITADA": "Limitada", "TEORICA": "Teórica",
    "NAO_AVALIADA": "Não avaliada", None: "—",
}

# ------------------------------------------------------------------ modulos
MODULO = {
    "FARMACO_FARMACO": "Interação entre medicamentos",
    "FARMACO_DOENCA": "Medicamento e condição clínica",
    "FARMACO_ALERGIA": "Alergia",
    "FARMACO_ALIMENTO": "Medicamento e alimento",
    "FARMACO_PLANTA": "Medicamento e planta ou chá",
    "FARMACO_SUPLEMENTO": "Medicamento e suplemento",
    "FARMACO_HABITO": "Medicamento e hábito",
    "FARMACO_CYP": "Enzima ou transportador",
    "DUPLICIDADE": "Duplicidade",
    "REACAO_ADVERSA": "Reação adversa",
    "CONFLITO_HORARIO": "Horário de administração",
    "REGRA_ADMINISTRACAO": "Como tomar",
    "POSOLOGIA": "Posologia",
    "DIVERGENCIA_CONCILIACAO": "Divergência de conciliação",
    "INFORMACAO_INSUFICIENTE": "Informação insuficiente",
    "ADESAO": "Adesão",
}

ALVO_TIPO = {
    "SUBSTANCIA": "medicamento", "DOENCA": "condição clínica",
    "ALERGIA": "alergia", "ITEM": "alimento, planta ou suplemento",
    "HABITO": "hábito", "CLASSE_ATC": "classe terapêutica",
    "ENZIMA": "enzima", "POSOLOGIA": "posologia", "LISTA": "lista",
    "NENHUM": "—",
}

# ------------------------------------------------------------- conciliacao
SITUACAO_PAR = {
    "CONCILIADO": "Conciliado",
    "DIVERGENCIA": "Divergência",
    "POSSIVEL_DIVERGENCIA": "Possível divergência",
    "INFORMACAO_INSUFICIENTE": "Informação insuficiente",
    "REVISAO_NECESSARIA": "Revisão necessária",
}

TIPO_DIVERGENCIA = {
    "SO_NA_PRESCRICAO": "Consta da prescrição, o paciente não relatou usar",
    "SO_NO_RELATO": "O paciente usa, não consta da prescrição",
    "DOSE_DIFERENTE": "Dose diferente",
    "FREQUENCIA_DIFERENTE": "Frequência diferente",
    "HORARIO_DIFERENTE": "Horário diferente",
    "VIA_DIFERENTE": "Via diferente",
    "DUPLICIDADE": "Item repetido na mesma lista",
    "POSOLOGIA_INSUFICIENTE": "Falta posologia em um dos lados",
    "SEM_CORRESPONDENCIA": "Sem correspondência no cadastro",
    "DESCONTINUADO_EM_USO": "Consta como suspenso e o paciente continua usando",
    None: "—",
}

INTENCIONALIDADE = {
    "NAO_DETERMINADA": "Não determinada",
    "INTENCIONAL": "Intencional",
    "NAO_INTENCIONAL": "Erro de conciliação",
}

# -------------------------------------------------------------- nao avaliado
MOTIVO_NAO_AVALIADO = {
    "SUBSTANCIA_NAO_RECONHECIDA": "Medicamento não reconhecido",
    "SUBSTANCIA_SEM_COBERTURA": "Substância sem cobertura na base",
    "SEM_INTERACAO_CONHECIDA": "Par verificado, nenhuma interação registrada",
    "POSOLOGIA_NAO_INFORMADA": "Posologia não informada",
    "HORARIO_NAO_INFORMADO": "Horário não informado",
    "REGRA_SEM_INTERVALO_ESTABELECIDO": "A fonte manda separar e não diz por "
                                        "quanto tempo",
    "GRAVIDADE_NAO_GRADUADA_NA_FONTE": "A fonte não graduou a gravidade",
    "CONDICAO_NAO_RECONHECIDA": "Condição clínica não reconhecida",
    "ALERGIA_NAO_RECONHECIDA": "Alergia não reconhecida",
    "ITEM_NAO_RECONHECIDO": "Item não reconhecido",
    "DOSE_NAO_INFORMADA": "Dose não informada",
    "HABITO_NAO_INFORMADO": "Hábito não informado",
    "SEM_CORRESPONDENCIA_ENTRE_LISTAS": "Faltou uma das listas para conciliar",
    "MODULO_SEM_FONTE_NO_ACERVO": "Módulo sem fonte disponível",
    "PAR_NAO_PONTUADO_PELO_MODELO": "O modelo preditivo não pontuou "
                                    "este par",
}

# --------------------------------------------------------------- diversos
SEXO = {"F": "Feminino", "M": "Masculino", "OUTRO": "Outro",
        "NAO_INFORMADO": "Não informado", None: "Não informado"}

CANAL = {"MIP": "Venda livre (MIP)", "TARJA_VERMELHA": "Tarja vermelha",
         "TARJA_VERMELHA_RETENCAO": "Tarja vermelha com retenção",
         "TARJA_PRETA": "Tarja preta", "NAO_DETERMINADO": "Não determinado"}

PAPEL_EVIDENCIA = {"PRINCIPAL": "Fonte principal",
                   "CORROBORA": "Corrobora", "DIVERGE": "Diverge"}

METODO_EXTRACAO = {"CARGA_DIRETA": "Carga direta", "REGEX": "Expressão regular",
                   "NLP": "Processamento de texto",
                   "CURADORIA_HUMANA": "Curadoria humana", None: "—"}

TIPO_ITEM = {"ALIMENTO": "Alimento", "BEBIDA": "Bebida", "CHA": "Chá",
             "PLANTA_MEDICINAL": "Planta medicinal",
             "SUPLEMENTO": "Suplemento", "VITAMINA": "Vitamina",
             "MINERAL": "Mineral"}


# O subtipo e um codigo interno, e ate a Fase 9 chegava a tela como
# "interacao prevista" — sem acento, em minusculas, direto do banco. Traduzir
# aqui e o mesmo criterio de todos os outros vocabularios deste arquivo.
SUBTIPO = {
    "INTERACAO_DOCUMENTADA": "Interação documentada",
    "INTERACAO_PREVISTA": "Interação prevista por modelo",
    "INTERACAO_FARMACOCINETICA": "Interação farmacocinética",
    "INTERACAO_FARMACODINAMICA": "Interação farmacodinâmica",
    "INTERACAO_FARMACEUTICA": "Interação farmacêutica",
    "NAO_DETERMINADO": "Tipo de interação não determinado",
    "CONTRAINDICADO": "Contraindicado",
    "USAR_COM_CAUTELA": "Usar com cautela",
    "EVITAR": "Evitar",
    "ALERGIA_SEM_VINCULO": "Alergia sem vínculo no cadastro",
    "MESMA_SUBSTANCIA": "Mesma substância",
    "MESMA_CLASSE_ATC": "Mesma classe ATC",
    "MESMA_CLASSE_ATC4": "Mesma classe ATC de 4º nível",
    "ITEM_EM_USO": "Item em uso pelo paciente",
    "ORIENTACAO_PREVENTIVA": "Orientação preventiva",
    "HABITO_ATUAL": "Hábito atual",
    "HABITO_ANTERIOR": "Hábito anterior",
    "ORIENTACAO": "Orientação de administração",
    "DOSE_NAO_INFORMADA": "Dose não informada",
    "SO_NO_RELATO": "Só no relato do paciente",
    "SO_NA_PRESCRICAO": "Só na prescrição",
    "DOSE_DIFERENTE": "Dose diferente",
    "FREQUENCIA_DIFERENTE": "Frequência diferente",
    "VIA_DIFERENTE": "Via diferente",
    "SEM_CORRESPONDENCIA": "Sem correspondência entre as listas",
}


def rotular(mapa: dict, valor, padrao: str = None):
    """Traduz sem inventar: valor desconhecido volta como veio."""
    if valor in mapa:
        return mapa[valor]
    return padrao if padrao is not None else (valor or "—")
