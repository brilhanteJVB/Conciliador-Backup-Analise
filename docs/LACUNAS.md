# Lacunas do acervo para os requisitos novos

**Data:** 09/09/2026 · **Medição:** `auditoria/04_lacunas.py` → `auditoria/saida/lacunas.json`

O sistema novo exige quatro coisas que o anterior não tinha: **posologia estruturada, horários, regras de administração e reação adversa**. Este documento mede o que o acervo sustenta e o que precisa de fonte nova.

---

## 1. Regras de administração — **o acervo sustenta**

`Drug to Food interactions Dataset.json` (DrugBank) não é só "interação com alimento": o campo `food_interactions` contém **diretivas de administração**. Medido nos 1.423 fármacos:

| Diretiva | Fármacos | Vira |
|---|---:|---|
| Tomar com ou sem alimento | 610 | `INDIFERENTE_ALIMENTO` |
| Evitar álcool | 323 | interação com hábito |
| Tomar com alimento | 315 | `COM_ALIMENTO` |
| Evitar toranja | 194 | interação com item |
| Estômago vazio / jejum | 177 | `JEJUM` |
| Separar de cátions (antiácido, cálcio, ferro) | 93 | `regra_separacao` |
| Com bastante água | 56 | `COM_AGUA_ABUNDANTE` |
| Evitar laticínio | 27 | `regra_separacao` |
| Evitar vitamina K / folhosos | 6 | interação com item |

**1.262 de 1.423 (88,7%)** têm ao menos uma diretiva detectável. Cruzando com a âncora brasileira, **600 dessas substâncias existem no Brasil** — é a base inicial da tabela `regra_administracao`.

**Ressalva:** o texto é inglês corrido, não campo estruturado. A extração é por padrão de texto e cai em `origem='FONTE_EXTERNA'` com `status_revisao='PENDENTE'`. Amostra precisa de conferência humana antes de liberar.

## 2. Regras de administração em português — **complemento, não volume**

Bulas ANVISA, 150 arquivos: 147 têm seção de posologia. Diretivas encontradas na bula inteira: 51 "não partir/triturar", 24 "com alimento", 11 "jejum", 4 "antes das refeições".

Volume baixo, mas é **fonte regulatória brasileira e já em português** — serve para validar e para escrever `texto_orientacao` sem tradução.

## 3. Intervalo de separação entre medicamentos — **LACUNA CONFIRMADA**

Busquei em `db_drug_interactions` (191.541 registros) por `hours`, `separate`, `apart`, `spacing`, `antacid`, `chelate`:

```
absorption  1.020        binding  11
hours 0 · separate 0 · apart 0 · antacid 0 · chelate 0
```

**Zero.** A fonte descreve o mecanismo ("X aumenta a absorção de Y") e nunca o intervalo.

Nas bulas, testei 12 trechos com "N horas": **1 é regra de separação real** (ácido ursodesoxicólico, "ao menos 2 horas antes ou após"); os outros 11 são meia-vida e tempo de pico. Regex tem precisão baixa demais aqui.

**Decisão:** o esquema aceita `regra_separacao.intervalo_horas = NULL` como valor legítimo, e a view devolve *"Requer separação — intervalo não estabelecido na fonte"*. O sistema diz que não sabe em vez de inventar. Preencher o intervalo é curadoria com fonte, registrada em [novas_fontes.md](novas_fontes.md).

## 4. Posologia estruturada — **não existe em fonte nenhuma, e não deveria**

`Drug finder` traz concentração (718/718), forma (718/718) e via (718/718), mas **nenhuma fonte traz frequência ou horário** — nem poderia: posologia é do paciente, não do fármaco. O dado nasce na anamnese.

O que o acervo precisa fornecer é o **limite** do que é plausível (dose máxima, intervalo mínimo), e isso está na bula, não carregado.

## 5. Reação adversa — **acervo sustenta, medido na sessão anterior**

VigiMed: 1.093.739 reações, MedDRA em português, 94% vinculam ao princípio ativo. Alimenta `substancia_reacao_adversa` **por desproporcionalidade (ROR com IC 95%)**, nunca por contagem bruta — a base é dominada por vacinas de COVID-19 por campanha de notificação.

---

## Resumo

| Requisito | Fonte no acervo | Cobertura BR | Situação |
|---|---|---|---|
| Regra de administração (alimento) | DrugBank food + bulas | 600 substâncias | **Suficiente para começar** |
| Separação de cátions | DrugBank (93) + bulas | parcial | Suficiente para o par, **sem intervalo** |
| **Intervalo de separação** | — | **0** | **Lacuna — exige fonte nova** |
| Posologia | — | — | Nasce na anamnese, não se carrega |
| Dose máxima / intervalo mínimo | bulas (não extraído) | 150 substâncias | Extrair de `texto/` |
| Reação adversa | VigiMed | 94% vinculável | Suficiente |
| Restrição por faixa etária | `TA_RESTRICAO_MEDICAMENTO` | 16.395 registros | Suficiente, **nunca usado** |
| Exame laboratorial | — | — | Sem fonte |

**Maior ganho por esforço:** ampliar o corpus de bulas. O `baixar_bulas.py` já funciona, aceita lista arbitrária e não tem limite embutido — foi rodado com 150 substâncias de 2.153. Bula é a única fonte brasileira que traz, no mesmo documento, posologia, modo de usar, interação, contraindicação e reação adversa.
