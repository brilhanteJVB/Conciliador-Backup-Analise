# -*- coding: utf-8 -*-
"""
GRAVACAO E LEITURA DO MODELO TREINADO.

FORMATO — a escolha nao e de gosto
----------------------------------
Sempre que a familia permite, o artefato e JSON: uma lista de coeficientes ou
uma tabela de valores, legivel por qualquer coisa e estavel no tempo. Pickle
de scikit-learn amarra o arquivo a uma versao de biblioteca; daqui a dois anos
o mesmo .pkl pode nao abrir, e o sistema vai virar um .exe que ninguem
recompila. Por isso:

    LOGISTICA               -> JSON  (media, escala, coeficientes, intercepto)
    TABELA_CLASSE_x_CLASSE  -> JSON  (a tabela inteira)
    FLORESTA / BOOSTING     -> pickle, com a versao do sklearn gravada ao lado
                               e AVISO explicito de que o artefato e fragil

Essa diferenca entra na tabela de comparacao como custo de manutencao, e nao
como detalhe de implementacao: um modelo que so abre numa versao especifica de
biblioteca e mais dificil de validar por terceiro.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
import sklearn


def _sigmoide(z):
    return 1.0 / (1.0 + np.exp(-z))


class ModeloCarregado:
    """Interface unica de previsao, independente do formato de origem."""

    def __init__(self, dados: dict, objeto=None):
        self.meta = dados
        self.tipo = dados["tipo"]
        self.obj = objeto

    def prever(self, X=None, pares=None, atc=None) -> np.ndarray:
        if self.tipo == "LOGISTICA_JSON":
            m = np.asarray(self.meta["media"], dtype=np.float64)
            s = np.asarray(self.meta["escala"], dtype=np.float64)
            w = np.asarray(self.meta["coeficientes"], dtype=np.float64)
            b = float(self.meta["intercepto"])
            z = ((np.asarray(X, dtype=np.float64) - m) / s) @ w + b
            return _sigmoide(z)
        if self.tipo == "TABELA_JSON":
            tab = self.meta["tabela"]
            g = float(self.meta["global"])
            out = np.empty(len(pares))
            for i, (a, b) in enumerate(pares):
                ca, cb = (atc or {}).get(a), (atc or {}).get(b)
                if not ca or not cb:
                    out[i] = g
                    continue
                x, y = ca[:3], cb[:3]
                out[i] = tab.get("%s|%s" % ((x, y) if x <= y else (y, x)), g)
            return out
        if self.tipo == "SKLEARN_PICKLE":
            return self.obj.predict_proba(X)[:, 1]
        raise ValueError(self.tipo)


def salvar(familia, caminho: Path, meta: dict) -> dict:
    """Grava o artefato. Devolve o cabecalho gravado (para o registro)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    nome = familia.nome
    if nome == "LOGISTICA":
        d = dict(meta, tipo="LOGISTICA_JSON",
                 media=[float(v) for v in familia.esc.mean_],
                 escala=[float(v) for v in familia.esc.scale_],
                 coeficientes=[float(v) for v in familia.m.coef_[0]],
                 intercepto=float(familia.m.intercept_[0]),
                 aviso=None)
        caminho.with_suffix(".json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(d, artefato=str(caminho.with_suffix(".json")))
    if nome == "TABELA_CLASSE_x_CLASSE":
        d = dict(meta, tipo="TABELA_JSON",
                 tabela={"%s|%s" % k: float(v) for k, v in familia.tab.items()},
                 global_=float(familia.global_),
                 suavizacao=float(familia.k), aviso=None)
        d["global"] = d.pop("global_")
        caminho.with_suffix(".json").write_text(
            json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(d, artefato=str(caminho.with_suffix(".json")))
    # arvores: pickle ao lado, e o JSON continua sendo O MANIFESTO.
    # `artefato` aponta SEMPRE para o .json — quem le comeca pelo manifesto,
    # descobre o tipo e so entao procura o .pkl irmao. Apontar direto para o
    # pickle fazia `carregar` tentar ler binario como texto.
    d = dict(meta, tipo="SKLEARN_PICKLE", sklearn=sklearn.__version__,
             pickle=caminho.with_suffix(".pkl").name,
             aviso="artefato depende da versao %s do scikit-learn; para "
                   "empacotamento em .exe isso e uma amarra, e esta declarado"
                   % sklearn.__version__)
    with caminho.with_suffix(".pkl").open("wb") as fh:
        pickle.dump(familia.m, fh, protocol=4)
    caminho.with_suffix(".json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return dict(d, artefato=str(caminho.with_suffix(".json")),
                bytes_pickle=caminho.with_suffix(".pkl").stat().st_size)


def carregar(caminho_json: Path) -> ModeloCarregado:
    d = json.loads(Path(caminho_json).read_text(encoding="utf-8"))
    obj = None
    if d["tipo"] == "SKLEARN_PICKLE":
        pkl = Path(caminho_json).with_suffix(".pkl")
        if sklearn.__version__ != d.get("sklearn"):
            print("  AVISO: artefato gravado com scikit-learn %s, lendo com %s"
                  % (d.get("sklearn"), sklearn.__version__))
        with pkl.open("rb") as fh:
            obj = pickle.load(fh)
    return ModeloCarregado(d, obj)
