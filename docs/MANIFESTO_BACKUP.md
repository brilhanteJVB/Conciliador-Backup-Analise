# Manifesto do backup — estado anterior à Fase 10

> **Este backup corresponde ao estado imediatamente anterior à Fase 10.**

| | |
|---|---|
| Gerado em | 10/09/2026 20:59:00 |
| Estado do projeto | **FASE 9 — CONCLUÍDA / APTO PARA EMPACOTAMENTO** |
| Arquivos no backup | **163** |
| Tamanho no backup | **78.96 MB** |
| Arquivos fora do backup | 12 (312.32 MB) |
| Gerado por | `scripts/gerar_manifesto_backup.py` |

## 1. O que entrou, por diretório

| Diretório | Arquivos | Tamanho |
|---|---:|---:|
| `database` | 3 | 73.38 MB |
| `auditoria` | 11 | 1.62 MB |
| `models` | 5 | 1.05 MB |
| `ml` | 56 | 0.77 MB |
| `data` | 1 | 0.68 MB |
| `tests` | 24 | 0.45 MB |
| `docs` | 15 | 0.31 MB |
| `app` | 19 | 0.20 MB |
| `pipeline` | 20 | 0.20 MB |
| `rules` | 3 | 0.14 MB |
| `reports` | 1 | 0.12 MB |
| `(raiz)` | 3 | 0.04 MB |
| `scripts` | 1 | 0.02 MB |
| `.claude` | 1 | 0.00 MB |
| **total** | **163** | **78.96 MB** |

## 2. Estado do banco

A identidade do banco **não** é o hash do arquivo `.db`: aquele muda a cada atendimento gravado, sem que um único dado de conhecimento tenha mudado. A identidade é a **impressão digital** — contagens mais o conteúdo das colunas que viram atributo, mais o hash dos arquivos de origem. É a mesma que o ML usa para dizer sobre qual dado um modelo foi treinado.

| | |
|---|---|
| **Impressão digital dos dados** | `9e9c85ee3ffea5e0` |
| Esquema | 44 tabelas, 15 views |
| Substâncias | 2094 (1159 com ATC) |
| Interações fármaco × fármaco | 112520 |
| Registros de evidência | 153647 |
| Lotes de carga | 12 |
| Previsões gravadas | 600 |
| **Modelos ativos** | **0** |
| Atendimentos · pacientes | 0 · 0 |
| `PRAGMA integrity_check` | **ok** |

### Modelos registrados

| Nome | Versão | Algoritmo | Status | Ativo | Semente | Versão dos dados | Limiar |
|---|---|---|---|---:|---:|---|---|
| m1_existencia_interacao | 1.0-boosting | GRADIENT_BOOSTING | EXPERIMENTAL | 0 | 20260909 | `9e9c85ee3ffea5e0` | **NULL** |
| m1_existencia_interacao | 1.0-logistica | LOGISTICA | EXPERIMENTAL | 0 | 20260909 | `9e9c85ee3ffea5e0` | **NULL** |

Limiar `NULL` e `ativo = 0` são o estado correto: a view de previsão é *fail-closed*, então o sistema restaurado a partir deste backup emite **zero** achados previstos, como a Fase 7 decidiu (D-041).

## 3. Hash dos arquivos críticos

sha256 do conteúdo inteiro. São os arquivos que, se divergirem, invalidam o backup.

