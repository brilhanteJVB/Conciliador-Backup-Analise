# Integração do modelo preditivo — Fase 8

**Data:** 10/09/2026 · Decisões **D-046** e **D-047**
**Estado:** caminho completo, testado de ponta a ponta, **desligado em produção**

---

## O que este documento responde

Como uma previsão de modelo chega — ou não chega — ao farmacêutico, e por quais
travas ela passa antes disso. É o fecho da costura que a Fase 7 deixou pronta
e desligada (`ML_FASE7.md` §9.4).

A pergunta que ordena o desenho é uma só: **o que impede uma estimativa
estatística de ser lida como um fato clínico?** A resposta não pode ser
"disciplina de quem programa". Tem de ser estrutura.

---

## 1. A cadeia, inteira

```
ml/  (fora do caminho determinístico)
  60_registrar_modelo.py   grava `modelo` com semente, versão dos dados,
                           espaço de atributos, limitações, status EXPERIMENTAL
  80_fila_curadoria.py     grava `predicao` com probabilidade, calibrada,
                           explicação e timestamp — status NAO_REVISADA
        │
        ▼   o modelo escreve no banco; o motor lê o banco. Nada é importado.
database/  vw_predicao_liberada     ← AS QUATRO TRAVAS ESTÃO AQUI
        │
        ▼
rules/motor_conciliacao.py  módulo 13 → achado natureza='PREVISTO'
        │
        ▼
app/    web.py           separa `documentados` de `previstos`
        servicos.py      detalhe_previsao() segue `predicao.<id>`
        templates/       bloco próprio · painel de rastreabilidade
        relatorio.py     seção própria no impresso e no texto puro
```

**`rules/` e `app/` não importam nada de `ml/`.** Verificado lendo o
código-fonte em `tests/teste_ml.py`, junto com a ausência de `import sklearn`,
`joblib`, `pickle` e `numpy` no caminho determinístico. Consequência prática: o
`.exe` da Fase 10 concilia sem carregar scikit-learn.

---

## 2. As quatro travas

`vw_predicao_liberada` só devolve linha quando **todas** valem:

| # | Trava | Por quê |
|---|---|---|
| 1 | `modelo.ativo = 1` | experimental não sai do laboratório |
| 2 | `modelo.status = 'HOMOLOGADO'` | homologar é ato humano registrado |
| 3 | `limiar_alerta` declarado **e** atingido pela probabilidade calibrada | **fail-closed**: `NULL` é o padrão e significa "não emite nada" |
| 4 | **o par não tem interação documentada** | onde há documento, o achado vem do documento |

Mais uma: previsão com `status='REVISADA_RECUSADA'` não volta.

A quarta trava é a que resolve estruturalmente o conflito regra × modelo. Não há
reconciliação a fazer, nem alerta duplicado, nem hierarquia a arbitrar: a
previsão simplesmente não existe onde existe evidência. O V2 provoca esse caso
de propósito — insere uma previsão de **0,999** para um par documentado — e
confirma que ela não aparece, enquanto o achado documentado permanece.

O `limiar_alerta` é propriedade da **versão** do modelo, escolhido na validação
e gravado ao lado das métricas que o justificam. Um modelo homologado por
engano, sem limiar, continua produzindo zero achados.

**Hoje: nenhum modelo ativo → a view devolve zero linhas → o módulo 13 não
produz nada → o sistema se comporta exatamente como antes de existir ML.**
Isso é o desejado (D-041) e há trava de regressão para isso.

---

## 3. O que uma previsão registra

| Campo do `achado` | Valor | Por quê |
|---|---|---|
| `origem_achado` | `MODELO` | |
| `natureza` · `status_informacao` | `PREVISTO` · `PREVISTO` | `CHECK` do esquema exige que andem juntos |
| `probabilidade_modelo` | a **calibrada** | é a que corresponde à frequência real (ML_FASE7 §6.4) |
| `origem_afirmacao` | `predicao.<id>` | daí se chega a modelo, versão, algoritmo, semente, versão dos dados, limiar, protocolo, explicação e timestamp |
| `metodo_deteccao` | `MODELO_<nome>_<versão>` | legível na tela sem consulta |
| `gravidade_fonte` | **NULL** | o modelo não gradua. Nunca |
| `nivel_evidencia` | **NULL** | previsão não tem nível de evidência |
| `confianca_sistema` | `BAIXA`, sempre | `_prioridade.confianca()` força para `PREVISTO` |
| `prioridade` | `INFORMATIVO` | teto por definição, não por cálculo — D-047 |
| `classificacao` | `POSSIVEL` | nunca `CONFIRMADO` |
| `requer_revisao_profissional` | `1` | |
| `grupo_chave` | `PREVISTA:a-b` | distinta de `PAR:a-b`: previsto e documentado nunca se agrupam |
| linhas em `achado_evidencia` | **nenhuma** | previsão não tem evidência, e a ausência tem de aparecer |

