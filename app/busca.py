# -*- coding: utf-8 -*-
"""
SERVICO DE BUSCA — o terceiro ponto de entrada previsto na arquitetura.

`docs/ARQUITETURA.md` previa tres servicos para a aplicacao consumir:
`buscar_medicamento`, `montar_agenda` e `conciliar`. Os dois ultimos ja
existiam desde as Fases 4 e 5. Este faltava — e sem ele a interface teria de
montar SQL dentro das telas, que e exatamente o que a especificacao proibe.

CONTRATO PUBLICO

    buscar_medicamento(con, termo, limite=20) -> list[Resultado]
    buscar_substancia(con, termo, limite=20)  -> list[Resultado]
    buscar_condicao(con, termo, limite=20)    -> list[Opcao]
    buscar_item(con, termo, tipos=None)       -> list[Opcao]
    detalhar_apresentacao(con, apresentacao_id) -> dict

Nenhuma dessas funcoes decide nada clinico. Elas encontram e descrevem; quem
avalia sao os motores.

QUATRO PASSES, DO DETERMINISTICO AO TOLERANTE
---------------------------------------------
1. CODIGO DE BARRAS  termo so com digito, tamanho 8/12/13/14 -> `apresentacao_ean`.
                     Deterministico. reconhecimento='EAN', confianca ALTA.
2. CHAVE EXATA       o esqueleto fonetico do termo bate com o de uma substancia
                     ou sinonimo. reconhecimento='NOME_EXATO', confianca ALTA.
3. PREFIXO DA CHAVE  para o autocompletar enquanto se digita.
                     reconhecimento='NOME_APROXIMADO', confianca MEDIA.
4. NOME COMERCIAL    LIKE sobre `produto.nome_comercial`, com apresentacao,
                     concentracao, forma e empresa.
                     reconhecimento='NOME_APROXIMADO', confianca MEDIA.

O esqueleto fonetico e o MESMO que uniu as fontes na Fase 2
(`pipeline/normalizacao.skeleton`): 'dipirona monoidratada' e 'metamisol'
caem na mesma chave. Casar por string crua nao funciona, e foi medido.

ASSOCIACAO EM DOSE FIXA
-----------------------
Uma apresentacao pode ter mais de uma substancia (losartana +
hidroclorotiazida). O resultado devolve **todas** em `.substancias`, e quem
grava expande em uma linha por componente — porque o modulo de interacao
precisa ver os dois lados. Ver `app/servicos.adicionar_medicamento`.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "pipeline"))
from normalizacao import skeleton  # noqa: E402

EAN_VALIDO = re.compile(r"^\d{8}$|^\d{12}$|^\d{13}$|^\d{14}$")
MIN_TERMO = 2


@dataclass
class Resultado:
    """Um candidato de medicamento, com a procedencia do casamento."""
    tipo: str                       # EAN | SUBSTANCIA | APRESENTACAO
    rotulo: str
    detalhe: str = ""
    substancia_id: Optional[int] = None
    apresentacao_id: Optional[int] = None
    produto: Optional[str] = None
    empresa: Optional[str] = None
    forma: Optional[str] = None
    concentracao: Optional[str] = None
    ean: Optional[str] = None
    # Uma linha por componente da associacao em dose fixa.
    substancias: list = field(default_factory=list)   # [(id, nome_dcb)]
    reconhecimento: str = "MANUAL"  # EAN | NOME_EXATO | NOME_APROXIMADO | MANUAL
    confianca: str = "BAIXA"        # ALTA | MEDIA | BAIXA
    n_produtos: int = 0

    @property
    def chave(self) -> str:
        """Identificador estavel para o formulario da tela."""
        if self.apresentacao_id:
            return "apresentacao:%d" % self.apresentacao_id
        if self.substancia_id:
            return "substancia:%d" % self.substancia_id
        return "livre:%s" % self.rotulo


@dataclass
class Opcao:
    """Item simples de lista: condicao clinica, alimento, planta, suplemento."""
    id: int
    nome: str
    grupo: Optional[str] = None
    tipo: Optional[str] = None


# =====================================================================
# MEDICAMENTO
# =====================================================================
def buscar_medicamento(con, termo: str, limite: int = 20) -> list:
    """Busca tolerante por medicamento, princípio ativo, marca ou código.

    Devolve no maximo `limite` resultados, os mais determinísticos primeiro.
    Nunca levanta excecao por termo curto ou vazio: devolve lista vazia.
    """
    termo = (termo or "").strip()
    if len(termo) < MIN_TERMO:
        return []

    so_digitos = re.sub(r"[^\d]", "", termo)
    if EAN_VALIDO.match(so_digitos):
        achados = _por_ean(con, so_digitos)
        if achados:
            return achados[:limite]

    vistos, saida = set(), []
    for fn in (_por_chave_exata, _por_prefixo_chave, _por_nome_comercial):
        for r in fn(con, termo, limite):
            if r.chave in vistos:
                continue
            vistos.add(r.chave)
            saida.append(r)
            if len(saida) >= limite:
                return saida
    return saida


def _por_ean(con, ean: str) -> list:
    """Codigo de barras: caminho deterministico, o unico com confianca ALTA
    que nao depende de leitura de nome."""
    saida = []
    for (apres_id, descricao, conc_v, conc_u, forma, via, qtd, prod_nome,
         empresa) in con.execute(
            "SELECT a.id, a.descricao, a.concentracao_valor, "
            "a.concentracao_unidade, a.forma_farmaceutica, a.via_administracao, "
            "a.quantidade_embalagem, p.nome_comercial, p.empresa "
            "FROM apresentacao_ean e JOIN apresentacao a ON a.id = e.apresentacao_id "
            "JOIN produto p ON p.id = a.produto_id WHERE e.ean = ?", (ean,)):
        saida.append(_montar_apresentacao(
            con, apres_id, descricao, conc_v, conc_u, forma, via, qtd,
            prod_nome, empresa, reconhecimento="EAN", confianca="ALTA",
            ean=ean))
    return saida


def _por_chave_exata(con, termo: str, limite: int) -> list:
    chave = skeleton(termo)
    if not chave:
        return []
    ids = {sid for (sid,) in con.execute(
        "SELECT id FROM substancia WHERE chave_normalizada = ?", (chave,))}
    ids |= {sid for (sid,) in con.execute(
        "SELECT substancia_id FROM substancia_sinonimo "
        "WHERE chave_normalizada = ?", (chave,))}
    return _substancias(con, ids, "NOME_EXATO", "ALTA", limite)


def _por_prefixo_chave(con, termo: str, limite: int) -> list:
    chave = skeleton(termo)
    if not chave or len(chave) < 3:
        return []
    ids = {sid for (sid,) in con.execute(
        "SELECT id FROM substancia WHERE chave_normalizada LIKE ? "
        "ORDER BY n_produtos_ativos DESC LIMIT ?", (chave + "%", limite))}
    ids |= {sid for (sid,) in con.execute(
        "SELECT substancia_id FROM substancia_sinonimo "
        "WHERE chave_normalizada LIKE ? LIMIT ?", (chave + "%", limite))}
    return _substancias(con, ids, "NOME_APROXIMADO", "MEDIA", limite)


def _substancias(con, ids, reconhecimento, confianca, limite) -> list:
    if not ids:
        return []
    marca = ",".join("?" * len(ids))
    saida = []
    for sid, nome, atc, canal, n_prod in con.execute(
            "SELECT id, nome_dcb, atc_codigo, canal_dispensacao, n_produtos_ativos "
            "FROM substancia WHERE id IN (%s) "
            "ORDER BY n_produtos_ativos DESC LIMIT ?" % marca,
            list(ids) + [limite]):
        detalhe = []
        if n_prod:
            detalhe.append("%d apresentação(ões) no mercado" % n_prod)
        if canal and canal != "NAO_DETERMINADO":
            detalhe.append(_rotulo_tarja(canal))
        if atc:
            detalhe.append("ATC %s" % atc)
        saida.append(Resultado(
            tipo="SUBSTANCIA", rotulo=nome, detalhe=" · ".join(detalhe),
            substancia_id=sid, substancias=[(sid, nome)],
            reconhecimento=reconhecimento, confianca=confianca,
            n_produtos=n_prod or 0))
    return saida


def _por_nome_comercial(con, termo: str, limite: int) -> list:
    padrao = "%" + termo.strip().upper() + "%"
    saida = []
    for (apres_id, descricao, conc_v, conc_u, forma, via, qtd, prod_nome,
         empresa) in con.execute(
            "SELECT a.id, a.descricao, a.concentracao_valor, "
            "a.concentracao_unidade, a.forma_farmaceutica, a.via_administracao, "
            "a.quantidade_embalagem, p.nome_comercial, p.empresa "
            "FROM produto p JOIN apresentacao a ON a.produto_id = p.id "
            "WHERE p.situacao='ATIVO' AND UPPER(p.nome_comercial) LIKE ? "
            "ORDER BY p.nome_comercial LIMIT ?", (padrao, limite)):
        saida.append(_montar_apresentacao(
            con, apres_id, descricao, conc_v, conc_u, forma, via, qtd,
            prod_nome, empresa, reconhecimento="NOME_APROXIMADO",
            confianca="MEDIA"))
    return saida


def _montar_apresentacao(con, apres_id, descricao, conc_v, conc_u, forma, via,
                         qtd, prod_nome, empresa, reconhecimento, confianca,
                         ean=None) -> Resultado:
    componentes = list(con.execute(
        "SELECT s.id, s.nome_dcb FROM apresentacao_substancia asu "
        "JOIN substancia s ON s.id = asu.substancia_id "
        "WHERE asu.apresentacao_id = ? ORDER BY s.nome_dcb", (apres_id,)))
    concentracao = None
    if conc_v is not None:
        concentracao = ("%g %s" % (conc_v, conc_u or "")).strip()
    partes = [p for p in (concentracao, forma, via) if p]
    if qtd:
        partes.append("emb. %d" % qtd)
    if empresa:
        partes.append(empresa)
    if componentes:
        partes.insert(0, " + ".join(n for _i, n in componentes))
    return Resultado(
        tipo="EAN" if ean else "APRESENTACAO",
        rotulo=prod_nome, detalhe=" · ".join(partes),
        substancia_id=componentes[0][0] if componentes else None,
        apresentacao_id=apres_id, produto=prod_nome, empresa=empresa,
        forma=forma, concentracao=concentracao, ean=ean,
        substancias=componentes, reconhecimento=reconhecimento,
        confianca=confianca)


def _rotulo_tarja(canal: str) -> str:
    return {"MIP": "venda livre (MIP)",
            "TARJA_VERMELHA": "tarja vermelha",
            "TARJA_VERMELHA_RETENCAO": "tarja vermelha com retenção",
            "TARJA_PRETA": "tarja preta"}.get(canal, canal)


def detalhar_apresentacao(con, apresentacao_id: int) -> Optional[dict]:
    linha = con.execute(
        "SELECT a.descricao, a.concentracao_valor, a.concentracao_unidade, "
        "a.forma_farmaceutica, a.via_administracao, a.quantidade_embalagem, "
        "a.codigo_ggrem, p.nome_comercial, p.empresa, p.categoria, "
        "p.registro_anvisa FROM apresentacao a JOIN produto p "
        "ON p.id = a.produto_id WHERE a.id = ?", (apresentacao_id,)).fetchone()
    if not linha:
        return None
    (descricao, cv, cu, forma, via, qtd, ggrem, prod, empresa, categoria,
     registro) = linha
    return {
        "descricao": descricao, "forma": forma, "via": via,
        "concentracao": ("%g %s" % (cv, cu or "")).strip() if cv is not None
                        else None,
        "quantidade": qtd, "codigo_ggrem": ggrem, "produto": prod,
        "empresa": empresa, "categoria": categoria,
        "registro_anvisa": registro,
        "eans": [e for (e,) in con.execute(
            "SELECT ean FROM apresentacao_ean WHERE apresentacao_id=? "
            "ORDER BY ordem", (apresentacao_id,))],
        "substancias": list(con.execute(
            "SELECT s.id, s.nome_dcb FROM apresentacao_substancia asu "
            "JOIN substancia s ON s.id=asu.substancia_id "
            "WHERE asu.apresentacao_id=?", (apresentacao_id,))),
    }


# =====================================================================
# SUBSTANCIA (alergia)
# =====================================================================
def buscar_substancia(con, termo: str, limite: int = 20) -> list:
    """So substancias — usada na tela de alergia, onde o que importa e o
    principio ativo e nao a marca."""
    termo = (termo or "").strip()
    if len(termo) < MIN_TERMO:
        return []
    vistos, saida = set(), []
    for fn in (_por_chave_exata, _por_prefixo_chave):
        for r in fn(con, termo, limite):
            if r.substancia_id in vistos:
                continue
            vistos.add(r.substancia_id)
            saida.append(r)
            if len(saida) >= limite:
                return saida
    if saida:
        return saida
    # Ultimo recurso: casar pelo texto do nome, para quem digita o sal.
    padrao = "%" + termo.lower() + "%"
    for sid, nome, n in con.execute(
            "SELECT id, nome_dcb, n_produtos_ativos FROM substancia "
            "WHERE LOWER(nome_dcb) LIKE ? ORDER BY n_produtos_ativos DESC "
            "LIMIT ?", (padrao, limite)):
        saida.append(Resultado(
            tipo="SUBSTANCIA", rotulo=nome, substancia_id=sid,
            substancias=[(sid, nome)], reconhecimento="NOME_APROXIMADO",
            confianca="MEDIA", n_produtos=n or 0))
    return saida


# =====================================================================
# CONDICAO CLINICA
# =====================================================================
def buscar_condicao(con, termo: str = "", limite: int = 40) -> list:
    """Condicoes do cadastro. Termo vazio devolve a lista inteira, agrupada —
    a especificacao pede que o profissional escolha em vez de digitar."""
    termo = (termo or "").strip().lower()
    if termo:
        linhas = con.execute(
            "SELECT id, nome, grupo FROM doenca WHERE LOWER(nome) LIKE ? "
            "ORDER BY grupo, nome LIMIT ?", ("%" + termo + "%", limite))
    else:
        linhas = con.execute(
            "SELECT id, nome, grupo FROM doenca ORDER BY grupo, nome LIMIT ?",
            (limite,))
    return [Opcao(id=i, nome=n, grupo=g) for i, n, g in linhas]


def condicoes_por_grupo(con) -> dict:
    """Para o checklist da anamnese: {grupo: [Opcao, ...]}."""
    saida = {}
    for o in buscar_condicao(con, "", limite=1000):
        saida.setdefault(o.grupo or "Outras", []).append(o)
    return saida


# =====================================================================
# ITEM NAO MEDICAMENTOSO (alimento, planta, suplemento)
# =====================================================================
GRUPOS_ITEM = {
    "ALIMENTO": ("ALIMENTO", "BEBIDA"),
    "PLANTA": ("CHA", "PLANTA_MEDICINAL"),
    "SUPLEMENTO": ("SUPLEMENTO", "VITAMINA", "MINERAL"),
}


def buscar_item(con, termo: str = "", grupo: Optional[str] = None,
                limite: int = 60) -> list:
    """Itens não medicamentosos. `grupo` ∈ ALIMENTO | PLANTA | SUPLEMENTO.

    A especificacao e explicita: alimento, suplemento e planta sao secoes
    SEPARADAS, porque tem funcao diferente na analise. O filtro por grupo e o
    que sustenta essa separacao na tela.
    """
    sql = "SELECT id, nome, tipo FROM item_nao_medicamentoso WHERE 1=1"
    args = []
    if grupo:
        tipos = GRUPOS_ITEM.get(grupo, ())
        if tipos:
            sql += " AND tipo IN (%s)" % ",".join("?" * len(tipos))
            args += list(tipos)
    if termo and termo.strip():
        sql += " AND LOWER(nome) LIKE ?"
        args.append("%" + termo.strip().lower() + "%")
    sql += " ORDER BY nome LIMIT ?"
    args.append(limite)
    return [Opcao(id=i, nome=n, tipo=t) for i, n, t in con.execute(sql, args)]


# =====================================================================
# AUTOTESTE
# =====================================================================
if __name__ == "__main__":
    import sqlite3

    BANCO = RAIZ / "database" / "conciliador.db"
    con = sqlite3.connect("file:%s?mode=ro" % BANCO.as_posix(), uri=True)
    falhas = []

    def checa(desc, ok, detalhe=""):
        print("   %s %-46s %s" % ("OK  " if ok else "ERRO", desc[:46],
                                  str(detalhe)[:70]))
        if not ok:
            falhas.append(desc)

    print("autoteste de app/busca.py\n")

    r = buscar_medicamento(con, "dipirona")
    checa("busca por princípio ativo", bool(r) and r[0].substancia_id,
          "%d resultado(s), 1º = %s" % (len(r), r[0].rotulo if r else "-"))
    checa("o primeiro é casamento exato",
          bool(r) and r[0].reconhecimento == "NOME_EXATO",
          r[0].reconhecimento if r else "-")

    # O esqueleto fonetico e o mesmo da carga: sinonimo cai na substancia.
    r2 = buscar_medicamento(con, "metamisol")
    checa("sinônimo fonético encontra a substância brasileira", bool(r2),
          r2[0].rotulo if r2 else "nada")

    r3 = buscar_medicamento(con, "dipiron")
    checa("prefixo (autocompletar) devolve candidatos", bool(r3),
          "%d resultado(s)" % len(r3))

    ean = con.execute("SELECT ean FROM apresentacao_ean LIMIT 1").fetchone()[0]
    r4 = buscar_medicamento(con, ean)
    checa("código de barras é determinístico",
          bool(r4) and r4[0].reconhecimento == "EAN" and r4[0].confianca == "ALTA",
          "%s -> %s" % (ean, r4[0].rotulo if r4 else "-"))

    r5 = buscar_medicamento(con, "x" * 30)
    checa("termo sem correspondência devolve lista vazia", r5 == [], len(r5))
    checa("termo curto não quebra", buscar_medicamento(con, "a") == [], "[]")
    checa("termo vazio não quebra", buscar_medicamento(con, "") == [], "[]")

    # Associacao em dose fixa precisa devolver TODOS os componentes.
    linha = con.execute(
        "SELECT apresentacao_id FROM apresentacao_substancia "
        "GROUP BY apresentacao_id HAVING COUNT(*) > 1 LIMIT 1").fetchone()
    if linha:
        d = detalhar_apresentacao(con, linha[0])
        checa("associação devolve todos os componentes",
              d and len(d["substancias"]) > 1,
              "%d componentes" % len(d["substancias"]) if d else "-")

    cond = buscar_condicao(con, "renal")
    checa("busca de condição clínica", bool(cond),
          cond[0].nome if cond else "nada")
    grupos = condicoes_por_grupo(con)
    checa("condições agrupadas para o checklist", len(grupos) > 3,
          "%d grupos" % len(grupos))

    plantas = buscar_item(con, grupo="PLANTA")
    alimentos = buscar_item(con, grupo="ALIMENTO")
    supl = buscar_item(con, grupo="SUPLEMENTO")
    checa("itens separados por grupo",
          bool(plantas) and bool(alimentos) and bool(supl),
          "plantas %d · alimentos %d · suplementos %d"
          % (len(plantas), len(alimentos), len(supl)))
    checa("os grupos não se misturam",
          not ({p.id for p in plantas} & {a.id for a in alimentos}), "ok")

    sub = buscar_substancia(con, "varfarina")
    checa("busca de substância para alergia", bool(sub),
          sub[0].rotulo if sub else "nada")

    con.close()
    print("\n%s" % ("FALHOU — %d" % len(falhas) if falhas
                    else "todos os testes passaram"))
    sys.exit(1 if falhas else 0)
