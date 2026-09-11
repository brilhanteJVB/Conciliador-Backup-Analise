# Manifesto do backup — FASE 10 — CONCLUÍDA / EMPACOTADO

> **Este backup corresponde ao estado ao fim da Fase 10: o sistema empacotado como executável Windows.**

| | |
|---|---|
| Gerado em | 11/09/2026 01:22:20 |
| Estado do projeto | **FASE 10 — CONCLUÍDA / EMPACOTADO** |
| Arquivos no backup | **176** |
| Tamanho no backup | **79.11 MB** |
| Arquivos fora do backup | 116 (492.51 MB) |
| Gerado por | `scripts/gerar_manifesto_backup.py` |

## 1. O que entrou, por diretório

| Diretório | Arquivos | Tamanho |
|---|---:|---:|
| `database` | 3 | 73.39 MB |
| `auditoria` | 11 | 1.62 MB |
| `models` | 5 | 1.05 MB |
| `ml` | 56 | 0.77 MB |
| `data` | 1 | 0.68 MB |
| `tests` | 26 | 0.50 MB |
| `docs` | 18 | 0.34 MB |
| `app` | 24 | 0.24 MB |
| `pipeline` | 21 | 0.20 MB |
| `rules` | 3 | 0.14 MB |
| `reports` | 1 | 0.12 MB |
| `(raiz)` | 3 | 0.04 MB |
| `scripts` | 3 | 0.03 MB |
| `.claude` | 1 | 0.00 MB |
| **total** | **176** | **79.11 MB** |

## 2. Estado do banco

A identidade do banco **não** é o hash do arquivo `.db`: aquele muda a cada atendimento gravado, sem que um único dado de conhecimento tenha mudado. A identidade é a **impressão digital** — contagens mais o conteúdo das colunas que viram atributo, mais o hash dos arquivos de origem. É a mesma que o ML usa para dizer sobre qual dado um modelo foi treinado.

| | |
|---|---|
| **Impressão digital dos dados** | `9e9c85ee3ffea5e0` |
| Esquema | 45 tabelas, 15 views |
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
| `database/schema.sql` | 67535 | `05a5ceed64a4da650e11b0a5ba28f9e5133a150758b083b8f2e18eebc9f08901` |
| `database/conciliador.db` | 76840960 | `0f3c81a1c2a7e006cb8036deea10da6a4efd457a9cd0c75c729eca259195acfb` |
| `pipeline/executar_tudo.py` | 5184 | `cd8436c8b503b359d6788c1e7c90931917fefab036f586a0eed43ab5f2740817` |
| `pipeline/_comum.py` | 10725 | `18f09f81f2e61bd69ab766b9d79d0c1e0ea51513769c33014aecd33a13139c07` |
| `pipeline/normalizacao.py` | 14999 | `e03c5beea07897997281c067bab2fc38e0ea9b4f0694eed2073ec82048a30da5` |
| `rules/motor_conciliacao.py` | 96070 | `efbd9eb423c830a02b207a38f1f201df10771727cdf4eb4b4ac31df6150a7a47` |
| `rules/motor_horarios.py` | 29092 | `3825361270104e62d444128be6be135c37b0eecf142eb67c8d8041cc3cc96402` |
| `rules/_prioridade.py` | 24406 | `8221ac39b166e4435fb4eadd704579846b7b6d0d7048270d54dc5565c7c7f3f2` |
| `app/web.py` | 26465 | `669215141ede0401e4b406b25bd676a9e0c8a20cc45868eddcf32e41e5dd8a42` |
| `app/servicos.py` | 42622 | `d476f806e3d7a4c455768af9537fc5b7cbc44bd903e0b5c1d06e2d0617beb397` |
| `app/busca.py` | 18864 | `86aa740bce99450ebad8ace287f1ef2602bb1c2b69b9e52a309bbf90908b5161` |
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
| `tests/fase9_v2_independente.py` | 30101 | `9634883993cdc619e02ee82f983278c0dc9e499928c78eefa7d46a0c46789002` |
| `tests/fase9_cenarios.py` | 34418 | `9b95d5d7afb4e8d40da906748ba3e1174078e162f6a49367d6431040272ad8cf` |
| `tests/fase9_convergencia.py` | 12555 | `a1e37ce0227d7b7d05c777b47eb5a2bb28d3a50c6a73fcebee89ee5e7dfd9cd8` |
| `auditoria/05_integridade_acervo.py` | 8675 | `bfa8bb42de51c519827866ba57507e35e51a7363c51c0cc7cb79e1090f14d62a` |
| `auditoria/saida/acervo_sha256.json` | 144166 | `7db8672b41a432bd507d25150f880f1b5e0604f0b1d721b0826cc676f2de6589` |
| `docs/STATUS.md` | 81789 | `2b0d851128d5c5bd4ca4a30402f962ce42547a0950765018acd576b487e38fba` |
| `docs/ARQUITETURA.md` | 18103 | `c3ddfc9ea93d0ede4bb21e9ea9b98deee662191a52a293a361168536fb756172` |
| `docs/DECISIONS.md` | 74423 | `19557fc080157802adec4a8eaa9fe72eb68f00cd0613f5aca180cb4aebe7f58b` |
| `docs/ML_FASE7.md` | 44258 | `c78caf44ece7c18d19f0d4cd925a4ceec3d52d0b6d86acb8d28e8260d6370df9` |
| `docs/FASE9_VALIDACAO.md` | 22312 | `e648b001093b073b98f590aea9c6da724584c5dfaf3eec5b524c94e0e5df145d` |
| `docs/EMPACOTAMENTO.md` | 10288 | `fec60176b1c5b9eef21cb94467e5e597fdf7dbbb25e2fe4c3361e526c31302c8` |
| `CLAUDE.md` | 33586 | `f55804b2a6eb19ec44cd2e6218851ba83925a2fe871c6ed1c9602762962326b1` |
| `README.md` | 9915 | `ca641e618f9cec23c6c4734d5f981f6ce2916bfbe130e8588a5a1d664f3b6359` |
| `app/caminhos.py` | 5555 | `5b6ae8a96ca1e68782f566d42e7fd8e16a121347f03295497bed690f97fe43f4` |
| `app/instalacao.py` | 9170 | `083ccb1cfd34a92d56b9a0a97030c5ff606ba33d6fcbad3a8edc0f7f4c4fdac1` |
| `app/atualizacao.py` | 11326 | `35825270aefea20a06a11d7fbca8d2bf3738395e59b7d69d6dc26878e6a1b9e3` |
| `app/principal.py` | 8664 | `aeb1bb7eea620e61c0609b6334ca275c3cb16248f5b774ef8670c610f6e69d8a` |
| `app/versao.py` | 3496 | `3ef84492f4c0105fbbad43745633eb87a82ef3b68d063cd4bb6ede97e7a4a00d` |
| `pipeline/80_identidade.py` | 4173 | `a7ac8f11ede544d7faec6d5a170f48b84b3c09b50603320181beb90a01714680` |
| `scripts/build_exe.py` | 6477 | `0c5b2619df9ef3fd35ef33ea834e62ef3d031fa7fad12a571d157c7b13b20839` |
| `scripts/preparar_conhecimento.py` | 8977 | `0f01b8d79f9d2b6feaeaa4cc065853b1b72b2c8a4519565810d25864b68cefc3` |
| `tests/fase10_empacotamento.py` | 29291 | `e19600c6aff49bf69f759ff6e098922c30c52e4824177118aaef054c48ed52fb` |
| `tests/fase10_v2_independente.py` | 21310 | `e57f5107eeb26995fa432457fa1e6912cc4fe1bef7b2aa4ee7160b04f18eefba` |
| `docs/GUIA_INSTALACAO.md` | 4837 | `a331beb65b06264364c3858181f8827caece13af03ff240e599f4e300416eb3c` |

