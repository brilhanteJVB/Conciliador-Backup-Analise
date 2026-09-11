# -*- coding: utf-8 -*-
"""
CARGA DE FARMACO x DOENCA — secao CONTRAINDICACOES das bulas ANVISA.

Alimenta o modulo 2 do motor (farmaco x doenca / condicao clinica) e o
modulo 10 (contraindicacao e precaucao).

POR QUE ESTA FONTE, E POR QUE NAO O `mapping.csv`
-------------------------------------------------
D-004 recusou `Drug-disease/mapping.csv` (42.200 pares) por um motivo unico e
decisivo: ele liga farmaco a doenca **sem qualificar a relacao**. Nao distingue
"trata" de "e contraindicado em". Usado como esta, o sistema alertaria contra
a doenca que o medicamento trata.

A secao CONTRAINDICACOES da bula nao tem esse problema: a relacao ja vem
declarada pelo proprio titulo da secao e repetida no verbo da frase
("e contraindicado em pacientes com insuficiencia renal"). E fonte
regulatoria brasileira, em portugues, e o trecho literal fica gravado em
`interacao_doenca.trecho_origem` para conferencia.

O QUE ISTO **NAO** E
--------------------
Nao e leitura revisada. Toda linha entra `status_revisao='PENDENTE'` com
evidencia `metodo_extracao='REGEX'`, e o motor a apresenta como
EXTRAIDO_AUTOMATICAMENTE, natureza POSSIVEL — nunca DOCUMENTADO. Uma frase
lida errado por expressao regular continua sendo frase lida errado, e quem
resolve isso e revisao farmaceutica, nao confianca no proprio codigo.

TRES GUARDAS DE PRECISAO
------------------------
1. O termo da condicao e o verbo de contraindicacao precisam estar na MESMA
   frase. Sem isso, "contraindicado em hipersensibilidade. Pacientes com
   diabetes devem monitorar a glicemia" viraria contraindicacao em diabetes.
2. Frase que diz que algo **nao foi estabelecido** ("a seguranca em criancas
   nao foi estabelecida") e ausencia de dado, nao contraindicacao: nao entra
   como alerta e vai para a contagem de nao-avaliado da carga.
3. "Nao deve ser utilizado ... **sem orientacao medica**" e precaucao, nao
   proibicao: vira USAR_COM_CAUTELA, e a distincao muda a prioridade.

A GRAVIDADE NAO E INVENTADA
---------------------------
A bula nao gradua. Toda linha entra `gravidade='NAO_DETERMINADA'`. O peso do
achado vem da RELACAO declarada (contraindicado x usar com cautela), que a
fonte de fato afirma — nunca de uma gravidade deduzida por script.

Uso: python pipeline/64_contraindicacoes_bula.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _comum import (ACERVO, abrir_carga, chaves_candidatas, conectar,  # noqa: E402
                    fechar_carga, id_fonte, resumo)

FONTE = "ANVISA - Bulario eletronico"
PASTA = "fontes_novas/01_anvisa_bulario/secoes"

# =====================================================================
# VOCABULARIO DE CONDICOES CLINICAS
#
# Escrito a mao, em portugues, e e o mesmo checklist que a anamnese da Fase 6
# vai usar. Nao e evidencia farmacologica: e a lista de coisas que o
# farmaceutico pergunta no balcao. Cada entrada tem os padroes de escrita que
# a bula realmente usa -- medidos no corpus, nao imaginados.
#
# (nome canonico, grupo, [padroes])
# =====================================================================
CONDICOES = [
    # --- cardiovascular ---
    ("hipertensão arterial", "Cardiovascular",
     [r"hipertens[ãa]o arterial", r"press[ãa]o (?:arterial )?(?:alta|elevada)"]),
    ("insuficiência cardíaca", "Cardiovascular",
     [r"insufici[êe]ncia card[íi]aca"]),
    ("doença arterial coronariana", "Cardiovascular",
     [r"doen[çc]a (?:card[íi]aca )?isqu[êe]mica", r"doen[çc]a arterial coronariana",
      r"insufici[êe]ncia coronariana", r"angina"]),
    ("infarto do miocárdio", "Cardiovascular", [r"infarto (?:do|agudo do) mioc[áa]rdio"]),
    ("arritmia cardíaca", "Cardiovascular",
     [r"arritmia", r"fibrila[çc][ãa]o atrial", r"prolongamento do (?:intervalo )?QT"]),
    ("bloqueio atrioventricular", "Cardiovascular",
     [r"bloqueio (?:atrioventricular|AV)"]),
    ("bradicardia", "Cardiovascular", [r"bradicardia"]),
    ("hipotensão", "Cardiovascular", [r"hipotens[ãa]o"]),
    ("acidente vascular cerebral", "Cardiovascular",
     [r"acidente vascular (?:cerebral|encef[áa]lico)", r"\bAVC\b"]),
    ("trombose", "Cardiovascular",
     [r"tromboembol", r"tromboflebite", r"trombose (?:venosa|arterial)?"]),
    # --- renal e hepatico ---
    ("insuficiência renal", "Renal e hepático",
     [r"insufici[êe]ncia renal", r"comprometimento renal",
      r"disfun[çc][ãa]o renal", r"doen[çc]a renal"]),
    ("insuficiência hepática", "Renal e hepático",
     [r"insufici[êe]ncia hep[áa]tica", r"comprometimento hep[áa]tico",
      r"disfun[çc][ãa]o hep[áa]tica", r"doen[çc]a hep[áa]tica", r"hepatopatia"]),
    ("cirrose hepática", "Renal e hepático", [r"cirrose"]),
    # --- metabolico e endocrino ---
    ("diabetes mellitus", "Metabólico e endócrino",
     [r"diabetes(?: mellitus)?", r"diab[ée]tic[oa]s?"]),
    ("hipotireoidismo", "Metabólico e endócrino", [r"hipotireoidismo"]),
    ("hipertireoidismo", "Metabólico e endócrino",
     [r"hipertireoidismo", r"tireotoxicose"]),
    ("dislipidemia", "Metabólico e endócrino",
     [r"dislipidemia", r"hipercolesterolemia", r"hipertriglicerid"]),
    ("hipercalemia", "Metabólico e endócrino", [r"hipercalemia", r"hiperpotassemia"]),
    ("hipocalemia", "Metabólico e endócrino", [r"hipocalemia", r"hipopotassemia"]),
    ("porfiria", "Metabólico e endócrino", [r"porfiria"]),
    ("fenilcetonúria", "Metabólico e endócrino", [r"fenilceton[úu]ria"]),
    ("obesidade", "Metabólico e endócrino", [r"obesidade"]),
    # --- respiratorio ---
    ("asma", "Respiratório", [r"\basma\b", r"asm[áa]tic"]),
    ("doença pulmonar obstrutiva crônica", "Respiratório",
     [r"doen[çc]a pulmonar obstrutiva", r"\bDPOC\b", r"enfisema"]),
    ("insuficiência respiratória", "Respiratório",
     [r"insufici[êe]ncia respirat[óo]ria", r"depress[ãa]o respirat[óo]ria"]),
    # --- digestivo ---
    ("úlcera péptica", "Digestivo",
     [r"[úu]lcera (?:p[ée]ptica|g[áa]strica|duodenal|gastroduodenal|gastrintestinal)"]),
    ("gastrite", "Digestivo", [r"gastrite"]),
    ("hemorragia digestiva", "Digestivo",
     [r"hemorragia (?:digestiva|gastrintestinal|gastrointestinal)",
      r"sangramento (?:digestivo|gastrintestinal)"]),
    ("doença inflamatória intestinal", "Digestivo",
     [r"doen[çc]a (?:de )?Crohn", r"retocolite", r"colite ulcerativa",
      r"doen[çc]a inflamat[óo]ria intestinal"]),
    ("obstrução intestinal", "Digestivo", [r"obstru[çc][ãa]o intestinal", r"[íi]leo paral"]),
    # --- neurologico e psiquiatrico ---
    ("epilepsia", "Neurológico e psiquiátrico",
     [r"epilepsia", r"epil[ée]ptic", r"convuls[õoã]"]),
    ("depressão", "Neurológico e psiquiátrico", [r"depress[ãa]o(?! respirat)"]),
    ("doença de Parkinson", "Neurológico e psiquiátrico", [r"(?:doen[çc]a de )?Parkinson"]),
    ("miastenia gravis", "Neurológico e psiquiátrico", [r"miastenia"]),
    ("glaucoma", "Neurológico e psiquiátrico", [r"glaucoma"]),
    ("enxaqueca", "Neurológico e psiquiátrico", [r"enxaqueca", r"migr[âa]nea"]),
    # --- hematologico ---
    ("anemia", "Hematológico", [r"anemia"]),
    ("discrasia sanguínea", "Hematológico",
     [r"discrasia", r"agranulocitose", r"neutropenia", r"aplasia medular"]),
    ("trombocitopenia", "Hematológico", [r"trombocitopenia", r"plaquetopenia"]),
    ("distúrbio de coagulação", "Hematológico",
     [r"dist[úu]rbio(?:s)? (?:de|da) coagula[çc][ãa]o", r"coagulopatia", r"hemofilia"]),
    # --- geniturinario ---
    ("hiperplasia prostática", "Geniturinário",
     [r"hiperplasia prost[áa]tica", r"hipertrofia prost[áa]tica"]),
    ("retenção urinária", "Geniturinário", [r"reten[çc][ãa]o urin[áa]ria"]),
    # --- imunologico e infeccioso ---
    ("lúpus eritematoso sistêmico", "Imunológico", [r"l[úu]pus"]),
    ("infecção ativa", "Infeccioso", [r"infec[çc][ãa]o(?:\s+\w+){0,2}\s+ativa"]),
    # --- estados fisiologicos que a anamnese registra ---
    ("gravidez", "Gestação e lactação",
     [r"gr[áa]vidas?", r"gesta[çc][ãa]o", r"gestantes?", r"gravidez"]),
    ("lactação", "Gestação e lactação",
     [r"lacta[çc][ãa]o", r"amamenta[çc][ãa]o", r"lactantes?", r"aleitamento"]),
]

CONDICOES_COMPILADAS = [
    (nome, grupo, re.compile("|".join(pats), re.IGNORECASE))
    for nome, grupo, pats in CONDICOES
]

# A fonte usou a palavra. Nao ha o que interpretar.
DIZ_CONTRAINDICADO = re.compile(r"contraindicad|contra-indicad", re.IGNORECASE)

# Formula padrao das bulas brasileiras de venda livre. Nao e proibicao.
SEM_ORIENTACAO = re.compile(r"sem orienta[çc][ãa]o m[ée]dica", re.IGNORECASE)

# Verbo que declara proibicao.
PROIBE = re.compile(
    r"contraindicad|contra-indicad|n[ãa]o (?:deve|devem|pode|podem) ser "
    r"(?:utilizad|administrad|usad|empregad)|n[ãa]o (?:utilizar|usar|administrar)|"
    r"n[ãa]o devem fazer uso", re.IGNORECASE)

# Verbo que declara precaucao, nao proibicao.
CAUTELA = re.compile(
    r"sem orienta[çc][ãa]o m[ée]dica|com (?:cautela|cuidado|precau[çc][ãa]o)|"
    r"deve ser (?:usado|utilizado) com|monitor|acompanhamento m[ée]dico|"
    r"avalia[çc][ãa]o (?:m[ée]dica|do m[ée]dico)", re.IGNORECASE)

# Frase que declara AUSENCIA de dado. Nao e contraindicacao nem precaucao.
NAO_ESTABELECIDO = re.compile(
    r"n[ãa]o (?:foi|foram|est[áa]|est[ãa]o) (?:estabelecid|determinad|avaliad)|"
    r"n[ãa]o h[áa] (?:dados|estudos|experi[êe]ncia)|"
    r"dados (?:s[ãa]o )?(?:insuficientes|limitados)", re.IGNORECASE)


def frases(texto: str):
    """Quebra o texto em frases e itens de lista.

    A bula usa ponto final, ponto e virgula e varios marcadores de bullet
    (•, -, −, –). Cada item de lista e uma afirmacao independente: separar
    por eles e o que garante a guarda 1 (termo e verbo na mesma frase).
    """
    if not texto:
        return []
    t = re.sub(r"\s+", " ", texto)
    partes = re.split(r"(?<=[.;])\s+|\s*[•−–—]\s*|\s+-\s+", t)
    return [p.strip() for p in partes if p and len(p.strip()) > 12]


def id_doenca(con, cache, nome, grupo):
    if nome in cache:
        return cache[nome]
    r = con.execute("SELECT id FROM doenca WHERE nome=?", (nome,)).fetchone()
    if r:
        cache[nome] = r[0]
        return r[0]
    cur = con.execute("INSERT INTO doenca (nome, grupo) VALUES (?,?)", (nome, grupo))
    cache[nome] = cur.lastrowid
    return cur.lastrowid


def indice(con):
    idx = defaultdict(set)
    for sid, chave in con.execute("SELECT id, chave_normalizada FROM substancia"):
        idx[chave].add(sid)
    for sid, chave in con.execute(
            "SELECT substancia_id, chave_normalizada FROM substancia_sinonimo"):
        idx[chave].add(sid)
    return idx


def main() -> int:
    con = conectar()
    if con.execute("SELECT COUNT(*) FROM interacao_doenca").fetchone()[0]:
        print("interacao_doenca ja carregada — nada a fazer")
        con.close()
        return 0

    pasta = ACERVO / PASTA
    arquivos = sorted(pasta.glob("*.json"))
    if not arquivos:
        print("ERRO: nenhuma secao de bula encontrada em %s" % pasta)
        con.close()
        return 1

    idx = indice(con)
    fonte_id = id_fonte(con, FONTE)
    carga_id = abrir_carga(con, FONTE, "pipeline/64_contraindicacoes_bula.py",
                           PASTA, "secoes extraidas de 150 bulas")

    cache_doenca = {}
    lidos = inseridos = sem_secao = sem_substancia = 0
    ambiguas = 0
    n_nao_estabelecido = 0
    por_relacao, por_condicao, por_grupo = (defaultdict(int), defaultdict(int),
                                            defaultdict(int))
    vistos = set()
    amostras = []

    for arq in arquivos:
        lidos += 1
        try:
            d = json.loads(arq.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        nome_subst = (d.get("substancia") or "").strip()
        secoes = d.get("secoes") or {}
        texto = secoes.get("contraindicacoes") or ""
        if not texto.strip():
            sem_secao += 1
            continue

        cand = set()
        for k in chaves_candidatas(nome_subst):
            cand |= idx.get(k, set())
        if len(cand) > 1:
            ambiguas += 1
            continue
        if not cand:
            sem_substancia += 1
            continue
        sid = next(iter(cand))

        for frase in frases(texto):
            proibe = bool(PROIBE.search(frase))
            cautela = bool(CAUTELA.search(frase))
            indefinido = bool(NAO_ESTABELECIDO.search(frase))
            if not (proibe or cautela):
                continue            # guarda 1: sem verbo, sem afirmacao
            if indefinido:
                # guarda 2: a bula esta dizendo que NAO SABE. Ausencia de
                # dado nunca vira regra.
                n_nao_estabelecido += 1
                continue
            # guarda 3: a PALAVRA da fonte manda. Se a bula escreveu
            # "contraindicado", e contraindicacao, ainda que a mesma frase
            # peca monitorizacao. So a formula brasileira de MIP
            # ("nao deve ser utilizado ... sem orientacao medica") rebaixa
            # para precaucao, porque ali a bula de fato nao proibe.
            if DIZ_CONTRAINDICADO.search(frase):
                relacao = "CONTRAINDICADO"
            elif SEM_ORIENTACAO.search(frase):
                relacao = "USAR_COM_CAUTELA"
            elif proibe:
                relacao = "CONTRAINDICADO"
            else:
                relacao = "USAR_COM_CAUTELA"

            for nome, grupo, rx in CONDICOES_COMPILADAS:
                if not rx.search(frase):
                    continue
                did = id_doenca(con, cache_doenca, nome, grupo)
                chave = (sid, did)
                if chave in vistos:
                    continue
                vistos.add(chave)
                trecho = frase[:600]
                cur = con.execute(
                    "INSERT OR IGNORE INTO interacao_doenca (substancia_id, doenca_id, "
                    "relacao, justificativa, trecho_origem, gravidade, origem, "
                    "fonte_id, status_revisao) VALUES (?,?,?,?,?,'NAO_DETERMINADA',"
                    "'BULA_ANVISA',?,'PENDENTE')",
                    (sid, did, relacao,
                     "Declarado na seção CONTRAINDICAÇÕES da bula registrada "
                     "na ANVISA.", trecho, fonte_id))
                if not cur.rowcount:
                    continue
                inseridos += 1
                por_relacao[relacao] += 1
                por_condicao[nome] += 1
                por_grupo[grupo] += 1
                con.execute(
                    "INSERT OR IGNORE INTO evidencia (tabela_alvo,id_alvo,fonte_id,"
                    "carga_id,documento,trecho,nivel_evidencia,metodo_extracao) "
                    "VALUES ('interacao_doenca',?,?,?,?,?,'RESPALDADA','REGEX')",
                    (cur.lastrowid, fonte_id, carga_id, arq.name, trecho))
                if len(amostras) < 8:
                    amostras.append((nome_subst, nome, relacao, trecho[:110]))

    fechar_carga(con, carga_id, lidos, inseridos,
                 sem_secao + sem_substancia + ambiguas,
                 "sem secao: %d; substancia nao casou: %d; ambiguas: %d; "
                 "frases de 'nao estabelecido' descartadas: %d"
                 % (sem_secao, sem_substancia, ambiguas, n_nao_estabelecido))
    con.commit()

    subs = con.execute("SELECT COUNT(DISTINCT substancia_id) FROM "
                       "interacao_doenca").fetchone()[0]
    resumo("FARMACO x DOENCA (bulas ANVISA)", [
        ("bulas lidas", lidos),
        ("sem seção de contraindicações", sem_secao),
        ("substância da bula não casou", sem_substancia),
        ("substância ambígua (não resolvida)", ambiguas),
        ("frases de 'não estabelecido' descartadas", n_nao_estabelecido),
        ("linhas inseridas", inseridos),
        ("substâncias cobertas", subs),
        ("condições distintas", len(por_condicao)),
        ("por relação", dict(por_relacao)),
    ])
    print("\n  por grupo de condição:")
    for g, n in sorted(por_grupo.items(), key=lambda x: -x[1]):
        print("    %-28s %d" % (g, n))
    print("\n  condições mais frequentes:")
    for c, n in sorted(por_condicao.items(), key=lambda x: -x[1])[:12]:
        print("    %-34s %d" % (c, n))
    print("\n  amostra do trecho que gerou a linha:")
    for s, c, r, t in amostras:
        print("    %-24s %-24s %-17s %s" % (s[:24], c[:24], r, t))
    print("\n  TODAS as %d linhas estão PENDENTE de revisão farmacêutica e"
          "\n  entram no relatório como EXTRAIDO_AUTOMATICAMENTE, nunca como"
          "\n  documentado. A gravidade fica NAO_DETERMINADA: a bula não gradua."
          % inseridos)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
