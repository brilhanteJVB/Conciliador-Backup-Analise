# Novas fontes

Registro exigido pela especificação. Uma entrada por fonte considerada para preencher lacuna do acervo.

**Estado dos itens abaixo: `CANDIDATA`** — identificadas a partir das lacunas medidas em [LACUNAS.md](LACUNAS.md). Nenhuma foi consultada ou baixada ainda. Ao consultar, preencher data e o que foi obtido, e mudar o estado para `EM_USO` ou `DESCARTADA`.

Prioridade da especificação: bases científicas → governamentais → regulatórias → literatura → bases farmacológicas reconhecidas → acadêmicas. Sites comerciais e blogs não servem como fonte principal.

---

## Lacuna 1 — intervalo de separação entre medicamentos

A mais grave: zero registros no acervo (ver LACUNAS §3). Sem ela, o motor de horários detecta que dois itens **precisam** ser separados mas não diz por quanto tempo.

| # | Fonte | Tipo | URL | Confiabilidade | Por que |
|---|---|---|---|---|---|
| 1.1 | **Bulário Eletrônico ANVISA** — seção "Modo de usar" | REGULATORIA | `consultas.anvisa.gov.br/#/bulario/` | ALTA | Já acessível: `baixar_bulas.py` funciona e traz o texto completo. Brasileira, em português, sem custo. **Melhor caminho.** |
| 1.2 | **DailyMed (NIH/FDA)** — seção *Dosage and Administration* | REGULATORIA | `dailymed.nlm.nih.gov` | ALTA | Bulas americanas em XML estruturado (SPL), com API aberta. Traz intervalo explícito onde a bula BR é omissa. |
| 1.3 | **RENAME / Formulário Terapêutico Nacional** | GOVERNAMENTAL | Ministério da Saúde | ALTA | RENAME 2024 já está no acervo; o Formulário Terapêutico, não. Traz orientação de administração em português. |
| 1.4 | Stockley's Drug Interactions | LITERATURA | licença paga | ALTA | Referência da área, mas **não aberta**. Só se a instituição tiver acesso. |
| 1.5 | Micromedex / Lexicomp | COMPILACAO | licença paga | ALTA | Mesma restrição. Citados como referência no acervo (`Drug finder`), sem acesso verificado. |

**Encaminhamento:** tentar 1.1 e 1.2 nesta ordem. São abertas, regulatórias e cobrem o que falta. Nada extraído delas entra como `APROVADO` sem conferência humana.

## Lacuna 2 — restrição por faixa etária e paciente idoso

O acervo tem `TA_RESTRICAO_MEDICAMENTO.csv` (16.395 registros), que basta para pediatria/geriatria básica. Para critério de inadequação no idoso, falta instrumento:

| # | Fonte | Tipo | Confiabilidade | Por que |
|---|---|---|---|---|
| 2.1 | **Critérios de Beers (AGS)** | LITERATURA | ALTA | Padrão internacional de medicamento potencialmente inadequado no idoso. Publicado em periódico indexado. |
| 2.2 | **STOPP/START** | LITERATURA | ALTA | Complementar a Beers; inclui omissão de prescrição, não só excesso. |
| 2.3 | **Consenso Brasileiro de Medicamentos Inadequados para Idosos** | LITERATURA | ALTA | Adaptado ao mercado brasileiro — preferir sobre Beers quando divergirem, registrando o conflito. |

## Lacuna 3 — exame laboratorial

Sem nenhuma fonte no acervo. Módulo medicamento × exame fica **fora do escopo da primeira versão** e é declarado como não avaliado no relatório, em vez de silenciado.

| # | Fonte | Tipo | Confiabilidade | Por que |
|---|---|---|---|---|
| 3.1 | LOINC | BASE_CIENTIFICA | ALTA | Vocabulário de exames; resolve a nomenclatura, não a interferência. |
| 3.2 | Bulas, seção "Alterações em exames laboratoriais" | REGULATORIA | ALTA | Fonte real da interferência analítica. Depende de ampliar o corpus de bulas. |

## Lacuna 4 — gravidade não graduada

58,3% das interações do sistema anterior estão `NAO_DETERMINADA` porque **a fonte não gradua** (DDInter marca 47.182 pares como `Unknown`). Não há processamento que recupere isso.