| Arquivo | Bytes | sha256 |
|---|---:|---|
| `database/schema.sql` | 66500 | `7f033555da20785c24bab21012eb0726edbc6a21dea88851a0fcb097078e82da` |
| `database/conciliador.db` | 76832768 | `4b04ab8eb127922b233679deba6e6f0abf93e71b61dd6b0bf44eda396417d801` |
| `pipeline/executar_tudo.py` | 4981 | `be6367351dea57b6d72d30cecf4df7dc855898cc80f474ddf4e97c00ef498c89` |
| `pipeline/_comum.py` | 10725 | `18f09f81f2e61bd69ab766b9d79d0c1e0ea51513769c33014aecd33a13139c07` |
| `pipeline/normalizacao.py` | 14999 | `e03c5beea07897997281c067bab2fc38e0ea9b4f0694eed2073ec82048a30da5` |
| `rules/motor_conciliacao.py` | 96070 | `efbd9eb423c830a02b207a38f1f201df10771727cdf4eb4b4ac31df6150a7a47` |
| `rules/motor_horarios.py` | 29092 | `3825361270104e62d444128be6be135c37b0eecf142eb67c8d8041cc3cc96402` |
| `rules/_prioridade.py` | 24406 | `8221ac39b166e4435fb4eadd704579846b7b6d0d7048270d54dc5565c7c7f3f2` |
| `app/web.py` | 26176 | `73814802590eb98cf2f52f6a25f90893a231dfddb4fe347ac9310519edfc41e8` |
| `app/servicos.py` | 42379 | `c93cd5b82b076ccfd5cecbfd1957cc02a58032a5d51100ea5800d525cf3e05fc` |
| `app/busca.py` | 18653 | `64341f7a18163eac4024106bc78af85cd94259655530ae5c76e313f8822e8009` |
| `app/relatorio.py` | 11377 | `831e949b9bee8d50e2bade5ec5d8766625113936c2e8f691575fbd387bd0ad7c` |
| `app/rotulos.py` | 11377 | `73f50bcab1821f3a32e0046b96b939fd6831b8f0dec37c0dddf87e27b72805b5` |
| `ml/_features.py` | 14674 | `d871c81d3acdb5d31247d7d00b0b1a0e01d19aedc75f0e48ff0957a67b5f4baa` |
| `ml/_comum.py` | 7075 | `9712ee68c5b1d1bedd8f99c5f7077470fe4d68dd8b7ec1c4ff8422ea7399311c` |
| `ml/70_predizer.py` | 15443 | `185c060077ef41c6652f175a900db24bc198bc88400bea0cca231fa39dd35215` |
| `models/espaco_features.json` | 3206 | `a442afc9381e7e8e7209b8473dc20d04daa38e3941dd794046a1dca8ae9e1f50` |
| `models/calibrador_m1.json` | 1849 | `7cab0faa4c197da169d995c34f287591a6859a90623aca743a8c0d1c20888af2` |
| `models/m1_1_0-boosting.json` | 507 | `c6761ca587ffb73adf4e93937cf8a7ab4c04180451465d0b03933a8b6c10f831` |
| `tests/teste_regressao.py` | 23957 | `368a785c190f3bef99a267539f6808795e1b639e584fe93f3acaad04438d4c93` |
| `tests/fase9_v1_sistema.py` | 58665 | `106f6e851855a15f1ef53d264f2cb033c2184586f684e4214b81bdbf508b837f` |
| `tests/fase9_v2_independente.py` | 29820 | `2eea1b01f9eb15e8392ffa82d0e60bc526bc1638bbcd8de4a165ac99850ffd3e` |
| `tests/fase9_cenarios.py` | 34418 | `9b95d5d7afb4e8d40da906748ba3e1174078e162f6a49367d6431040272ad8cf` |
| `tests/fase9_convergencia.py` | 11871 | `47c4342d6c6aa73ae90528b540ce9c9504775472f1991e61bb91166c8f27bd16` |
| `auditoria/05_integridade_acervo.py` | 8675 | `bfa8bb42de51c519827866ba57507e35e51a7363c51c0cc7cb79e1090f14d62a` |
| `auditoria/saida/acervo_sha256.json` | 144166 | `8be9c1859f0c849c63a4c9c4a8d291c0bd888ae8895abb220a34e41264109bb6` |
| `docs/STATUS.md` | 77208 | `772c68d8ab0fd8738d20034eb655e90e34ea14546315b889467c94ffd3680a75` |
| `docs/ARQUITETURA.md` | 17435 | `053ebae1bde8f3861e31fb8c9520d1a3822e174de74c5338ea927024f556aa62` |
| `docs/DECISIONS.md` | 70071 | `f87ac67f231ebbc68709bce5301906c632a4d919b0a7a00eb9c4c6ead94c489a` |
| `docs/ML_FASE7.md` | 44258 | `c78caf44ece7c18d19f0d4cd925a4ceec3d52d0b6d86acb8d28e8260d6370df9` |
| `docs/FASE9_VALIDACAO.md` | 22312 | `e648b001093b073b98f590aea9c6da724584c5dfaf3eec5b524c94e0e5df145d` |
| `docs/EMPACOTAMENTO.md` | 7654 | `875a1da38fb286b19e2be0438c6a6091bce4b8774c26f0bc6120f10732385614` |
| `CLAUDE.md` | 30644 | `b8a55c195cde602c827ef159510070a70938c41a2d721ab16070e09bff93589d` |
| `README.md` | 9149 | `929430b0776c5a93488a3047ed260ecf22d2edf636cf4add18a934c5fbbb5996` |

## 4. O que ficou de fora — e por quê

Nenhum arquivo foi descartado em silêncio.

| Arquivo | Tamanho | Motivo | Alternativa | Impacto na reconstrução |
|---|---:|---|---|---|
| database/conciliador_backup_*.db (5 arquivos) | 311.98 MB | fotografia de uma fase já superada (5 ou 7) | permanece no disco local, em `database/`, intocada | NENHUM — o que restaura a Fase 9 é `database/conciliador.db`, que está versionado |
| data/preview/*.html (6 arquivos) | 0.22 MB | página capturada por teste para inspeção visual | recriada por `tests/verificacao_aplicacao.py` | NENHUM |
| data/aplicacao.log | 0.12 MB | log de execução: é da máquina, não do projeto | recriado sozinho por `app/web.py` na importação | NENHUM |

## 5. Como restaurar a partir daqui

```bash
git clone https://github.com/brilhanteJVB/Conciliador-Backup-Analise.git
cd Conciliador-Backup-Analise
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"
PYTHONIOENCODING=utf-8 "$PY" pipeline/executar_tudo.py   # incremental: confere
```

A carga incremental **não muda nada** se o banco restaurado estiver íntegro — é a própria definição de idempotência do projeto (D-045). Se a bateria fechar em 972 conferências com exit 0, a restauração está correta.

**Não rode `--recriar` para conferir:** ele apaga `modelo` e `predicao`, e as 600 previsões levaram vinte minutos de treino para existir. O conhecimento é reconstruível a partir do acervo; as previsões, não.