## 4. O que ficou de fora — e por quê

Nenhum arquivo foi descartado em silêncio.

| Arquivo | Tamanho | Motivo | Alternativa | Impacto na reconstrução |
|---|---:|---|---|---|
| database/conciliador_backup_*.db (5 arquivos) | 311.98 MB | fotografia de uma fase já superada (5 ou 7) | permanece no disco local, em `database/`, intocada | NENHUM — o que restaura a Fase 9 é `database/conciliador.db`, que está versionado |
| dist/ (executável gerado) (84 arquivos) | 93.25 MB | executável gerado pelo build (Fase 10) | recriado por `scripts/build_exe.py` em ~17 s | NENHUM — é artefato, não fonte |
| conhecimento/ (banco distribuível) (2 arquivos) | 70.05 MB | banco distribuível, cópia do banco em uso com o atendimento esvaziado | recriado por `scripts/preparar_conhecimento.py` | NENHUM — `database/conciliador.db` está no backup |
| build/ (intermediários do build) (17 arquivos) | 16.86 MB | arquivos intermediários do PyInstaller | recriados por `scripts/build_exe.py` | NENHUM |
| data/preview/*.html (6 arquivos) | 0.22 MB | página capturada por teste para inspeção visual | recriada por `tests/verificacao_aplicacao.py` | NENHUM |
| data/aplicacao.log | 0.15 MB | log de execução: é da máquina, não do projeto | recriado sozinho por `app/web.py` na importação | NENHUM |
| config/sessao.chave | 0.00 MB | SEGREDO por instalação — assina o cookie de sessão | regenerado sozinho na próxima execução | NENHUM — e nunca deve ser versionado |

## 5. Como restaurar a partir daqui

```bash
git clone https://github.com/brilhanteJVB/Conciliador-Backup-Analise.git
cd Conciliador-Backup-Analise
PY="/c/Users/ACER/AppData/Local/Programs/Python/Python312/python.exe"
PYTHONIOENCODING=utf-8 "$PY" pipeline/executar_tudo.py   # incremental: confere
```

A carga incremental **não muda nada** se o banco restaurado estiver íntegro — é a própria definição de idempotência do projeto (D-045). Se a bateria fechar em 972 conferências com exit 0, a restauração está correta.

**Não rode `--recriar` para conferir:** ele apaga `modelo` e `predicao`, e as 600 previsões levaram vinte minutos de treino para existir. O conhecimento é reconstruível a partir do acervo; as previsões, não.
