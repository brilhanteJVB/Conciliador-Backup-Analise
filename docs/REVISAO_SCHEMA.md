# Revisão do esquema — antes da carga

**Data:** 09/09/2026 · Revisão exigida como primeira tarefa da Fase 2.

Os 8 testes de invariante da Fase 1 passavam. Isso não significava esquema correto: eles testavam o que eu já sabia verificar. A revisão procurou o que eles não cobriam. **Nove problemas encontrados, todos corrigidos antes de qualquer carga.**

---

## P-01 — `UNIQUE(a, b, origem)` impedia registrar duas fontes para o mesmo par · **CRÍTICO**

`interacao_substancia` tinha `UNIQUE (substancia_a_id, substancia_b_id, origem)`, e `origem` é um enum (`FONTE_EXTERNA`, `CURADORIA`, …), não a fonte.

DDInter e `db_drug_interactions` afirmam ambas o par varfarina × omeprazol, ambas com `origem='FONTE_EXTERNA'`. A segunda carga seria **rejeitada em silêncio**.

Consequência: os 38.892 pares que as duas fontes têm em comum entrariam por uma só, e a detecção de conflito de gravidade — exigida pela especificação — ficaria impossível, porque só existiria um valor para comparar.

**Correção:** `fonte_id` obrigatório em todas as tabelas de afirmação, e a unicidade passa a ser por `(par, fonte)`. Uma linha por fonte; o conflito vira consulta.

## P-02 — Nenhum registro de lote de importação · **ALTO**

A especificação pede `documento_origem`, `data_importacao` e `versao` por registro. O esquema tinha `fonte` e `evidencia`, mas nada dizia *quando* e *por qual execução* a linha entrou, nem qual versão do arquivo foi lida.

**Correção:** tabela `carga` (uma linha por execução de script sobre uma fonte, com arquivo, hash, versão, contagens) e `carga_id` em `evidencia`. Toda linha carregada é rastreável até a execução que a criou.

## P-03 — `hora` aceitava `29:59` · **MÉDIO**

`CHECK (hora GLOB '[0-2][0-9]:[0-5][0-9]')` deixa passar 20–29 na primeira posição.

**Correção:** `GLOB '[0-1][0-9]:[0-5][0-9]' OR GLOB '2[0-3]:[0-5][0-9]'`. Testado com `29:59`.

## P-04 — Sem tabela de identificadores externos · **MÉDIO**

A especificação lista "identificadores externos" (DrugBank, PubChem CID, ChEMBL, UniProt, DDInterID). Não havia onde guardá-los, e sem eles a deduplicação de Nível 1 e 2 (identificador exato e alternativo) não tem sobre o que operar.

**Correção:** `substancia_identificador (substancia_id, sistema, valor)`.

## P-05 — Ambiguidade de deduplicação não tinha onde ser marcada · **ALTO**

A especificação exige que caso ambíguo **não seja fundido automaticamente** e receba marca `AMBIGUO`. O esquema não tinha campo para isso — o pipeline teria de escolher em silêncio ou descartar.

Caso real medido no acervo: `ibuprofen` casa com "ibuprofeno" **e** "levolisinato de ibuprofeno".

**Correção:** `substancia.status_resolucao` (`RESOLVIDA` / `AMBIGUA` / `PENDENTE`) e tabela `resolucao_ambigua`, que guarda o termo de origem, os candidatos e a fonte — para curadoria posterior, sem perder o dado.

## P-06 — `apresentacao` sem chave natural · **MÉDIO**

Só havia `ean`, e EAN **não é único**: medido na CMED, 183 EANs aparecem em mais de uma linha, e `-` (ausente) aparece 50.217 vezes. Usar EAN como identidade fundiria apresentações distintas.

**Correção:** `codigo_ggrem TEXT UNIQUE` (medido: 25.702 valores, zero repetições) como chave natural da CMED. `ean` continua indexado e não único; `-` vira NULL na carga.

## P-07 — `classe_atc` referenciada antes de existir · **BAIXO**

`substancia.atc_codigo REFERENCES classe_atc(codigo)` aparecia antes do `CREATE TABLE classe_atc`. SQLite resolve FK em tempo de execução e funciona, mas quebra em qualquer ferramenta que valide na ordem do arquivo.

**Correção:** `classe_atc` movida para antes de `substancia`.

## P-08 — Índices faltando em colunas de junção · **BAIXO**

`atendimento_medicamento.substancia_id`, `interacao_item.substancia_id`, `evidencia.fonte_id`, `apresentacao.produto_id` e `apresentacao_substancia.substancia_id` não tinham índice. Em SQLite, FK não cria índice sozinha.

**Correção:** cinco índices acrescentados.

## P-09 — `regra_administracao` e `regra_separacao` com a mesma falha do P-01 · **ALTO**

`UNIQUE (substancia_id, tipo)` impediria que bula ANVISA e DrugBank registrassem a mesma regra — justamente o cruzamento que permite validar uma contra a outra.

**Correção:** `fonte_id` obrigatório e unicidade por `(substância, tipo, fonte)`.

---

## Verificação de suporte aos requisitos

| Requisito | Onde | OK |
|---|---|---|
| Medicamentos / produtos | `produto` | ✔ |
| Princípios ativos | `substancia`, `substancia_sinonimo` | ✔ |
| Apresentações | `apresentacao` (+ `codigo_ggrem`) | ✔ |
| EAN | `apresentacao.ean`, indexado, não único | ✔ |
| ATC | `classe_atc`, `substancia.atc_codigo` | ✔ |
| CAS e identificadores externos | `substancia.cas`, `substancia_identificador` | ✔ |
| Posologia estruturada | `posologia` (11 campos) | ✔ |
| Horários | `horario_administracao`, `rotina_refeicao` | ✔ |
| Alimentação | `regra_administracao`, `interacao_item` | ✔ |
| Regras de administração | `regra_administracao`, `regra_separacao` | ✔ |
| Interações | 5 tabelas por tipo | ✔ |
| Fontes e evidências | `fonte`, `carga`, `evidencia` | ✔ |
| Previsões futuras | `modelo`, `predicao` | ✔ |
| Deduplicação ambígua | `status_resolucao`, `resolucao_ambigua` | ✔ |

**Resultado:** 40 tabelas, 6 views. Os 8 testes originais continuam passando e 7 novos foram acrescentados para os problemas acima.
