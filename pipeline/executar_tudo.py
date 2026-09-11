# -*- coding: utf-8 -*-
"""
Executa o pipeline inteiro, na ordem, e para no primeiro erro.

A numeracao dita a ordem e ela importa: substancia antes de produto (o
vinculo precisa da substancia), produto antes de ATC (o nivel 5 usa o nome
em portugues da DCB ja carregada).

Uso:
    python pipeline/executar_tudo.py              # carga incremental
    python pipeline/executar_tudo.py --recriar    # apaga e reconstroi
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PIPELINE = RAIZ / "pipeline"
TESTES = RAIZ / "tests"

ETAPAS = [
    ("pipeline/10_fontes.py", "catálogo de fontes"),
    ("pipeline/20_substancias.py", "substâncias (ANVISA + DCB)"),
    ("pipeline/30_produtos.py", "produtos, apresentações e EAN (CMED)"),
    ("pipeline/40_atc.py", "classificação ATC (WHO)"),
    ("pipeline/50_regras_administracao.py", "regras de administração (DrugBank)"),
    ("pipeline/55_regras_bula.py", "regras de administração (bulas ANVISA)"),
    ("pipeline/58_conflitos_administracao.py", "conflitos entre fontes"),
    ("pipeline/60_interacoes_substancia.py", "interações fármaco × fármaco"),
    ("pipeline/62_papel_farmacocinetico.py", "papel farmacocinético (FDA)"),
    ("pipeline/64_contraindicacoes_bula.py", "fármaco × doença (bulas)"),
    ("pipeline/65_habitos_bula.py", "fármaco × hábito: tabagismo (bulas)"),
    ("pipeline/68_vincular_atc_pendente.py",
     "vínculo ATC — 2ª passada, pelos sinônimos INN"),
    ("pipeline/90_validacao.py", "validação estrutural"),
]

VERIFICACOES = [
    ("tests/teste_normalizacao.py", "normalizador"),
    ("tests/teste_schema.py", "invariantes do esquema"),
    ("tests/verificacao_20_substancias.py", "substâncias (independente)"),
    ("tests/verificacao_30_produtos.py", "produtos (independente)"),
    ("tests/verificacao_50_regras.py", "regras de administração (independente)"),
    ("tests/teste_motor_horarios.py", "motor de horários (casos clínicos)"),
    ("tests/verificacao_motor_horarios.py", "motor de horários (independente)"),
    ("pipeline/traducao_interacao.py", "tradução de interação (cobertura)"),
    ("rules/_prioridade.py", "tabela de prioridade (autoteste)"),
    ("tests/teste_motor_conciliacao.py", "motor de conciliação (casos clínicos)"),
    ("tests/verificacao_motor_conciliacao.py", "motor de conciliação (independente)"),
    ("app/busca.py", "serviço de busca (autoteste)"),
    ("tests/teste_aplicacao.py", "aplicação (fluxo do usuário)"),
    ("tests/verificacao_aplicacao.py", "aplicação (independente)"),
    ("tests/teste_ponta_a_ponta.py", "atendimento completo, ponta a ponta"),
    ("tests/teste_regressao.py", "regressão das fases anteriores"),
    ("tests/teste_ml.py", "garantias de Machine Learning (Fase 7)"),
    ("tests/teste_integracao_ml.py", "integração do modelo (Fase 8, V1)"),
    ("tests/verificacao_integracao_ml.py",
     "integração do modelo (Fase 8, V2 independente)"),
    ("tests/fase9_cenarios.py", "dez cenários clínicos integrados (Fase 9)"),
    ("tests/fase9_v1_sistema.py", "sistema inteiro (Fase 9, V1 funcional)"),
    ("tests/fase9_v2_independente.py",
     "sistema inteiro (Fase 9, V2 independente)"),
]

# NAO entram acima, e o motivo e o mesmo nos dois casos:
#   tests/fase9_convergencia.py   roda os ETLs — poria a bateria dentro de si
#   tests/teste_idempotencia.py   idem
#   auditoria/05_integridade_acervo.py  le 2,2 GB do acervo; e deliberado
# Ver docs/FASE9_VALIDACAO.md §"Como repetir esta validação".


def roda(rel: str, descricao: str, extra=()) -> bool:
    print("\n" + "=" * 72)
    print(">> %s  —  %s" % (rel, descricao))
    print("=" * 72, flush=True)
    t0 = time.time()
    r = subprocess.run([sys.executable, str(RAIZ / rel), *extra],
                       cwd=str(RAIZ))
    print("   (%.1fs)" % (time.time() - t0))
    return r.returncode == 0


def main() -> int:
    recriar = "--recriar" in sys.argv
    print("PIPELINE DO CONCILIADOR — %s"
          % ("reconstrução completa" if recriar else "carga incremental"))

    for i, (rel, desc) in enumerate(ETAPAS):
        extra = ("--recriar",) if (recriar and i == 0) else ()
        if not roda(rel, desc, extra):
            print("\nPIPELINE INTERROMPIDO em %s" % rel)
            return 1

    print("\n\n" + "#" * 72)
    print("# VERIFICAÇÃO 2 — independente da carga")
    print("#" * 72)
    falhou = []
    for rel, desc in VERIFICACOES:
        if not roda(rel, desc):
            falhou.append(rel)

    print("\n" + "=" * 72)
    if falhou:
        print("VERIFICAÇÕES COM FALHA: %s" % ", ".join(falhou))
        return 1
    print("PIPELINE COMPLETO — carga validada e verificada de forma independente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
