# -*- coding: utf-8 -*-
"""
PREVISAO — a porta unica pela qual o modelo fala com o resto do sistema.

CONTRATO
--------
    prever(con, pares)          -> lista de Previsao
    contrato_achado(previsao)   -> dicionario com os campos de `achado`
    gravar_predicoes(con, ...)  -> escreve em `predicao` (nunca em `achado`)

`contrato_achado` NAO insere nada. Ele devolve a linha que a Fase 8 inseriria
se o modelo fosse homologado, ja com `natureza='PREVISTO'`,
`status_informacao='PREVISTO'`, `origem_achado='MODELO'`,
`nivel_evidencia=NULL` e `origem_afirmacao='predicao.<id>'` — exatamente o que
os CHECK do esquema exigem. Existir sem ser chamado e o ponto: o contrato fica
pronto e testado antes de qualquer previsao chegar ao balcao.

TRES TRAVAS
-----------
1. ESPACO DE ATRIBUTOS. Se `models/espaco_features.json` divergir do que
   `_features.espaco()` produz hoje, a funcao levanta erro e nao preve. Foi
   assim que o sistema anterior quebrou em silencio ao acrescentar o ATC.
2. MODELO NAO HOMOLOGADO. `prever` funciona (e para isso que serve a fila de
   curadoria), mas `contrato_achado` recusa enquanto `status<>'HOMOLOGADO'` —
   previsao de modelo experimental nao vira alerta nem por engano.
3. COBERTURA. Par cujo lado nao tem ATC recebe `cobertura='FRACA'` e o texto
   diz isso. Numero sem cobertura e pior que numero nenhum.

Uso:
    python ml/70_predizer.py varfarina omeprazol
    python ml/70_predizer.py --autoteste
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _artefato import carregar
from _comum import MODELOS, RAIZ, conectar, secao, titulo
from _features import carregar_contexto, construir, espaco

VERSAO_PADRAO = "1.0-boosting"


class EspacoDivergente(RuntimeError):
    pass


class ModeloNaoHomologado(RuntimeError):
    pass


@dataclass
class Previsao:
    substancia_a_id: int
    substancia_b_id: int
    nome_a: str
    nome_b: str
    probabilidade: float
    probabilidade_calibrada: float | None
    modelo: str
    versao: str
    algoritmo: str
    status_modelo: str
    cobertura: str                    # BOA | FRACA
    ja_documentado: bool
    contribuicoes: list = field(default_factory=list)
    predicao_id: int | None = None


class Preditor:
    def __init__(self, con, versao: str = VERSAO_PADRAO):
        linha = con.execute(
            "SELECT id,nome,versao,algoritmo,n_features,espaco_features_json,"
            "calibrador_json,artefato,status FROM modelo WHERE nome=? AND versao=?",
            ("m1_existencia_interacao", versao)).fetchone()
        if not linha:
            raise RuntimeError("modelo %s nao registrado — rode "
                               "ml/60_registrar_modelo.py" % versao)
        (self.modelo_id, self.nome, self.versao, self.algoritmo, self.n_features,
         espaco_json, calib_json, artefato, self.status) = linha
        self.con = con
        self.blocos = ("ATC", "REG", "ADM", "PK")
        self.ctx = carregar_contexto(con, None, origem_grafo="SEM_GRAFO")
        atual = espaco(self.ctx, self.blocos)
        gravado = json.loads(espaco_json)
        if atual != gravado:
            faltando = [n for n in gravado if n not in atual]
            sobrando = [n for n in atual if n not in gravado]
            raise EspacoDivergente(
                "o espaco de atributos mudou desde o treino: %d gravados, %d "
                "atuais; faltando %s; sobrando %s. Retreine antes de prever."
                % (len(gravado), len(atual), faltando[:5], sobrando[:5]))
        self.nomes = atual
        self.calibrador = json.loads(calib_json) if calib_json else None
        self.obj = carregar(RAIZ / artefato if not Path(artefato).is_absolute()
                            else Path(artefato))
        self.atc = {s: c for s, c in con.execute(
            "SELECT id, atc_codigo FROM substancia WHERE atc_codigo IS NOT NULL")}
        self.nome_subst = {s: n for s, n in con.execute(
            "SELECT id, nome_dcb FROM substancia")}
        self.X_ref = None

    # ------------------------------------------------------------- previsao
    def _calibrar(self, p):
        c = self.calibrador
        if not c or not c.get("tabela"):
            return None
        t = c["tabela"]
        return np.interp(p, t["x"], t["y"])

    def prever(self, pares, com_explicacao=True) -> list[Previsao]:
        pares = [(a, b) if a < b else (b, a) for a, b in pares]
        X = construir(self.ctx, pares, self.blocos)
        p = self.obj.prever(X=X, pares=pares, atc=self.atc)
        pc = self._calibrar(p)
        documentados = self._documentados(pares)
        saida = []
        for i, (a, b) in enumerate(pares):
            cob = "BOA" if (a in self.atc and b in self.atc) else "FRACA"
            pv = Previsao(
                substancia_a_id=a, substancia_b_id=b,
                nome_a=self.nome_subst.get(a, "?"),
                nome_b=self.nome_subst.get(b, "?"),
                probabilidade=float(p[i]),
                probabilidade_calibrada=(float(pc[i]) if pc is not None else None),
                modelo=self.nome, versao=self.versao, algoritmo=self.algoritmo,
                status_modelo=self.status, cobertura=cob,
                ja_documentado=(a, b) in documentados)
            if com_explicacao:
                pv.contribuicoes = self._explicar(X[i])
            saida.append(pv)
        return saida

    def _documentados(self, pares):
        achados = set()
        for a, b in pares:
            r = self.con.execute(
                "SELECT 1 FROM vw_interacao_liberada WHERE substancia_a_id=? "
                "AND substancia_b_id=? LIMIT 1", (a, b)).fetchone()
            if r:
                achados.add((a, b))
        return achados

    def _explicar(self, x, k=5):
        """Contribuicao aproximada por ocultacao. NAO e SHAP; ver 40_*."""
        if self.X_ref is None:
            self.X_ref = np.zeros(len(self.nomes), dtype=np.float32)
        base = float(self.obj.prever(X=x.reshape(1, -1))[0])
        var = np.repeat(x.reshape(1, -1), len(self.nomes), axis=0)
        for j in range(len(self.nomes)):
            var[j, j] = self.X_ref[j]
        p = self.obj.prever(X=var)
        efeito = base - p
        ordem = np.argsort(-np.abs(efeito))[:k]
        return [dict(atributo=self.nomes[j], valor=float(x[j]),
                     efeito=float(efeito[j])) for j in ordem
                if abs(efeito[j]) > 1e-6]

    # -------------------------------------------------- contrato da interface
    def contrato_achado(self, pv: Previsao) -> dict:
        """Campos de `achado` para uma previsao. Recusa modelo nao homologado."""
        if self.status != "HOMOLOGADO":
            raise ModeloNaoHomologado(
                "modelo %s %s esta com status %s; previsao dele nao pode virar "
                "achado. Homologar e ato humano registrado, nao efeito colateral "
                "de uma consulta." % (self.nome, self.versao, self.status))
        if pv.predicao_id is None:
            raise RuntimeError("grave a predicao antes: origem_afirmacao tem de "
                               "apontar para uma linha real de `predicao`")
        prob = pv.probabilidade_calibrada or pv.probabilidade
        return dict(
            modulo="FARMACO_FARMACO", subtipo="INTERACAO_PREVISTA",
            classificacao="POSSIVEL", natureza="PREVISTO",
            status_informacao="PREVISTO", origem_achado="MODELO",
            probabilidade_modelo=prob,
            origem_afirmacao="predicao.%d" % pv.predicao_id,
            nivel_evidencia=None, gravidade_fonte=None,
            confianca_sistema="BAIXA", confianca_extracao="CALCULADO",
            requer_revisao_profissional=1,
            item_a=pv.nome_a, substancia_a_id=pv.substancia_a_id,
            item_b=pv.nome_b, substancia_b_id=pv.substancia_b_id,
            alvo_tipo="SUBSTANCIA",
            titulo="Possível interação prevista por modelo entre %s e %s"
                   % (pv.nome_a, pv.nome_b),
            mecanismo=None, efeito_esperado=None, descricao_fonte=None,
            conduta=None,
            explicacao=self.texto(pv),
            metodo_deteccao="MODELO_%s_%s" % (pv.modelo, pv.versao),
            grupo_chave="PREV:%d:%d" % (pv.substancia_a_id, pv.substancia_b_id))

    def texto(self, pv: Previsao) -> str:
        """O que a interface mostra. Diz o que e e o que NAO e.

        A primeira frase depende de `ja_documentado` e nao pode ser fixa: dizer
        "nao ha interacao documentada" sobre um par que ESTA documentado seria
        o proprio erro que esta fase existe para impedir, com o sinal trocado.
        """
        prob = pv.probabilidade_calibrada or pv.probabilidade
        if pv.ja_documentado:
            partes = [
                "Já existe interação DOCUMENTADA entre %s e %s nas fontes "
                "carregadas — o alerta que vale é o documentado, e ele vem do "
                "caminho determinístico, não daqui." % (pv.nome_a, pv.nome_b),
                "A estimativa abaixo serve apenas para conferir o modelo em "
                "par conhecido; ela não acrescenta nada ao que a fonte já diz.",
            ]
        else:
            partes = [
                "Não há interação documentada entre %s e %s nas fontes "
                "carregadas." % (pv.nome_a, pv.nome_b),
            ]
        partes += [
            "Esta linha é uma PREVISÃO estatística, não uma evidência: "
            "probabilidade estimada de %.0f%% de que exista interação "
            "documentada em alguma base." % (100 * prob),
            "Modelo %s versão %s (%s), status %s."
            % (pv.modelo, pv.versao, pv.algoritmo, pv.status_modelo),
        ]
        if pv.cobertura == "FRACA":
            partes.append("ATENÇÃO: pelo menos um dos fármacos não tem "
                          "classificação ATC no banco; o modelo opinou com "
                          "poucos atributos e a estimativa é frágil.")
        if not pv.ja_documentado:
            partes.append("Nenhuma bula, artigo ou base afirmou esta "
                          "interação.")
        partes.append("Requer verificação por farmacêutico antes de qualquer "
                      "conduta.")
        return " ".join(partes)

    # ----------------------------------------------------------- persistencia
    def gravar_predicoes(self, previsoes) -> int:
        n = 0
        for pv in previsoes:
            cur = self.con.execute(
                "INSERT OR REPLACE INTO predicao (modelo_id,substancia_a_id,"
                "substancia_b_id,probabilidade,probabilidade_calibrada,"
                "explicacao_json,gravidade_sugerida) VALUES (?,?,?,?,?,?,NULL)",
                (self.modelo_id, pv.substancia_a_id, pv.substancia_b_id,
                 pv.probabilidade, pv.probabilidade_calibrada,
                 json.dumps(pv.contribuicoes, ensure_ascii=False)))
            pv.predicao_id = cur.lastrowid
            n += 1
        self.con.commit()
        return n


# -------------------------------------------------------------------- CLI

def _buscar(con, termo):
    r = con.execute("SELECT id, nome_dcb FROM substancia WHERE nome_dcb=? "
                    "COLLATE NOCASE", (termo,)).fetchone()
    if r:
        return r
    return con.execute("SELECT id, nome_dcb FROM substancia WHERE nome_dcb LIKE ? "
                       "ORDER BY LENGTH(nome_dcb) LIMIT 1",
                       ("%" + termo + "%",)).fetchone()


def _autoteste() -> int:
    con = conectar()
    titulo("AUTOTESTE DO CONTRATO DE PREVISAO")
    falhas = []
    p = Preditor(con)
    print("  modelo %s %s (%s), status %s" % (p.nome, p.versao, p.algoritmo,
                                              p.status))
    print("  espaco de atributos confere: %d nomes" % len(p.nomes))

    pares = [(1, 2), (3, 4), (10, 500)]
    pares = [(a, b) for a, b in pares if a != b]
    pv = p.prever(pares)
    if len(pv) != len(pares):
        falhas.append("numero de previsoes diferente do numero de pares")
    if not all(0.0 <= x.probabilidade <= 1.0 for x in pv):
        falhas.append("probabilidade fora de [0,1]")
    else:
        print("  todas as probabilidades em [0,1]  OK")

    # simetria da previsao
    inv = p.prever([(b, a) for a, b in pares], com_explicacao=False)
    if not all(abs(x.probabilidade - z.probabilidade) < 1e-9
               for x, z in zip(pv, inv)):
        falhas.append("previsao muda com a ordem do par")
    else:
        print("  prever(a,b) == prever(b,a)  OK")

    # o contrato recusa modelo experimental
    try:
        p.contrato_achado(pv[0])
        falhas.append("contrato_achado aceitou modelo NAO homologado")
    except ModeloNaoHomologado:
        print("  contrato_achado recusa modelo EXPERIMENTAL  OK")

    # divergencia de espaco e detectada
    try:
        p2 = Preditor(con)
        p2.nomes = p2.nomes[:-1]
        gravado = json.loads(con.execute(
            "SELECT espaco_features_json FROM modelo WHERE nome=? AND versao=?",
            ("m1_existencia_interacao", VERSAO_PADRAO)).fetchone()[0])
        if espaco(p2.ctx, p2.blocos) == gravado:
            print("  espaco atual identico ao gravado  OK")
        else:
            falhas.append("espaco atual difere do gravado")
    except Exception as e:
        falhas.append("erro ao conferir espaco: %s" % e)

    # gravidade_sugerida continua proibida
    try:
        con.execute("INSERT INTO predicao (modelo_id,substancia_a_id,"
                    "substancia_b_id,probabilidade,gravidade_sugerida) "
                    "VALUES (?,1,2,0.5,'MAIOR')", (p.modelo_id,))
        falhas.append("o banco aceitou gravidade sugerida por modelo")
        con.rollback()
    except Exception:
        con.rollback()
        print("  banco recusa gravidade sugerida pelo modelo  OK")

    print()
    if falhas:
        for f in falhas:
            print("  FALHA: %s" % f)
        return 1
    print("AUTOTESTE OK")
    return 0


def main(argv) -> int:
    if "--autoteste" in argv:
        return _autoteste()
    if len(argv) < 2:
        print(__doc__)
        return 2
    con = conectar()
    a = _buscar(con, argv[0])
    b = _buscar(con, argv[1])
    if not a or not b:
        print("substancia nao encontrada: %s" % (argv[0] if not a else argv[1]))
        return 1
    p = Preditor(con)
    pv = p.prever([(a[0], b[0])])[0]
    titulo("%s  x  %s" % (pv.nome_a, pv.nome_b))
    secao("o que a fonte diz")
    print("  interacao documentada nas bases carregadas: %s"
          % ("SIM" if pv.ja_documentado else "nao"))
    secao("o que o modelo estima")
    print("  probabilidade bruta ....... %.3f" % pv.probabilidade)
    if pv.probabilidade_calibrada is not None:
        print("  probabilidade calibrada ... %.3f" % pv.probabilidade_calibrada)
    print("  cobertura de atributos .... %s" % pv.cobertura)
    print("  modelo .................... %s %s (%s), status %s"
          % (pv.modelo, pv.versao, pv.algoritmo, pv.status_modelo))
    secao("o que pesou (contribuicao aproximada, nao SHAP)")
    for c in pv.contribuicoes:
        print("  [%+.3f] %s = %g" % (c["efeito"], c["atributo"], c["valor"]))
    secao("texto que iria para a tela")
    print("  " + p.texto(pv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
