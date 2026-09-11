# -*- coding: utf-8 -*-
"""
CAMADA DE SERVICOS — tudo que escreve no atendimento, e a orquestracao.

    INTERFACE (app/web.py)
        v
    SERVICOS (este arquivo, app/busca.py, app/relatorio.py)
        v
    MOTORES  (rules/motor_horarios.py, rules/motor_conciliacao.py)
        v
    BANCO    (database/conciliador.db)

REGRA DA CAMADA, e ela e a razao de este arquivo existir:

  - `web.py` NAO tem uma linha de SQL clinico. Todo acesso ao conhecimento
    farmacologico passa por `busca.py` ou pelos motores.
  - Este arquivo NAO decide nada clinico. Ele grava o que o farmaceutico
    informou e chama quem sabe avaliar.
  - Nenhuma regra dos motores e reimplementada aqui. Se a tela precisar de
    algo que o motor nao devolve, o certo e ampliar o contrato do motor —
    nao recalcular por fora.

O QUE ESTE ARQUIVO NUNCA FAZ
----------------------------
  - nao escreve gravidade, prioridade nem confianca: sao do motor;
  - nao decide intencionalidade de divergencia sem nome de profissional;
  - nao preenche dado ausente com valor padrao: `None` fica `None`, e a
    ausencia e exibida como ausencia;
  - nao altera prescricao, dose nem horario do paciente por conta propria.

ASSOCIACAO EM DOSE FIXA
-----------------------
Um produto pode ter mais de uma substancia (losartana + hidroclorotiazida).
`adicionar_medicamento` grava **uma linha por componente**, com o mesmo
`nome_relatado`, porque o modulo de interacao precisa enxergar os dois lados.
Para o farmaceutico continua sendo um item so: as telas agrupam por
`nome_relatado`, e a posologia informada uma vez vale para o grupo inteiro.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

RAIZ = Path(__file__).resolve().parent.parent
for _p in ("pipeline", "rules", "app"):
    sys.path.insert(0, str(RAIZ / _p))

import caminhos                                     # noqa: E402
from motor_conciliacao import conciliar_atendimento  # noqa: E402
from motor_horarios import montar_agenda             # noqa: E402

# O caminho do banco e decidido em `app/caminhos.py`, nunca aqui: num `.exe`
# ele fica na pasta de dados do usuario, e nao ao lado do codigo. Em
# desenvolvimento o valor e exatamente o de sempre.
BANCO = caminhos.banco()

HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

EVENTOS_ROTINA = [
    ("ACORDAR", "Acordar"), ("CAFE_MANHA", "Café da manhã"),
    ("LANCHE_MANHA", "Lanche da manhã"), ("ALMOCO", "Almoço"),
    ("LANCHE_TARDE", "Lanche da tarde"), ("JANTAR", "Jantar"),
    ("CEIA", "Ceia"), ("DORMIR", "Dormir"),
    ("TRABALHO_INICIO", "Início do trabalho"), ("TRABALHO_FIM", "Fim do trabalho"),
    ("ESCOLA_INICIO", "Início da escola"), ("ESCOLA_FIM", "Fim da escola"),
]

HABITOS = [
    ("TABAGISMO", "Tabagismo"), ("ALCOOL", "Bebida alcoólica"),
    ("CAFEINA", "Café ou outras fontes de cafeína"),
    ("ENERGETICO", "Energéticos"), ("SUPLEMENTO", "Suplementos"),
    ("CHA_PLANTA", "Chás e plantas"), ("AUTOMEDICACAO", "Automedicação"),
    ("MIP_FREQUENTE", "Uso frequente de medicamento isento de prescrição"),
]

SITUACOES_HABITO = [("ATUAL", "Sim, atualmente"), ("EX", "Já teve, hoje não"),
                    ("NUNCA", "Nunca"), ("NAO_INFORMADO", "Não informado")]

LISTAS = [("PRESCRITA", "Prescrito (receita apresentada)"),
          ("RELATADA", "Relatado pelo paciente"),
          ("EM_USO", "Confirmado em uso"),
          ("ANTERIOR", "Uso anterior / suspenso"),
          ("HISTORICO", "Histórico de atendimento anterior")]

ORIGENS = [("PRESCRITO", "Prescrito por profissional"),
           ("AUTOMEDICACAO", "Automedicação"),
           ("MIP", "Medicamento isento de prescrição"),
           ("SUPLEMENTO", "Suplemento"), ("FITOTERAPICO", "Fitoterápico"),
           ("NAO_INFORMADO", "Não informado")]


class ErroDeUso(ValueError):
    """Entrada invalida do usuario. A interface mostra a mensagem como esta.

    Distinta de erro tecnico: esta e culpa do formulario, nao do sistema, e o
    texto foi escrito para ser lido por uma pessoa.
    """


# =====================================================================
# CONEXAO
# =====================================================================
def conectar() -> sqlite3.Connection:
    if not BANCO.exists():
        raise FileNotFoundError(
            "O banco não foi encontrado em %s. Rode "
            "'python pipeline/executar_tudo.py --recriar' antes de abrir a "
            "aplicação." % BANCO)
    con = sqlite3.connect(BANCO, timeout=15)
    con.execute("PRAGMA foreign_keys = ON")
    return con


# =====================================================================
# ATENDIMENTO
# =====================================================================
def novo_codigo(con) -> str:
    hoje = _dt.date.today().strftime("%Y%m%d")
    n = con.execute("SELECT COUNT(*) FROM atendimento WHERE codigo LIKE ?",
                    (hoje + "-%",)).fetchone()[0]
    for tentativa in range(n + 1, n + 500):
        codigo = "%s-%03d" % (hoje, tentativa)
        if not con.execute("SELECT 1 FROM atendimento WHERE codigo=?",
                           (codigo,)).fetchone():
            return codigo
    raise ErroDeUso("Não foi possível gerar um código de atendimento hoje.")


def criar_atendimento(con, nome_paciente: str, farmaceutico: str = None,
                      crf: str = None) -> str:
    nome = (nome_paciente or "").strip()
    if not nome:
        raise ErroDeUso("Informe o nome do paciente para iniciar o atendimento.")
    cur = con.execute("INSERT INTO paciente (nome) VALUES (?)", (nome,))
    codigo = novo_codigo(con)
    con.execute("INSERT INTO atendimento (paciente_id, codigo, farmaceutico, crf) "
                "VALUES (?,?,?,?)",
                (cur.lastrowid, codigo, (farmaceutico or "").strip() or None,
                 (crf or "").strip() or None))
    con.commit()
    return codigo


def obter_atendimento(con, codigo: str) -> Optional[dict]:
    r = con.execute(
        "SELECT a.id, a.codigo, a.farmaceutico, a.crf, a.iniciado_em, "
        "a.concluido_em, a.situacao, p.id, p.nome, p.data_nascimento, p.sexo, "
        "p.peso_kg, p.altura_cm, p.contato, p.observacao "
        "FROM atendimento a JOIN paciente p ON p.id = a.paciente_id "
        "WHERE a.codigo = ?", (codigo,)).fetchone()
    if not r:
        return None
    d = dict(zip(("id", "codigo", "farmaceutico", "crf", "iniciado_em",
                  "concluido_em", "situacao", "paciente_id", "nome",
                  "data_nascimento", "sexo", "peso_kg", "altura_cm", "contato",
                  "observacao"), r))
    d["idade"] = _idade(d["data_nascimento"])
    return d


def exigir_atendimento(con, codigo: str) -> dict:
    at = obter_atendimento(con, codigo)
    if at is None:
        raise ErroDeUso("Atendimento %s não encontrado." % codigo)
    return at


def listar_atendimentos(con, limite: int = 50) -> list:
    return [dict(zip(("codigo", "nome", "iniciado_em", "situacao",
                      "n_medicamentos", "n_achados"), r))
            for r in con.execute(
                "SELECT a.codigo, p.nome, a.iniciado_em, a.situacao, "
                "(SELECT COUNT(DISTINCT nome_relatado) FROM atendimento_medicamento m "
                " WHERE m.atendimento_id = a.id), "
                "(SELECT c.n_achados FROM conciliacao c WHERE c.atendimento_id = a.id "
                " ORDER BY c.id DESC LIMIT 1) "
                "FROM atendimento a JOIN paciente p ON p.id = a.paciente_id "
                "ORDER BY a.id DESC LIMIT ?", (limite,))]


def concluir_atendimento(con, codigo: str) -> None:
    at = exigir_atendimento(con, codigo)
    con.execute("UPDATE atendimento SET situacao='CONCLUIDO', "
                "concluido_em=datetime('now') WHERE id=?", (at["id"],))
    con.commit()


def reabrir_atendimento(con, codigo: str) -> None:
    at = exigir_atendimento(con, codigo)
    con.execute("UPDATE atendimento SET situacao='EM_ANDAMENTO', "
                "concluido_em=NULL WHERE id=?", (at["id"],))
    con.commit()


# =====================================================================
# PACIENTE
# =====================================================================
def salvar_paciente(con, codigo: str, nome: str, data_nascimento: str = None,
                    sexo: str = None, peso_kg: str = None,
                    altura_cm: str = None, contato: str = None,
                    observacao: str = None, farmaceutico: str = None,
                    crf: str = None) -> None:
    at = exigir_atendimento(con, codigo)
    nome = (nome or "").strip()
    if not nome:
        raise ErroDeUso("O nome do paciente é obrigatório.")
    nasc = _validar_data(data_nascimento, "data de nascimento")
    if nasc and _dt.date.fromisoformat(nasc) > _dt.date.today():
        raise ErroDeUso("A data de nascimento não pode ser no futuro.")
    peso = _validar_numero(peso_kg, "peso", 0.5, 400)
    altura = _validar_numero(altura_cm, "altura", 30, 250)
    if sexo not in (None, "", "F", "M", "OUTRO", "NAO_INFORMADO"):
        raise ErroDeUso("Sexo inválido.")
    con.execute(
        "UPDATE paciente SET nome=?, data_nascimento=?, sexo=?, peso_kg=?, "
        "altura_cm=?, contato=?, observacao=? WHERE id=?",
        (nome, nasc, sexo or "NAO_INFORMADO", peso, altura,
         _limpo(contato), _limpo(observacao), at["paciente_id"]))
    con.execute("UPDATE atendimento SET farmaceutico=?, crf=? WHERE id=?",
                (_limpo(farmaceutico), _limpo(crf), at["id"]))
    con.commit()


# =====================================================================
# CONDICOES CLINICAS
# =====================================================================
def listar_condicoes(con, codigo: str) -> list:
    at = exigir_atendimento(con, codigo)
    return [dict(zip(("id", "doenca_id", "nome", "grupo", "descricao_livre",
                      "desde"), r))
            for r in con.execute(
                "SELECT pc.id, pc.doenca_id, d.nome, d.grupo, "
                "pc.descricao_livre, pc.desde FROM paciente_condicao pc "
                "LEFT JOIN doenca d ON d.id = pc.doenca_id "
                "WHERE pc.paciente_id=? ORDER BY d.grupo, d.nome, pc.id",
                (at["paciente_id"],))]


def adicionar_condicao(con, codigo: str, doenca_id=None, descricao_livre=None,
                       desde=None) -> None:
    at = exigir_atendimento(con, codigo)
    doenca_id = _inteiro(doenca_id)
    livre = _limpo(descricao_livre)
    if doenca_id is None and not livre:
        raise ErroDeUso("Escolha uma condição da lista ou descreva-a.")
    if doenca_id is not None:
        if not con.execute("SELECT 1 FROM doenca WHERE id=?",
                           (doenca_id,)).fetchone():
            raise ErroDeUso("Condição não encontrada no cadastro.")
        ja = con.execute("SELECT 1 FROM paciente_condicao WHERE paciente_id=? "
                         "AND doenca_id=?", (at["paciente_id"], doenca_id)
                         ).fetchone()
        if ja:
            raise ErroDeUso("Esta condição já está registrada.")
    con.execute("INSERT INTO paciente_condicao (paciente_id, doenca_id, "
                "descricao_livre, desde) VALUES (?,?,?,?)",
                (at["paciente_id"], doenca_id, livre,
                 _validar_data(desde, "data de início")))
    con.commit()


def remover_condicao(con, codigo: str, condicao_id: int) -> None:
    at = exigir_atendimento(con, codigo)
    con.execute("DELETE FROM paciente_condicao WHERE id=? AND paciente_id=?",
                (_inteiro(condicao_id), at["paciente_id"]))
    con.commit()


# =====================================================================
# ALERGIAS
# =====================================================================
GRAVIDADES_ALERGIA = [("ANAFILAXIA", "Anafilaxia"), ("GRAVE", "Grave"),
                      ("MODERADA", "Moderada"), ("LEVE", "Leve"),
                      ("NAO_INFORMADA", "Não informada")]


def listar_alergias(con, codigo: str) -> list:
    at = exigir_atendimento(con, codigo)
    return [dict(zip(("id", "substancia_id", "substancia", "descricao_livre",
                      "reacao", "gravidade"), r))
            for r in con.execute(
                "SELECT pa.id, pa.substancia_id, s.nome_dcb, pa.descricao_livre, "
                "pa.reacao, pa.gravidade FROM paciente_alergia pa "
                "LEFT JOIN substancia s ON s.id = pa.substancia_id "
                "WHERE pa.paciente_id=? ORDER BY pa.id",
                (at["paciente_id"],))]


def adicionar_alergia(con, codigo: str, substancia_id=None,
                      descricao_livre=None, reacao=None,
                      gravidade="NAO_INFORMADA") -> None:
    at = exigir_atendimento(con, codigo)
    sid = _inteiro(substancia_id)
    livre = _limpo(descricao_livre)
    if sid is None and not livre:
        raise ErroDeUso("Escolha a substância na busca ou descreva a alergia.")
    if sid is not None and not con.execute(
            "SELECT 1 FROM substancia WHERE id=?", (sid,)).fetchone():
        raise ErroDeUso("Substância não encontrada no cadastro.")
    if gravidade not in dict(GRAVIDADES_ALERGIA):
        gravidade = "NAO_INFORMADA"
    if sid is not None and con.execute(
            "SELECT 1 FROM paciente_alergia WHERE paciente_id=? AND "
            "substancia_id=?", (at["paciente_id"], sid)).fetchone():
        raise ErroDeUso("Esta alergia já está registrada.")
    con.execute("INSERT INTO paciente_alergia (paciente_id, substancia_id, "
                "descricao_livre, reacao, gravidade) VALUES (?,?,?,?,?)",
                (at["paciente_id"], sid, livre, _limpo(reacao), gravidade))
    con.commit()


def remover_alergia(con, codigo: str, alergia_id: int) -> None:
    at = exigir_atendimento(con, codigo)
    con.execute("DELETE FROM paciente_alergia WHERE id=? AND paciente_id=?",
                (_inteiro(alergia_id), at["paciente_id"]))
    con.commit()


# =====================================================================
# HABITOS
# =====================================================================
def listar_habitos(con, codigo: str) -> dict:
    at = exigir_atendimento(con, codigo)
    return {h: dict(zip(("situacao", "quantidade", "frequencia"), r))
            for h, *r in con.execute(
                "SELECT habito, situacao, quantidade, frequencia "
                "FROM paciente_habito WHERE paciente_id=?",
                (at["paciente_id"],))}


def salvar_habito(con, codigo: str, habito: str, situacao: str,
                  quantidade=None, frequencia=None) -> None:
    at = exigir_atendimento(con, codigo)
    if habito not in dict(HABITOS):
        raise ErroDeUso("Hábito desconhecido: %s" % habito)
    if situacao not in dict(SITUACOES_HABITO):
        raise ErroDeUso("Situação inválida para o hábito.")
    con.execute(
        "INSERT INTO paciente_habito (paciente_id, habito, situacao, "
        "quantidade, frequencia) VALUES (?,?,?,?,?) "
        "ON CONFLICT (paciente_id, habito) DO UPDATE SET situacao=excluded.situacao, "
        "quantidade=excluded.quantidade, frequencia=excluded.frequencia",
        (at["paciente_id"], habito, situacao, _limpo(quantidade),
         _limpo(frequencia)))
    con.commit()


# =====================================================================
# MEDICAMENTOS
# =====================================================================
@dataclass
class GrupoMedicamento:
    """Um item de farmacoterapia como o farmaceutico o enxerga.

    Uma associacao em dose fixa sao varias linhas no banco (uma por
    componente) e UM cartao na tela. `ids` traz todas as linhas; `grupo_id` e
    a menor delas e serve de identificador estavel na URL.
    """
    grupo_id: int
    ids: list
    nome_relatado: str
    lista: str
    origem: str
    reconhecimento: str
    confianca: Optional[str]
    apresentacao_id: Optional[int]
    substancias: list = field(default_factory=list)
    posologia: Optional[dict] = None
    horarios: list = field(default_factory=list)

    @property
    def reconhecido(self) -> bool:
        return self.reconhecimento != "NAO_RECONHECIDO"

    @property
    def tem_posologia(self) -> bool:
        return self.posologia is not None

    def resumo_posologia(self) -> str:
        if not self.posologia:
            return "posologia não informada"
        p = self.posologia
        partes = []
        if p["dose_valor"] is not None:
            partes.append("%g %s" % (p["dose_valor"], p["dose_unidade"] or ""))
        else:
            partes.append("dose não informada")
        if p["vezes_por_dia"]:
            partes.append("%dx/dia" % p["vezes_por_dia"])
        elif p["intervalo_horas"]:
            partes.append("a cada %g h" % p["intervalo_horas"])
        if p["se_necessario"]:
            partes.append("se necessário")
        if self.horarios:
            partes.append(", ".join(self.horarios))
        return " · ".join(partes)


def listar_medicamentos(con, codigo: str, lista: str = None) -> list:
    at = exigir_atendimento(con, codigo)
    sql = ("SELECT am.id, am.nome_relatado, am.lista, am.origem, "
           "am.reconhecimento, am.confianca_reconhecimento, am.apresentacao_id, "
           "am.substancia_id, s.nome_dcb, po.id "
           "FROM atendimento_medicamento am "
           "LEFT JOIN substancia s ON s.id = am.substancia_id "
           "LEFT JOIN posologia po ON po.atendimento_medicamento_id = am.id "
           "WHERE am.atendimento_id = ?")
    args = [at["id"]]
    if lista:
        sql += " AND am.lista = ?"
        args.append(lista)
    sql += " ORDER BY am.id"

    grupos = {}
    for (am_id, nome, lst, origem, rec, conf, apres, sid, dcb,
         pos_id) in con.execute(sql, args):
        chave = (lst, nome, apres)
        g = grupos.get(chave)
        if g is None:
            g = GrupoMedicamento(
                grupo_id=am_id, ids=[], nome_relatado=nome, lista=lst,
                origem=origem, reconhecimento=rec, confianca=conf,
                apresentacao_id=apres)
            grupos[chave] = g
        g.ids.append(am_id)
        if sid:
            g.substancias.append((sid, dcb))
        if pos_id and g.posologia is None:
            g.posologia = _ler_posologia(con, pos_id)
            g.horarios = [h for (h,) in con.execute(
                "SELECT hora FROM horario_administracao WHERE posologia_id=? "
                "ORDER BY hora", (pos_id,))]
    return list(grupos.values())


def obter_grupo(con, codigo: str, grupo_id: int) -> GrupoMedicamento:
    for g in listar_medicamentos(con, codigo):
        if g.grupo_id == int(grupo_id):
            return g
    raise ErroDeUso("Medicamento não encontrado neste atendimento.")


def adicionar_medicamento(con, codigo: str, nome_relatado: str,
                          escolha: str = None, lista: str = "RELATADA",
                          origem: str = "PRESCRITO") -> int:
    """Grava um item. `escolha` vem da busca: 'apresentacao:<id>',
    'substancia:<id>' ou vazio (o farmaceutico digitou e nada casou).

    Devolve o `grupo_id`. Associacao em dose fixa vira **uma linha por
    componente**, com o mesmo `nome_relatado`.
    """
    at = exigir_atendimento(con, codigo)
    nome = (nome_relatado or "").strip()
    if not nome:
        raise ErroDeUso("Informe o nome do medicamento.")
    if lista not in dict(LISTAS):
        raise ErroDeUso("Lista inválida.")
    if origem not in dict(ORIGENS):
        raise ErroDeUso("Origem inválida.")

    apresentacao_id, substancias, reconhecimento, confianca = _resolver_escolha(
        con, escolha)

    ja = con.execute(
        "SELECT id FROM atendimento_medicamento WHERE atendimento_id=? "
        "AND nome_relatado=? AND lista=? AND "
        "(apresentacao_id IS ? OR apresentacao_id = ?)",
        (at["id"], nome, lista, apresentacao_id, apresentacao_id)).fetchone()
    if ja:
        raise ErroDeUso("%s já está na lista %s deste atendimento."
                        % (nome, dict(LISTAS)[lista]))

    if not substancias:
        substancias = [None]
    ids = []
    for sid in substancias:
        cur = con.execute(
            "INSERT INTO atendimento_medicamento (atendimento_id, substancia_id, "
            "apresentacao_id, nome_relatado, origem, lista, reconhecimento, "
            "confianca_reconhecimento) VALUES (?,?,?,?,?,?,?,?)",
            (at["id"], sid, apresentacao_id, nome, origem, lista,
             reconhecimento, confianca))
        ids.append(cur.lastrowid)
    con.commit()
    return min(ids)


def _resolver_escolha(con, escolha: str):
    """'apresentacao:<id>' | 'substancia:<id>' | vazio -> (apres, [sids], rec, conf)."""
    escolha = (escolha or "").strip()
    if escolha.startswith("apresentacao:"):
        apres = _inteiro(escolha.split(":", 1)[1])
        if not con.execute("SELECT 1 FROM apresentacao WHERE id=?",
                           (apres,)).fetchone():
            raise ErroDeUso("Apresentação não encontrada.")
        sids = [s for (s,) in con.execute(
            "SELECT substancia_id FROM apresentacao_substancia "
            "WHERE apresentacao_id=?", (apres,))]
        # Apresentacao sem vinculo de substancia existe (118 casos medidos na
        # Fase 2). Nao e erro: e ausencia, e vai declarada.
        return apres, sids, ("EAN" if sids else "MANUAL"), ("ALTA" if sids
                                                            else "BAIXA")
    if escolha.startswith("substancia:"):
        sid = _inteiro(escolha.split(":", 1)[1])
        if not con.execute("SELECT 1 FROM substancia WHERE id=?",
                           (sid,)).fetchone():
            raise ErroDeUso("Substância não encontrada.")
        return None, [sid], "NOME_EXATO", "ALTA"
    # O farmaceutico digitou e nao escolheu nada da lista. O item entra
    # NAO_RECONHECIDO — e o motor declara que nenhum modulo o avaliou.
    return None, [], "NAO_RECONHECIDO", None


def remover_medicamento(con, codigo: str, grupo_id: int) -> None:
    g = obter_grupo(con, codigo, grupo_id)
    marca = ",".join("?" * len(g.ids))
    con.execute("DELETE FROM atendimento_medicamento WHERE id IN (%s)" % marca,
                g.ids)
    con.commit()


def mover_medicamento(con, codigo: str, grupo_id: int, lista: str) -> None:
    """Move o item para outra lista (ex.: relatado -> confirmado em uso)."""
    if lista not in dict(LISTAS):
        raise ErroDeUso("Lista inválida.")
    g = obter_grupo(con, codigo, grupo_id)
    marca = ",".join("?" * len(g.ids))
    con.execute("UPDATE atendimento_medicamento SET lista=? WHERE id IN (%s)"
                % marca, [lista] + g.ids)
    con.commit()


# =====================================================================
# POSOLOGIA
# =====================================================================
def salvar_posologia(con, codigo: str, grupo_id: int, dose_valor=None,
                     dose_unidade=None, vezes_por_dia=None,
                     intervalo_horas=None, via_administracao=None,
                     duracao_dias=None, data_inicio=None,
                     data_fim_prevista=None, uso_continuo=False,
                     se_necessario=False, condicao_uso=None,
                     texto_original=None, horarios=None) -> None:
    """Grava a posologia do grupo inteiro.

    TODO campo pode ser desconhecido, e desconhecido fica `None` — a
    especificacao e explicita: melhor 'não informado' do que um valor
    inventado. O unico par que o esquema recusa e uso continuo com data de
    fim prevista, porque as duas coisas se contradizem.
    """
    g = obter_grupo(con, codigo, grupo_id)

    dose = _validar_numero(dose_valor, "dose", 0, 100000, permitir_zero=True)
    vezes = _inteiro(vezes_por_dia)
    if vezes is not None and not (1 <= vezes <= 12):
        raise ErroDeUso("A frequência precisa estar entre 1 e 12 vezes por dia.")
    intervalo = _validar_numero(intervalo_horas, "intervalo", 0.5, 168)
    duracao = _inteiro(duracao_dias)
    if duracao is not None and duracao < 1:
        raise ErroDeUso("A duração precisa ser de pelo menos um dia.")
    inicio = _validar_data(data_inicio, "data de início")
    fim = _validar_data(data_fim_prevista, "data de término")
    if inicio and fim and fim < inicio:
        raise ErroDeUso("A data de término é anterior à data de início.")
    continuo = 1 if uso_continuo else 0
    prn = 1 if se_necessario else 0
    if continuo and fim:
        raise ErroDeUso("Uso contínuo não combina com data de término "
                        "prevista. Escolha um dos dois.")

    horas = []
    for h in (horarios or []):
        h = (h or "").strip()
        if not h:
            continue
        if not HORA.match(h):
            raise ErroDeUso("Horário inválido: %r. Use o formato HH:MM, "
                            "entre 00:00 e 23:59." % h)
        if h in horas:
            raise ErroDeUso("O horário %s foi informado duas vezes." % h)
        horas.append(h)
    if vezes is not None and horas and len(horas) != vezes:
        # NAO e erro: o motor detecta e explica. Aqui so nao impedimos.
        pass

    for am_id in g.ids:
        con.execute("DELETE FROM posologia WHERE atendimento_medicamento_id=?",
                    (am_id,))
        cur = con.execute(
            "INSERT INTO posologia (atendimento_medicamento_id, dose_valor, "
            "dose_unidade, vezes_por_dia, intervalo_horas, via_administracao, "
            "duracao_dias, data_inicio, data_fim_prevista, uso_continuo, "
            "se_necessario, condicao_uso, texto_original) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (am_id, dose, _limpo(dose_unidade), vezes, intervalo,
             _limpo(via_administracao), duracao, inicio, fim, continuo, prn,
             _limpo(condicao_uso), _limpo(texto_original)))
        for h in sorted(horas):
            con.execute("INSERT INTO horario_administracao (posologia_id, hora, "
                        "definido_por) VALUES (?,?,'FARMACEUTICO')",
                        (cur.lastrowid, h))
    con.commit()


def _ler_posologia(con, pos_id: int) -> dict:
    r = con.execute(
        "SELECT dose_valor, dose_unidade, vezes_por_dia, intervalo_horas, "
        "via_administracao, duracao_dias, data_inicio, data_fim_prevista, "
        "uso_continuo, se_necessario, condicao_uso, texto_original "
        "FROM posologia WHERE id=?", (pos_id,)).fetchone()
    return dict(zip(("dose_valor", "dose_unidade", "vezes_por_dia",
                     "intervalo_horas", "via_administracao", "duracao_dias",
                     "data_inicio", "data_fim_prevista", "uso_continuo",
                     "se_necessario", "condicao_uso", "texto_original"), r))


# =====================================================================
# ROTINA
# =====================================================================
def listar_rotina(con, codigo: str) -> dict:
    at = exigir_atendimento(con, codigo)
    return {e: h for e, h in con.execute(
        "SELECT evento, hora FROM rotina_paciente WHERE atendimento_id=?",
        (at["id"],))}


def salvar_rotina(con, codigo: str, valores: dict) -> None:
    at = exigir_atendimento(con, codigo)
    validos = dict(EVENTOS_ROTINA)
    for evento, hora in (valores or {}).items():
        if evento not in validos:
            continue
        hora = (hora or "").strip()
        if not hora:
            con.execute("DELETE FROM rotina_paciente WHERE atendimento_id=? "
                        "AND evento=?", (at["id"], evento))
            continue
        if not HORA.match(hora):
            raise ErroDeUso("Horário inválido em %s: %r. Use HH:MM."
                            % (validos[evento], hora))
        con.execute(
            "INSERT INTO rotina_paciente (atendimento_id, evento, hora) "
            "VALUES (?,?,?) ON CONFLICT (atendimento_id, evento) "
            "DO UPDATE SET hora=excluded.hora", (at["id"], evento, hora))
    con.commit()


# =====================================================================
# ITENS: ALIMENTOS, PLANTAS, SUPLEMENTOS
# =====================================================================
FREQUENCIAS_ITEM = [("DIARIO", "Diário"), ("SEMANAL", "Semanal"),
                    ("OCASIONAL", "Ocasional"), ("RARO", "Raro"),
                    ("NAO_INFORMADA", "Não informada")]


def listar_itens(con, codigo: str) -> list:
    at = exigir_atendimento(con, codigo)
    return [dict(zip(("id", "item_id", "nome", "tipo", "nome_relatado",
                      "frequencia", "horario_habitual"), r))
            for r in con.execute(
                "SELECT ai.id, ai.item_id, i.nome, i.tipo, ai.nome_relatado, "
                "ai.frequencia, ai.horario_habitual FROM atendimento_item ai "
                "LEFT JOIN item_nao_medicamentoso i ON i.id = ai.item_id "
                "WHERE ai.atendimento_id=? ORDER BY ai.id", (at["id"],))]


def adicionar_item(con, codigo: str, item_id=None, nome_relatado=None,
                   frequencia="NAO_INFORMADA", horario_habitual=None) -> None:
    at = exigir_atendimento(con, codigo)
    iid = _inteiro(item_id)
    nome = _limpo(nome_relatado)
    if iid is not None:
        r = con.execute("SELECT nome FROM item_nao_medicamentoso WHERE id=?",
                        (iid,)).fetchone()
        if not r:
            raise ErroDeUso("Item não encontrado no cadastro.")
        nome = nome or r[0]
        if con.execute("SELECT 1 FROM atendimento_item WHERE atendimento_id=? "
                       "AND item_id=?", (at["id"], iid)).fetchone():
            raise ErroDeUso("%s já está registrado neste atendimento." % r[0])
    if not nome:
        raise ErroDeUso("Escolha um item da lista ou informe o nome.")
    if frequencia not in dict(FREQUENCIAS_ITEM):
        frequencia = "NAO_INFORMADA"
    horario = _limpo(horario_habitual)
    if horario and not HORA.match(horario):
        raise ErroDeUso("Horário inválido: %r. Use HH:MM." % horario)
    con.execute("INSERT INTO atendimento_item (atendimento_id, item_id, "
                "nome_relatado, frequencia, horario_habitual) VALUES (?,?,?,?,?)",
                (at["id"], iid, nome, frequencia, horario))
    con.commit()


def remover_item(con, codigo: str, registro_id: int) -> None:
    at = exigir_atendimento(con, codigo)
    con.execute("DELETE FROM atendimento_item WHERE id=? AND atendimento_id=?",
                (_inteiro(registro_id), at["id"]))
    con.commit()


# =====================================================================
# ANALISE — a orquestracao
# =====================================================================
def analisar(con, codigo: str, persistir: bool = True):
    """Chama o motor de conciliacao. Ponto.

    Nenhuma regra e reimplementada aqui: o que esta funcao faz alem de chamar
    o motor e (a) reaplicar as decisoes que o profissional ja registrou e
    (b) gravar o resultado. As duas coisas sao persistencia, nao avaliacao.
    """
    at = exigir_atendimento(con, codigo)
    if not listar_medicamentos(con, codigo):
        raise ErroDeUso("Não há nenhum medicamento registrado neste "
                        "atendimento. Acrescente ao menos um antes de analisar.")
    res = conciliar_atendimento(con, at["id"], persistir=persistir)
    if persistir:
        _reaplicar_anotacoes(con, at["id"], res)
        con.commit()
    return res


def resultado_atual(con, codigo: str):
    """Resultado recalculado por leitura, sem gravar.

    A tela usa isto: se o dado do paciente mudou, o resultado muda junto —
    mesma decisao da agenda da Fase 4.
    """
    at = exigir_atendimento(con, codigo)
    return conciliar_atendimento(con, at["id"], persistir=False)


def montar_agenda_do_atendimento(con, codigo: str):
    at = exigir_atendimento(con, codigo)
    return montar_agenda(con, at["id"])


def ultima_conciliacao(con, codigo: str) -> Optional[dict]:
    at = exigir_atendimento(con, codigo)
    r = con.execute(
        "SELECT id, executada_em, versao_motor, n_achados FROM conciliacao "
        "WHERE atendimento_id=? ORDER BY id DESC LIMIT 1", (at["id"],)).fetchone()
    return dict(zip(("id", "executada_em", "versao_motor", "n_achados"), r)) \
        if r else None


# =====================================================================
# ANOTACAO DO PROFISSIONAL
# =====================================================================
def chave_divergencia(par) -> str:
    """Chave ESTAVEL de uma divergencia: sobrevive a uma reanalise."""
    return "%s|%s" % (par.tipo_divergencia or "SEM_TIPO",
                      par.substancia_id if par.substancia_id is not None
                      else par.nome_exibicao)


def detalhe_previsao(con, origem_afirmacao: str) -> dict | None:
    """Tudo o que sustenta um achado PREVISTO, a partir de 'predicao.<id>'.

    A tela nao tem SQL (D-036) e o motor nao carrega modelo: a rastreabilidade
    da previsao chega por aqui, seguindo o ponteiro `origem_afirmacao` ate a
    view que ja aplica as travas de homologacao. Se o modelo for desativado
    depois de o achado ter sido gravado, esta funcao devolve None e a tela diz
    que a previsao nao esta mais liberada — em vez de exibir um numero orfao.
    """
    if not (origem_afirmacao or "").startswith("predicao."):
        return None
    try:
        pid = int(origem_afirmacao.split(".", 1)[1])
    except (ValueError, IndexError):
        return None
    colunas = ("predicao_id", "probabilidade", "probabilidade_calibrada",
               "probabilidade_exibida", "explicacao_json", "criado_em",
               "status_predicao", "revisado_por", "modelo_nome",
               "modelo_versao", "algoritmo", "n_features",
               "protocolo_validacao", "limiar_alerta", "limitacoes",
               "versao_dados", "semente")
    r = con.execute(
        "SELECT %s FROM vw_predicao_liberada WHERE predicao_id=?"
        % ",".join(colunas), (pid,)).fetchone()
    if r is None:
        return None
    d = dict(zip(colunas, r))
    try:
        d["fatores"] = json.loads(d["explicacao_json"] or "[]")
    except (ValueError, TypeError):
        d["fatores"] = []
    return d


def listar_anotacoes(con, codigo: str) -> dict:
    at = exigir_atendimento(con, codigo)
    return {(alvo, chave): dict(zip(
        ("situacao", "intencionalidade", "observacao", "profissional", "crf",
         "registrado_em"), r))
        for alvo, chave, *r in con.execute(
            "SELECT alvo, chave, situacao, intencionalidade, observacao, "
            "profissional, crf, registrado_em FROM anotacao_profissional "
            "WHERE atendimento_id=?", (at["id"],))}


def registrar_anotacao(con, codigo: str, alvo: str, chave: str,
                       situacao: str = "REVISADO", intencionalidade=None,
                       observacao=None, profissional=None, crf=None) -> None:
    """Registra que uma PESSOA olhou. Nunca altera prioridade nem gravidade."""
    at = exigir_atendimento(con, codigo)
    if alvo not in ("ACHADO", "DIVERGENCIA"):
        raise ErroDeUso("Alvo de anotação inválido.")
    if situacao not in ("REVISADO", "NAO_APLICAVEL"):
        raise ErroDeUso("Situação de revisão inválida.")
    profissional = _limpo(profissional) or _limpo(at.get("farmaceutico"))
    if not profissional:
        raise ErroDeUso("Informe o nome do profissional que está revisando. "
                        "Sem identificação, a revisão não é registrada.")
    intenc = _limpo(intencionalidade)
    if intenc and alvo != "DIVERGENCIA":
        raise ErroDeUso("Intencionalidade só se aplica a uma divergência.")
    if intenc and intenc not in ("INTENCIONAL", "NAO_INTENCIONAL"):
        raise ErroDeUso("Intencionalidade inválida.")
    con.execute(
        "INSERT INTO anotacao_profissional (atendimento_id, alvo, chave, "
        "situacao, intencionalidade, observacao, profissional, crf) "
        "VALUES (?,?,?,?,?,?,?,?) "
        "ON CONFLICT (atendimento_id, alvo, chave) DO UPDATE SET "
        "situacao=excluded.situacao, intencionalidade=excluded.intencionalidade, "
        "observacao=excluded.observacao, profissional=excluded.profissional, "
        "crf=excluded.crf, registrado_em=datetime('now')",
        (at["id"], alvo, chave, situacao, intenc or None, _limpo(observacao),
         profissional, _limpo(crf) or _limpo(at.get("crf"))))
    con.commit()


def _reaplicar_anotacoes(con, atendimento_id: int, res) -> None:
    """Leva a decisao humana ja registrada para as linhas recem-gravadas.

    `conciliacao_par.intencionalidade` so aceita valor diferente de
    NAO_DETERMINADA com `avaliado_por` preenchido — o CHECK do esquema exige.
    Aqui o nome vem da anotacao, que exigiu identificacao para existir.
    """
    if not res.conciliacao_id:
        return
    anotacoes = {(alvo, chave): (intenc, prof, quando)
                 for alvo, chave, intenc, prof, quando in con.execute(
                     "SELECT alvo, chave, intencionalidade, profissional, "
                     "registrado_em FROM anotacao_profissional "
                     "WHERE atendimento_id=? AND alvo='DIVERGENCIA'",
                     (atendimento_id,))}
    if not anotacoes:
        return
    for par in res.pares:
        dados = anotacoes.get(("DIVERGENCIA", chave_divergencia(par)))
        if not dados or not dados[0]:
            continue
        intenc, prof, quando = dados
        con.execute(
            "UPDATE conciliacao_par SET intencionalidade=?, avaliado_por=?, "
            "avaliado_em=? WHERE conciliacao_id=? AND nome_exibicao=? "
            "AND (tipo_divergencia IS ? OR tipo_divergencia=?)",
            (intenc, prof, quando, res.conciliacao_id, par.nome_exibicao,
             par.tipo_divergencia, par.tipo_divergencia))
        par.intencionalidade = intenc


# =====================================================================
# PENDENCIAS — o que falta, sem bloquear
# =====================================================================
def pendencias(con, codigo: str) -> list:
    """O que ainda falta para a análise ser útil.

    Advertencia, nao trava. A especificacao e explicita: indicar o que falta,
    sem bloquear o profissional. So a ausencia total de medicamento impede a
    analise, e por um motivo obvio.
    """
    at = exigir_atendimento(con, codigo)
    meds = listar_medicamentos(con, codigo)
    faltas = []
    if not at["nome"] or at["nome"].strip() == "":
        faltas.append(("paciente", "O nome do paciente não foi informado."))
    if at["data_nascimento"] is None:
        faltas.append(("paciente", "Sem data de nascimento: a idade não "
                                   "aparece no contexto dos achados."))
    if not meds:
        faltas.append(("medicamentos", "Nenhum medicamento registrado — a "
                                       "análise não pode ser executada."))
    sem_pos = [g.nome_relatado for g in meds if not g.tem_posologia]
    if sem_pos:
        faltas.append(("posologia", "Sem posologia: %s. A agenda de horários "
                                    "não é montada para esses itens."
                       % ", ".join(sem_pos[:5])))
    nao_rec = [g.nome_relatado for g in meds if not g.reconhecido]
    if nao_rec:
        faltas.append(("medicamentos", "Sem vínculo com o cadastro: %s. "
                                       "Nenhum módulo avalia esses itens."
                       % ", ".join(nao_rec[:5])))
    if not listar_rotina(con, codigo):
        faltas.append(("rotina", "Rotina não informada: o motor não consegue "
                                 "dizer se um horário respeita a relação com "
                                 "as refeições."))
    if not listar_condicoes(con, codigo):
        faltas.append(("anamnese", "Nenhuma condição clínica registrada — o "
                                   "módulo medicamento × doença não terá o "
                                   "que verificar."))
    if not listar_alergias(con, codigo):
        faltas.append(("anamnese", "Nenhuma alergia registrada — inclusive "
                                   "'nega alergias' é informação, e vale "
                                   "registrar."))
    habitos = listar_habitos(con, codigo)
    nao_informados = [rot for h, rot in HABITOS
                      if h in ("TABAGISMO", "ALCOOL", "CAFEINA")
                      and habitos.get(h, {}).get("situacao") in
                      (None, "NAO_INFORMADO")]
    if nao_informados:
        faltas.append(("anamnese", "Hábitos não informados: %s."
                       % ", ".join(nao_informados)))
    return faltas


def pode_analisar(con, codigo: str) -> bool:
    return bool(listar_medicamentos(con, codigo))


# =====================================================================
# AJUDANTES DE VALIDACAO
# =====================================================================
def _limpo(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return v or None


def _inteiro(v):
    if v is None or v == "":
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        raise ErroDeUso("Valor numérico inválido: %r." % v)


def _validar_numero(v, rotulo, minimo, maximo, permitir_zero=False):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    try:
        n = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        raise ErroDeUso("A %s precisa ser um número. Recebi %r." % (rotulo, v))
    if n == 0 and permitir_zero:
        raise ErroDeUso("A %s não pode ser zero. Deixe em branco se não for "
                        "conhecida." % rotulo)
    if not (minimo <= n <= maximo):
        raise ErroDeUso("A %s precisa estar entre %g e %g. Recebi %g."
                        % (rotulo, minimo, maximo, n))
    return n


def _validar_data(v, rotulo):
    v = (v or "").strip() if isinstance(v, str) else v
    if not v:
        return None
    try:
        return _dt.date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise ErroDeUso("A %s está em formato inválido. Use AAAA-MM-DD."
                        % rotulo)


def _idade(nascimento):
    if not nascimento:
        return None
    try:
        d = _dt.date.fromisoformat(str(nascimento)[:10])
    except ValueError:
        return None
    hoje = _dt.date.today()
    return hoje.year - d.year - ((hoje.month, hoje.day) < (d.month, d.day))