| # | Fonte | Tipo | Confiabilidade | Por que |
|---|---|---|---|---|
| 4.1 | **Curadoria farmacêutica** sobre a fila priorizada | CURADORIA | ALTA | Única saída real. A fila por impacto de balcão já existe no acervo (`banco/curadoria/gravidade_indeterminada.csv`, 300 mais urgentes). |
| 4.2 | Bula, seção "Interações medicamentosas" | REGULATORIA | ALTA | Dá gravidade implícita ("contraindicado", "usar com cautela") para os pares que a bula cita. |

## Lacuna 5 — segunda fonte que gradue gravidade (descoberta na Fase 5)

**Estado: `CANDIDATA`.** Medido em 09/09/2026, com as duas bases já carregadas.

O esquema foi desenhado com unicidade por fonte (D-016) justamente para que a
discordância entre fontes fosse detectável, e `vw_conflito_gravidade` existe
para isso. Ela devolve **zero** — e não porque as fontes concordem: das duas
bases de interação carregadas, **só o DDInter gradua**. O
`db_drug_interactions` descreve o efeito e não gradua nada. Há 17.750 pares
afirmados pelas duas, e em nenhum deles pode haver conflito de gravidade,
porque só um lado se pronuncia.

Consequência prática: a máquinaria de conflito do motor está construída e
testada, mas hoje **só com cenário construído dentro da transação do teste**.
Ela passa a valer sobre dado real no dia em que entrar uma segunda fonte
graduada.

| # | Fonte | Tipo | Confiabilidade | Por quê |
|---|---|---|---|---|
| 5.1 | **Bula ANVISA, seção "Interações medicamentosas"** | REGULATORIA | ALTA | Dá gravidade implícita ("contraindicado", "usar com cautela") para os pares que a bula cita. Já está no acervo; falta extrair. É o caminho mais barato. |
| 5.2 | **Curadoria farmacêutica sobre fila priorizada** | CURADORIA | ALTA | Única saída para os pares que nenhuma fonte gradua. Exige gente, não código. |
| 5.3 | ONC High Priority DDI List | LITERATURA | ALTA | Lista curta e consensual de interações de alta prioridade; serve de âncora de gravidade e de teste de sanidade. |

## Lacuna 6 — transportadores de membrana (descoberta na Fase 5)

**Estado: `CANDIDATA`.**

`papel_farmacocinetico` cobre 22 substâncias e **8 sistemas CYP**. Nenhum
transportador: P-gp, OATP1B1, OAT, OCT, MATE, BCRP. É uma parte inteira do
mecanismo de interação farmacocinética que o sistema não enxerga, e o módulo 7
declara isso.

Foi medido por que as bulas não resolvem: das 150 do acervo, **11** mencionam
qualquer enzima ou transportador, e as frases invertem a direção com
facilidade (ver D-026). Regex não tem precisão aqui.

| # | Fonte | Tipo | Confiabilidade | Por quê |
|---|---|---|---|---|
| 6.1 | **FDA, tabelas de transportadores** | REGULATORIA | ALTA | Mesma origem da tabela de CYP já usada, mesmo formato, mesma qualidade. Extensão natural. |
| 6.2 | **IUPHAR/BPS GtoPdb** | BASE_CIENTIFICA | ALTA | Já está no acervo (`08_iuphar_gtopdb/`), traz alvo e ação com direção. CC BY-SA, exige atribuição. |
| 6.3 | DrugBank, campo de transportadores | BASE_CIENTIFICA | MEDIA | Cobertura ampla, mas restrição de uso comercial e citação única para todo o conjunto (D-006). |

---

## Regras para qualquer fonte nova

1. Registrar aqui **antes** de carregar: fonte, URL, tipo, data, o que foi obtido, motivo.
2. Toda linha carregada entra com `origem` e `evidencia` apontando para a fonte. Sem exceção.
3. Fonte comercial sem acesso verificado **não é citada** como se tivesse sido consultada.
4. Divergência entre fontes vai para `auditoria_conflito` com `decisao='NAO_RESOLVIDO'` até alguém decidir.
5. Licença importa: IUPHAR/GtoPdb é CC BY-SA (exige atribuição) e DrugBank restringe uso comercial. Uso acadêmico em TCC tende a ser aceitável, mas é questão jurídica, não técnica.