---

## 4. O que o farmacêutico vê

**Na tela de resultados** — bloco próprio, `id="bloco-previsto"`, borda
tracejada roxa, **depois** de todos os blocos de prioridade, com o cabeçalho:

> **Isto não é alerta e não é interação documentada.** Nenhuma bula, artigo ou
> base do acervo afirma os pares abaixo. São estimativas estatísticas de um
> modelo, que calcula a probabilidade de o par *estar documentado em alguma
> base* — não a gravidade e não o risco. Não contam nos indicadores de
> prioridade acima.

Cada linha mostra **Evidência documental: nenhuma**, a probabilidade, a
confiança do sistema e o modelo. No painel de indicadores há um contador
próprio, *"Previstos (sem documento)"*, fora da escala de prioridade.

**No detalhe do achado** — a declaração de ausência de evidência, seguida do
painel de rastreabilidade (origem, modelo, versão, algoritmo, probabilidade
bruta e calibrada, limiar, atributos, protocolo de validação, versão dos dados,
semente, data, situação da previsão) e da lista *"O que o modelo pesou"*, com o
aviso de que a contribuição é **aproximada, não é SHAP e não é mecanismo
farmacológico**. Fecha com as limitações declaradas do modelo, lidas do banco.

Se o modelo for desativado depois de o achado ter sido gravado, o painel some e
a tela diz que *"a previsão que originou esta linha não está mais liberada"* —
em vez de exibir um número órfão.

**No relatório** (HTML e texto puro) — seção separada, depois dos achados, com
a mesma declaração. É onde misturar previsão com fato teria a consequência mais
duradoura, porque o relatório é o que sai impresso.

---

## 5. Ausência declarada, nunca silêncio

Quando há modelo ativo e um par **não** foi pontuado (ou ficou abaixo do
limiar), o motor registra em `nao_avaliado` com motivo
`PAR_NAO_PONTUADO_PELO_MODELO`:

> O modelo ativo não pontuou este par, ou a probabilidade ficou abaixo do limiar
> de alerta. Isso **não** é o modelo afirmando que não há interação.

É a mesma invariante de sempre: ausência de alerta nunca é ausência de risco.

---

## 6. Verificação

| | |
|---|---:|
| **V1** `tests/teste_integracao_ml.py` | 59 conferências |
| **V2** `tests/verificacao_integracao_ml.py` | 42 conferências, caminho independente |
| `tests/teste_ml.py` (regressão) | 44 → **61** travas |
| `pipeline/90_validacao.py` | **+8** checagens da integração |
| Bateria completa | exit 0, **445** verificações |

Ambos os testes trabalham numa **cópia** do banco: exercitar a integração exige
homologar um modelo, e homologar no banco de produção seria o teste ligando
aquilo que a Fase 7 decidiu manter desligado.

O V2 procura, por caminho independente (SQL cru e HTML, sem as estruturas do
motor), os oito modos de falha: previsão como fato, perda de rastreabilidade,
vazamento entre pacientes, erro de probabilidade, paciente errado, duplicação,
conflito regra × modelo e regressão na aplicação. Nenhum encontrado.

---

## 7. Como homologar um modelo, quando houver motivo

Não há atalho, e é de propósito:

```sql
UPDATE modelo SET limiar_alerta = <valor escolhido na validação>,
                  status = 'HOMOLOGADO'
 WHERE nome = 'm1_existencia_interacao' AND versao = '<versão>';
UPDATE modelo SET ativo = 0 WHERE problema = '<mesmo problema>' AND ativo = 1;
UPDATE modelo SET ativo = 1 WHERE nome = '...' AND versao = '<versão>';
```

O índice único parcial impede dois ativos para o mesmo problema; o `CHECK`
impede ativar o que não está homologado. **Não faça isto sem os rótulos humanos
que a Fase 7 mostrou faltarem** — ver `ML_FASE7.md` §9.2.

---

## 8. Limitações

1. **O caminho está pronto e desligado.** A decisão da Fase 7 (D-041) não
   mudou: no regime realista o modelo tem recall 0,56 e precisão 0,39.
2. **O motor lê previsões pré-calculadas**, não roda modelo. Par não pontuado é
   declarado, nunca silenciado.
3. **A cobertura da fila é parcial** — 600 pares gravados, de 581.201
   pontuados. Um uso real exigiria pontuar sob demanda ou ampliar a fila.
4. **Nada disto é validação clínica.** O projeto tem um modelo experimental de
   previsão de *existência de interação documentada*, validado
   computacionalmente. Nenhum farmacêutico avaliou nenhuma previsão dele.
