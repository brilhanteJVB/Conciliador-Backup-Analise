# Registro de decisões

Formato exigido pela Fase 33: **decisão · motivo · alternativas · escolha · impacto**.
Uma entrada por decisão relevante de arquitetura, dados ou Machine Learning.

---

## D-001 — Auditar antes de construir

**Data:** 08/09/2026

**Decisão.** Nenhuma linha de ETL, modelo ou interface foi escrita antes da auditoria terminar.

**Motivo.** A especificação exige essa ordem, e ela se justificou: três resultados só apareceram porque a leitura veio antes da suposição — `medicine_dataset.csv` (85 MB) tem aproveitamento zero, o VigiMed (493 MB) nunca foi usado, e o acervo já contém um sistema pronto.

**Alternativas.** Começar pelo ETL das fontes de nome reconhecível.

**Impacto.** 689 arquivos lidos, zero falhas. Quatro decisões subsequentes mudaram por causa do que a leitura mostrou.

---

## D-002 — Recomendar absorção do sistema existente em vez de reconstrução

**Data:** 08/09/2026 · **Status:** recomendação, aguarda decisão do usuário

**Decisão.** Recomendo que `Sistema Conciliador projeto` importe `banco/conciliador.db` e a curadoria humana como fontes de primeira ordem, em vez de reconstruir tudo a partir dos CSVs brutos.

**Motivo.** O acervo contém um sistema funcionando: 49 tabelas, 408.997 linhas, 24 ETLs, motor de 8 módulos, interface e modelos validados. Rodei `15_validacao.py` sem alterar nada e ele passou em todas as garantias de segurança clínica. Mais importante: `banco/curadoria/` contém informação que **não está em nenhuma fonte do acervo** — 30 substâncias do módulo tabaco com mecanismo, conduta e referências PubMed conferidas uma a uma. Nenhum script recria isso, porque a informação foi pesquisada por uma pessoa.

**Alternativas.**
1. Reconstrução completa do zero — perde a curadoria e as invariantes já testadas.
2. Absorção total sem revisão — herda eventuais erros sem examiná-los.
3. **Absorção com validação na chegada** (escolhida): importar e rodar a validação no destino; se passar, a migração foi fiel.

**Impacto.** Preserva meses de curadoria. Em contrapartida, o projeto novo herda o esquema existente em vez de partir de uma modelagem limpa. Considero a troca claramente favorável: o esquema atual já implementa as invariantes de segurança, que são a parte difícil.

---

## D-003 — Descartar `medicine_dataset.csv`

**Data:** 08/09/2026

**Decisão.** O maior dataset internacional do acervo (85,3 MB, 248.218 linhas) não entra no banco.

**Motivo.** Medição: **0 de 219.115 nomes** casam com substância brasileira. A causa foi verificada, não presumida — a coluna `name` contém marcas do mercado indiano (`augmentin 625 duo tablet`, `azithral 500 tablet`), não princípios ativos. O que sobra são 23 classes terapêuticas e 358 classes de ação em inglês, redundantes com o WHO ATC, que é fonte oficial e cobre 51,2% das substâncias brasileiras.

**Alternativas.** Recuperar parte dos nomes removendo dosagem e forma farmacêutica. Rejeitado: mesmo recuperando, seriam medicamentos não dispensados no Brasil.

**Impacto.** −85 MB, nenhuma perda de cobertura.

---

## D-004 — Descartar `Drug-disease/mapping.csv`

**Data:** 08/09/2026

**Decisão.** Os 42.200 pares fármaco–doença não entram no módulo 5.

**Motivo.** O arquivo liga `DrugID` a `DiseaseID` **sem qualificar a relação**. Não distingue "trata" de "é contraindicado em". Usar como interação fármaco–doença faria o sistema alertar contra a doença que o medicamento trata — um erro clínico grave apresentado com aparência de rigor.

**Alternativas.** Inferir a direção pela descrição textual. Rejeitado: inferência não verificada não pode virar alerta, pela invariante de que só `vw_alerta_clinico` chega ao farmacêutico.

**Impacto.** O módulo 5 continua com 488 registros não verificados. A lacuna permanece — e é honesta.

---

## D-005 — VigiMed como prioridade número um do que falta

**Data:** 08/09/2026

**Decisão.** A camada de reação adversa (Fase 8), hoje inexistente, deve ser a próxima construída, alimentada pelo VigiMed.

**Motivo.** 1.093.739 reações notificadas no Brasil, terminologia MedDRA **já em português**, e o vínculo com o medicamento foi verificado: 377.731 de 400.000 (94%) casaram numa amostra. O banco atual não tem tabela de reação adversa. É o maior ganho por esforço do acervo.

**Alternativas.** Extrair reação adversa das bulas por NLP. Complementar, não substituto: a bula traz o texto do fabricante, o VigiMed traz o que aconteceu no Brasil.

**Impacto e ressalva obrigatória.** São notificações espontâneas, não incidência. A base é dominada por vacinas de COVID-19 por causa de campanha de notificação ativa; contagem bruta mediria a campanha. O uso correto é **desproporcionalidade (PRR/ROR)** e o resultado é **sinal**, nunca prova de causalidade. Essa ressalva precisa aparecer na interface, não só na documentação.

---

## D-006 — Não tratar `DDI 2.0.json`, `DDI Database.json` e `Drug finder…deepseek.csv` como evidência primária

**Data:** 08/09/2026

**Decisão.** Os três permanecem como apoio para redação de mecanismo e como pista de curadoria, sempre com revisão humana.

**Motivo.** Procedência frágil, medida: `Drug to Food` tem uma única referência para 1.423 registros; `DDI 2.0.json` tem 46 de 80 registros citando **apenas o nome de um periódico** (`"New England Journal of Medicine"`), o que não é referência; o único DOI de todo o acervo é o do artigo que *descreve* o DrugBank, e não evidência de nenhuma interação específica. O arquivo `deepseek` traz erro de conteúdo verificável — em `Acyclovir`, `Side Effects` contém *"Varicella zoster virus (VZV) infections"*, que é indicação.

**Alternativas.** Usar como fonte plena por causa do bom aproveitamento brasileiro (64,4% no `deepseek`, o melhor do acervo). Rejeitado: cobertura alta não compensa procedência que não se sustenta.

**Impacto.** Perde-se cobertura de contraindicação e categoria de gravidez, campos que nenhuma outra fonte traz. Fica registrado como o melhor candidato a curadoria manual.

---

## D-007 — Corrigir a leitura antes de confiar no número

**Data:** 08/09/2026

**Decisão.** O inventário passou por quatro correções de método antes de ser aceito.

**Motivo.** Cada uma nasceu de um resultado que não fazia sentido:

| Sintoma | Causa | Correção |
|---|---|---|
| 2 arquivos "ilegíveis" | `chardet` disse `ascii` lendo só o início | Testar UTF-8 contra 8 MB antes de aceitar |
| CSV da ANVISA lido como **`big5`** (chinês) | idem | Só aceitar palpite se for codec latino |
| 7 arquivos com "1 coluna" | aspas contendo o separador | Parsear com cada candidato e comparar consistência |
| CMED com cabeçalho `Secretaria Executiva` | 41 linhas de banner preenchidas até 74 colunas com `;` | Exigir 60% de células preenchidas na linha de cabeçalho |
| Contagem de linhas divergindo da auditoria anterior | quebra de linha dentro de campo | Contar registros CSV; reportar as duas medidas |

**Impacto.** A contagem exata passou a bater com a auditoria anterior (43.441 vs 43.439 registros). Sem essas correções, cinco conclusões do relatório estariam erradas.

---

## D-008 — Manter as invariantes de segurança clínica herdadas

**Data:** 08/09/2026

**Decisão.** As quatro invariantes do sistema existente são condição de aceitação de qualquer código novo, não convenção.

1. `vw_alerta_clinico` é o único caminho até o farmacêutico — inferência mecanística e predição de ML não revisadas não chegam a ele.
2. **ML nunca atribui gravidade.** `predicao_ml.gravidade_sugerida` é sempre `NULL`.
3. **Discrepância nasce `NAO_DETERMINADA`.** Só humano identificado grava `NAO_INTENCIONAL`.
4. **Ausência de alerta nunca é apresentada como ausência de risco.** `SEM_INTERACAO_CONHECIDA` ≠ `SUBSTANCIA_NAO_COBERTA`.

**Motivo.** A invariante 2 não é postura: é resultado medido. O modelo rebaixava 88% das interações MAIOR. A 4 é a que mais importa no balcão, porque 47,2% das substâncias brasileiras não têm nenhum dado de interação — silêncio ali significa "não sei", não "é seguro".

**Impacto.** Limita o que o ML pode fazer. É o limite certo.

---

## D-009 — Não propor arquitetura de ML nova nesta fase

**Data:** 08/09/2026

**Decisão.** Manter o modelo existente (188 features, v2.0, calibração isotônica) e não propor fatoração de matriz nem GNN.

**Motivo.** Já foram avaliadas e descartadas por motivo **estrutural**, não de preferência: 1.103 das 2.097 substâncias não têm nenhuma aresta na matriz de interações, e são exatamente o ponto cego que motivou o projeto. Um modelo de grafo não tem o que propagar onde não há aresta. A AUC de 0,97 da literatura é split por par; a equivalente aqui é 0,9390 — o número honesto, split por fármaco, é 0,8561.

**Alternativas.** Testar GNN mesmo assim. Rejeitado nesta fase: gastaria o esforço no ponto onde o modelo já é bom, e não onde ele é cego.

**Impacto.** O próximo modelo útil é o de **relevância de alerta** (fadiga), que depende dos rótulos do piloto com dois farmacêuticos — trabalho que depende de pessoas, não de código.

---

## D-010 — Preservação do acervo original

**Data:** 08/09/2026

**Decisão.** `C:\Conteudos banco de dados tcc` é tratado como somente leitura. Nenhum arquivo foi criado, movido, alterado ou apagado lá.

**Motivo.** Regra explícita da especificação, e boa prática independente dela: o acervo é a prova de origem de tudo que o sistema afirma.

**Verificação.** Os três scripts de auditoria abrem a origem apenas para leitura e gravam exclusivamente em `Sistema Conciliador projeto/auditoria/saida/`. A única execução que tocou o acervo foi `15_validacao.py`, que é somente leitura (verificado por inspeção antes de rodar: nenhum `INSERT`, `UPDATE`, `DELETE` ou `commit`).

**Impacto.** Os 12 backups do banco (1,03 GB) permanecem onde estão. Recomendo arquivá-los, mas **não os removi** — remoção em acervo alheio não é decisão minha.

---

## D-011 — Reconstrução do zero, com o sistema anterior como fonte

**Data:** 09/09/2026 · **Decisão do usuário**, substitui a recomendação de D-002.

**Decisão.** Arquitetura própria, escrita do zero. O sistema anterior passa a ser fonte de dados, referência de resultado e teste de regressão — não base estrutural.

**Impacto e mitigação.** O risco apontado em D-002 permanece real: `banco/curadoria/` contém informação que nenhuma fonte do acervo tem. A mitigação é tratá-la como **fonte de dados**, o que a decisão permite: entra pelo pipeline com `origem='CURADORIA'` e `evidencia` apontando ao arquivo original, em vez de ser reescrita. Nada se perde; o que muda é que a arquitetura ao redor é nova.

**Ganho.** O requisito novo — posologia estruturada, horários e regras de administração — não cabia no esquema anterior, onde `dose` era TEXT e não havia entidade de horário. Reconstruir permite pôr isso no centro em vez de anexar.

---

## D-012 — Posologia estruturada como decisão de esquema

**Data:** 09/09/2026

**Decisão.** `posologia` guarda dose, unidade, vezes por dia, intervalo, via, duração e condição em colunas próprias. `texto_original` acompanha, nunca substitui. Horário é tabela própria, uma linha por horário, com `CHECK` de formato `HH:MM`.

**Motivo.** Sem isso o motor de horários não tem o que analisar: "tomar 1 comprimido 2x ao dia" é opaco para código. `dose_valor` continua aceitando NULL de propósito — no balcão o paciente frequentemente não sabe a dose, e forçar preenchimento produz dado inventado.

**Alternativas.** Texto livre com interpretação por NLP na hora da análise. Rejeitado: transforma erro de interpretação em erro clínico silencioso.

**Impacto.** Testado: `horario_administracao` recusa `'de manhã'` e aceita `'06:30'`.

---

## D-013 — Intervalo de separação nunca é inventado

**Data:** 09/09/2026

**Decisão.** `regra_separacao.intervalo_horas` aceita NULL, e NULL é o caso comum. A view devolve *"Requer separação — intervalo não estabelecido na fonte"*.

**Motivo.** Medido: **0 de 191.541** registros de `db_drug_interactions` mencionam intervalo, separação ou antiácido. Nas bulas, 1 de 12 trechos com "N horas" era regra de separação; os outros eram meia-vida. A informação não existe no acervo.

**Alternativas.** (a) Adotar 2 horas como padrão — rejeitado: é número inventado com aparência de regra. (b) Omitir o achado — rejeitado: viola "ausência de alerta nunca é ausência de risco". (c) **Declarar a necessidade sem o intervalo** — escolhida.

**Impacto.** O farmacêutico vê que há necessidade de separar e que o intervalo não foi estabelecido, o que é acionável e honesto. Preencher intervalos é curadoria com fonte, priorizada em `novas_fontes.md`.

---

## D-014 — Prioridade e gravidade são colunas diferentes

**Data:** 09/09/2026

**Decisão.** `achado.gravidade_fonte` (MAIOR/MODERADA/MENOR) vem da fonte. `achado.prioridade` (CRÍTICO→INFORMATIVO) é de exibição e considera contexto do paciente.

**Motivo.** A especificação pede a escala de risco de cinco níveis, mas as fontes graduam em três e sobre o par isolado, sem paciente. Fundir as duas escalas exigiria inventar a conversão e perderia a informação original.

**Impacto.** A fórmula que liga uma à outra ainda não existe e será documentada com justificativa por peso quando escrita — peso sem justificativa é proibido pela especificação.

---

## D-015 — M3 (gravidade por ML) não será treinado

**Data:** 09/09/2026

**Decisão.** Dos cinco modelos previstos, M3 (estimativa de gravidade) sai do escopo.

**Motivo.** O alvo está ausente em 58,3% dos casos porque **a fonte não gradua** — DDInter marca 47.182 pares como `Unknown`. Treinar sobre os 41,7% restantes aprenderia o critério de quem graduou aqueles, e o modelo seria aplicado justamente onde esse critério não existe.

**Alternativas.** Tratar `Unknown` como classe própria. Rejeitado: "não sei" não é grau de gravidade, e o modelo passaria a prever ausência de informação.

**Impacto.** Gravidade continua vindo de fonte ou de curadoria. O ML prioriza; não gradua.

---

## D-016 — Uma linha por (afirmação, fonte)

**Data:** 09/09/2026

**Decisão.** `UNIQUE` nas tabelas de afirmação inclui `fonte_id`, não `origem`.

**Motivo.** `origem` é um enum (`FONTE_EXTERNA`, `CURADORIA`…), não identifica a fonte. DDInter e `db_drug_interactions` afirmam ambas varfarina × omeprazol com `origem='FONTE_EXTERNA'`: a segunda seria rejeitada em silêncio, e os 38.892 pares comuns entrariam por uma só. Sem duas linhas não há o que comparar, e a detecção de conflito de gravidade — exigida pela especificação — ficaria impossível.

**Alternativas.** Guardar a fonte vencedora e descartar a outra. Rejeitado: escolher em silêncio é exatamente o que a Fase 20 proíbe.

**Impacto.** Mais linhas, e conflito vira consulta (`vw_conflito_gravidade`) em vez de colisão de chave.

---

## D-017 — CMED como fonte de tarja, não o código numérico da ANVISA

**Data:** 09/09/2026

**Decisão.** `canal_dispensacao` vem do campo `TARJA` da CMED, que é rótulo por extenso.

**Motivo.** O sistema anterior mapeou o código numérico `CO_TARJA` da ANVISA ao contrário e chegou a afirmar que **tramadol era venda livre** e dipirona controlada. Ler `"Tarja Vermelha sob restrição"` elimina a classe de erro inteira: não há mapa a inverter. Verificado em cinco fármacos conhecidos, todos corretos.

**Alternativas.** Corrigir o mapa numérico. Rejeitado: continuaria dependendo de um mapa que ninguém consegue conferir de cabeça.

**Impacto.** 69,2% das substâncias com canal definido. Empate entre tarjas de apresentações diferentes fica `NAO_DETERMINADO`, nunca desempatado por chute.

---

## D-018 — Normalizador copiado para o projeto, com procedência

**Data:** 09/09/2026

**Decisão.** `analise_dados/scripts/lib_norm.py` foi copiado para `pipeline/normalizacao.py`, com hash da origem no cabeçalho, e passou a ser mantido aqui.

**Motivo.** É conhecimento determinístico (tabela de sais + regras fonéticas), não arquitetura — e a decisão D-011 permite incorporar conhecimento do acervo. Depender do diretório de origem em tempo de execução impediria o `.exe` de funcionar isolado.

**Duas correções já aplicadas na cópia**, ambas descobertas por dado que não casava:
- hidratos superiores (`pentaidratado`…) não estavam na tabela de sais, e `sulfato de morfina pentaidratado` não casava com morfina;
- `ácido` qualificando um sal já removido (`maleato ácido de timolol`) sobrevivia ao esqueleto. Só sai quando vem logo após um sal — em `ácido acetilsalicílico` ele inicia o nome e fica.

**Impacto.** `tests/teste_normalizacao.py` fixa 33 casos, incluindo simetria PT/EN e não colisão entre moléculas parecidas (varfarina × vareniclina).

---

## D-019 — Tradução de classe ATC por molde, com cobertura declarada

**Data:** 09/09/2026

**Decisão.** Nomes de classe são traduzidos por molde (`{X} channel blockers` → `Bloqueadores dos canais de {X}`), com regra tudo-ou-nada. O que não é coberto fica em inglês e marcado.

**Motivo.** Tradução palavra a palavra produz português errado, porque a ordem muda: `Calcium channel blockers` virava `Cálcio canal bloqueadores`. O molde traduz a estrutura, não os termos isolados.

**Alternativas.** (a) Tradução automática por serviço externo — rejeitado: enviaria dados a terceiro e não é verificável. (b) Deixar tudo em inglês — viola a regra de idioma. (c) Traduzir pela metade — pior que o original.

**Impacto medido.** Níveis 1 e 2 (os que aparecem no relatório): **100%**. Níveis 3 e 4: 39,1% e 14,6%. Nível 5 é a própria substância e usa o nome DCB. **75,5% do total continua em inglês, declarado como não traduzido.** Ampliar o glossário é trabalho incremental e seguro.

---

## D-020 — A aplicação é a Fase 6, e as fases anteriores entregam serviços

**Data:** 09/09/2026

**Decisão.** O roteiro passou a ter uma fase explícita para a aplicação do farmacêutico: **Fase 6 de 10**, imediatamente depois dos três motores e antes do Machine Learning.

**Motivo.** O roteiro anterior ia de "paciente/posologia" — que é camada de dados — direto para "relatório". Não havia fase de interface, e isso é falha de planejamento: o objetivo do projeto é um sistema de conciliação usável, não um banco farmacológico.

**Alternativas.** (a) Construir a interface agora — rejeitado: sem regra de administração, motor de horários e motor de conciliação, as telas não teriam o que mostrar nem o que responder. (b) Deixar para o fim, depois do ML — rejeitado: o ML melhora a ordenação dos alertas, não habilita o atendimento; a aplicação tem de estar usável antes.

**Impacto.** As Fases 3–5 passam a entregar **serviços com função de entrada única e testável** (`buscar_medicamento`, `montar_agenda`, `conciliar`), não apenas tabelas. A Fase 6 fica sendo a camada de tela sobre lógica que já funciona e já tem teste — o que a encurta e impede que a regra clínica seja reescrita dentro da interface.

---

## D-021 — `origem` diz de onde veio; `metodo_extracao` diz como foi lida

**Data:** 09/09/2026

**Decisão.** As views de regra expõem `confianca_extracao`, que combina os dois campos, e o motor rebaixa o achado de DOCUMENTADO para POSSÍVEL quando a regra ainda não foi revisada.

**Motivo.** A bula da ANVISA é fonte regulatória — mas uma regra tirada dela por expressão regular pode ser leitura errada de um texto correto. `origem='BULA_ANVISA'` sozinha faria a view liberar para a tela uma extração automática como se fosse fato conferido. Medi a diferença: buscando "N horas" na bula inteira, só 1 de 12 trechos era regra de separação; o resto era meia-vida e tempo de pico.

**Impacto.** As 725 regras carregadas aparecem como `EXTRAIDA_AUTOMATICAMENTE`. Nenhuma se apresenta como revisada. A curadoria farmacêutica é que as promove.

---

## D-022 — Orientação em português por tipo, não tradução frase a frase

**Data:** 09/09/2026

**Decisão.** Cada tipo de regra tem um texto fixo em português, escrito e revisado uma vez. O inglês original é guardado como `trecho` da evidência.

**Motivo.** A regra de idioma exige português, mas traduzir automaticamente texto clínico corrido é onde erro de tradução vira erro de conduta. Como o conjunto de tipos é fechado (12), escrever 12 frases corretas cobre todos os 725 registros sem nenhuma tradução automática.

**Impacto.** 100% das regras em português, com o texto de origem preservado e auditável.

---

## D-023 — Contradição dentro de uma fonte não é gravada; entre fontes, é

**Data:** 09/09/2026

**Decisão.** Se o mesmo trecho de bula produz duas regras alimentares excludentes, **nenhuma** é gravada e o caso vai para `auditoria_conflito`. Se duas fontes diferentes discordam, as duas linhas permanecem e o conflito é registrado.

**Motivo.** São situações distintas. Dentro de um texto, ter *"com as refeições"* e *"antes das refeições"* significa que a nossa leitura foi ambígua — gravar qualquer uma seria escolher no escuro, e instrução contraditória de posologia é pior do que instrução nenhuma. Entre fontes, a divergência é informação real, e o esquema já guarda uma linha por fonte (D-016) justamente para isso.

**Impacto.** 3 bulas ambíguas registradas sem gravar regra; `diosmina` deixou de ter três orientações alimentares simultâneas.

---

## D-024 — DDInter e `db_drug_interactions` entram como fontes separadas, nunca fundidas

**Data:** 09/09/2026

**Decisão.** Cada uma das duas bases de interação entra como uma **linha própria** do mesmo par em `interacao_substancia`, com o seu `fonte_id`. Nenhuma fusão, nenhum "preencher o que falta na outra".

**Motivo.** Elas são complementares e assimétricas, e isso foi medido: o **DDInter gradua** a gravidade e **não publica descrição nenhuma**; o **`db_drug_interactions` descreve** o efeito em texto e **não gradua nada**. Fundir as duas numa linha só produziria um registro aparentemente completo cuja procedência ninguém conseguiria desfazer, e destruiria a possibilidade de detectar discordância — que é exatamente o que a unicidade por fonte (D-016) existe para preservar.

**Alternativas.** Uma linha por par, com a gravidade do DDInter e a descrição do outro. Rejeitado: cria um registro que nenhuma fonte afirma.

**Impacto.** 112.520 linhas para 94.770 pares distintos; **17.750 pares afirmados pelas duas fontes**, cada um com duas evidências no achado. Consequência honesta a declarar: **`vw_conflito_gravidade` devolve zero**, e não porque as fontes concordem — porque **só uma delas gradua**. Conflito de gravidade entre fontes é hoje estruturalmente indetectável no acervo, e só deixará de ser quando entrar uma terceira base graduada.

---

## D-025 — Contraindicação vem da seção CONTRAINDICAÇÕES da bula, não do `mapping.csv`

**Data:** 09/09/2026

**Decisão.** O módulo fármaco × doença é alimentado pela seção **CONTRAINDICAÇÕES** das 150 bulas ANVISA, cruzada com um vocabulário curado de 46 condições clínicas em português.

**Motivo.** D-004 recusou `Drug-disease/mapping.csv` (42.200 pares) por um motivo que continua de pé: ele liga fármaco a doença **sem qualificar a relação**, e o sistema alertaria contra a doença que o medicamento trata. A seção de contraindicações não tem esse defeito: a relação está declarada no título da seção **e** no verbo da frase. É fonte regulatória brasileira, em português, e o trecho literal fica gravado em `interacao_doenca.trecho_origem`.

**Alternativas.** Inferir a direção do `mapping.csv` pela descrição textual — rejeitado de novo, pelo mesmo motivo. Ficar sem o módulo 2 — rejeitado: existia fonte no acervo.

**Impacto.** **182 linhas, 102 substâncias, 28 condições distintas** — 94 contraindicações e 88 precauções. Cobertura de 4,9% das substâncias, que é pouco e está declarado. **Todas `PENDENTE`**, apresentadas como `EXTRAIDO_AUTOMATICAMENTE` e natureza `POSSIVEL`, nunca documentadas. Três guardas de precisão no extrator: termo e verbo na mesma frase; "não foi estabelecido" é ausência de dado e não entra; "sem orientação médica" é precaução e não proibição.

---

## D-026 — Papel farmacocinético só da tabela da FDA; as bulas foram medidas e recusadas

**Data:** 09/09/2026

**Decisão.** `papel_farmacocinetico` é alimentada exclusivamente pela tabela de fármacos-índice da FDA (31 linhas, 28 aproveitadas). As bulas **não** são usadas para isso.

**Motivo.** Foi medido antes de decidir: das 150 bulas, **11** mencionam alguma enzima ou transportador, e as frases não são extraíveis com precisão aceitável. O exemplo que fechou a questão é real, da bula de carbamazepina: *"A coadministração de indutores de CYP3A4 com carbamazepina pode diminuir as concentrações plasmáticas de carbamazepina"*. Um regex que procure "indutor" perto de "CYP3A4" conclui que a carbamazepina **é** indutora. Ela é — mas não por causa desta frase, que fala de indutores agindo **sobre** ela. Acertar pelo motivo errado é o mesmo defeito de D-004, e a frase seguinte erraria.

**Alternativas.** Extrair com regex e marcar `PENDENTE`. Rejeitado: 11 substâncias não compensam poluir a base com afirmações invertidas que alguém teria de desfazer uma a uma.

**Impacto.** 28 linhas, 22 substâncias (1,1%), 8 sistemas CYP, **nenhum transportador**. Pouco volume, alta confiança, zero inferência na carga. A lacuna fica declarada em `novas_fontes.md` em vez de preenchida com leitura duvidosa. Um ajuste foi necessário: a FDA escreve pelo nome adotado nos EUA (`rifampin`) e o Brasil pela DCB (`rifampicina`); a equivalência de **nomenclatura** está declarada no carregador e recuperou 5 linhas — inclusive o indutor enzimático de maior impacto de balcão do conjunto.

---

## D-027 — Prioridade é tabela explícita com justificativa por peso; idade não entra nela

**Data:** 09/09/2026

**Decisão.** A prioridade de exibição vive em `rules/_prioridade.py`, como uma tabela `(módulo, chave) → (prioridade, por quê)`. Cada linha carrega o texto que explica o peso, e esse texto vai para o campo `justificativa_prioridade` do achado. Modificadores de contexto são três, e só três: anafilaxia declarada força CRÍTICO; informação insuficiente limita a INFORMATIVO; confiança baixa rebaixa um degrau.

**Motivo.** A especificação proíbe peso inventado, e prioridade é a decisão mais contestável do sistema — é ela que decide o que o farmacêutico lê primeiro numa fila. Espalhada dentro do motor, discutir um peso exigiria ler o motor inteiro.

**A idade ficou de fora de propósito.** O motor lê a idade, escreve no contexto do achado e **não deixa que ela mexa na prioridade**. Sem instrumento carregado (Beers, STOPP/START, Consenso Brasileiro), o sistema não tem base para afirmar que um fármaco é inadequado no idoso, e afirmar mesmo assim seria inventar regra clínica. A lacuna está registrada em `novas_fontes.md`, Lacuna 2, e o próprio motor a declara em `nao_avaliado` quando o paciente tem 65 anos ou mais.

**Alternativas.** Fórmula numérica com pesos somados. Rejeitado: número somado esconde a regra e torna impossível justificar um caso ao farmacêutico. Deixar a idade subir a prioridade "por precaução" — rejeitado: precaução sem fonte é invenção.

**Impacto.** 33 linhas de tabela, todas com justificativa, verificadas por autoteste. Efeito medido na coorte: **54,4% dos achados saem com confiança BAIXA e por isso um degrau abaixo** — consequência direta de o acervo ser majoritariamente extração automática não revisada, e não um defeito do cálculo.

---

## D-028 — Duplicidade terapêutica é no 4º nível ATC, não no 5º

**Data:** 09/09/2026

**Decisão.** O módulo de duplicidade agrupa substâncias distintas pelo **4º nível** da classificação ATC (5 caracteres), não pelo 5º.

**Motivo.** O plano original dizia "ATC 5º nível igual". Medindo no banco antes de escrever o teste: **zero** grupos de 5º nível contêm duas substâncias diferentes — e não podia ser diferente, porque o 5º nível **é** a substância. A regra seria letra morta. No 4º nível há **248 grupos**, e são exatamente os clinicamente certos: dois inibidores da bomba de prótons, dois inibidores da ECA, duas estatinas, dois bloqueadores do receptor da angiotensina.

**Alternativas.** Manter o 5º nível e cobrir só a repetição da mesma substância. Rejeitado: deixaria de fora a duplicidade que mais importa no balcão, que é a de finalidade.

**Impacto.** A regra passou a disparar. Ressalva declarada no texto do achado: o sistema guarda **um** código ATC por substância, então substâncias com mais de uma indicação podem ficar fora do agrupamento.

---

## D-029 — Gravidade que a fonte não publica fica em prioridade baixa, e é contada à parte

**Data:** 09/09/2026

**Decisão.** Interação documentada cuja gravidade **nenhuma** fonte graduou sai com `gravidade_fonte='NAO_DETERMINADA'`, `status_informacao='NAO_DETERMINADO'`, prioridade **BAIXO**, revisão exigida, e uma linha própria em `nao_avaliado` com motivo `GRAVIDADE_NAO_GRADUADA_NA_FONTE`.

**Motivo.** São **65,8% das linhas de interação** (74.061 de 112.520). Há três saídas e duas são erradas. Subir por precaução seria mentir sobre a fonte e enterrar os alertas graduados no meio do ruído. Esconder seria pior: a interação existe. Sobra a terceira — exibir em prioridade baixa, dizer por quê, e **contar separadamente**, para que o número apareça no resumo em vez de se dissolver.

**Alternativas.** Tratar como MODERADA por precaução. Rejeitado: é atribuir gravidade que o sistema não tem. Omitir do relatório. Rejeitado: ausência de alerta nunca é ausência de risco.

**Impacto.** Na coorte sintética, 19 de 68 achados (27,9%) têm gravidade não determinada. O resumo estruturado tem um campo próprio (`n_informacao_insuficiente`) para que a interface possa mostrar esse número sem recontá-lo.

---

## D-030 — A conciliação classifica a situação; nunca a intencionalidade

**Data:** 09/09/2026

**Decisão.** O motor calcula a **situação** de cada par (conciliado, divergência, possível divergência, informação insuficiente, revisão necessária) e grava `intencionalidade='NAO_DETERMINADA'` sempre. O `CHECK` de `conciliacao_par` recusa qualquer outro valor sem `avaliado_por` preenchido.

**Motivo.** Diferença não é erro. Dose prescrita 10 mg e relatada 20 mg pode ser ajuste posterior que a lista não acompanhou, decisão do prescritor, ou erro de conciliação — e nada no dado distingue os três. Dizer "erro" é ato clínico com nome e CRF, não saída de script. A restrição está no esquema, não na disciplina de quem escreve o código.

**Alternativas.** Inferir intencionalidade por heurística (ex.: dose maior = erro). Rejeitado: inferência não verificada não pode virar acusação num prontuário.

**Impacto.** Verificado por invariante em duas frentes: o motor nunca grava outro valor, e o banco recusa se alguém tentar.

---

## D-031 — Sem lista prescrita não há divergência: há ausência de lista

**Data:** 09/09/2026

**Decisão.** Quando o atendimento não tem nenhum item na lista `PRESCRITA`, o motor **não** emite divergência nenhuma. Emite uma declaração em `nao_avaliado` com motivo `SEM_CORRESPONDENCIA_ENTRE_LISTAS`, e os demais módulos analisam a farmacoterapia relatada normalmente.

**Motivo.** É o atendimento de balcão mais comum: o paciente chega sem receita. Sem esta regra, cada um dos seus medicamentos viraria uma divergência `SO_NO_RELATO`, e um paciente com 12 itens abriria o relatório com 12 alertas de conciliação que não existem. Fadiga de alerta fabricada por defeito de modelagem.

**Alternativas.** Emitir as divergências e deixar a interface filtrar. Rejeitado: a especificação é explícita — a interface não reimplementa lógica, e um dado errado filtrado na tela continua errado no banco.

**Impacto.** Testado como caso próprio na verificação funcional (caso 23).

---

## D-032 — A chave de agrupamento identifica o problema, nunca a linha

**Data:** 09/09/2026

**Decisão.** Nenhuma `achado.grupo_chave` pode conter id de `atendimento_medicamento`. Chaves são construídas sobre substância, doença, item, hábito ou classe.

**Motivo.** Defeito real, encontrado pelo **teste de propriedade** da verificação 2 (monotonicidade: acrescentar um medicamento nunca pode apagar um achado). As orientações de administração estavam agrupadas por linha, e o efeito prático era duplo: o mesmo "como tomar" aparecia duas vezes quando o paciente trazia marca e genérico do mesmo princípio ativo, e o agrupamento passava a depender de quem foi cadastrado primeiro.

**Alternativas.** Manter a chave por linha e deduplicar na tela. Rejeitado pelo mesmo motivo de D-031.

**Impacto.** Uma orientação por substância. Trava de regressão e invariante da verificação 2 impedem o retorno.

---

## D-033 — A anotação do profissional é presa a uma chave estável, nunca ao id do achado

**Data:** 09/09/2026

**Decisão.** A revisão de um achado e a avaliação de uma divergência ficam em `anotacao_profissional`, indexadas por uma **chave estável** — `achado.grupo_chave` para o achado, `(tipo de divergência + substância)` para a divergência. Nunca por `achado.id` ou `conciliacao_par.id`.

**Motivo.** O achado é **recalculado a cada análise**, e é assim que tem de ser: mudar o dado do paciente precisa mudar o resultado junto. O `id` muda a cada recálculo. Presa ao id, a revisão do farmacêutico desapareceria na primeira reanálise — e ele descobriria isso depois de já ter revisado vinte alertas. É a mesma lição que o sistema anterior aprendeu ao parear avaliadores para o kappa de Cohen.

**Alternativas.** Congelar o achado ao gravar e anotar sobre a linha congelada. Rejeitado: o congelamento faz a tela mostrar um resultado velho depois de o farmacêutico corrigir um dado, que é pior.

**Impacto.** O profissional pode revisar, corrigir um dado, reanalisar e continuar vendo o que já revisou. Verificado no eixo 4 da verificação independente e travado na regressão.

---

## D-034 — Intencionalidade só entra no banco com nome de profissional, e só por essa porta

**Data:** 09/09/2026

**Decisão.** A aplicação nunca grava `conciliacao_par.intencionalidade` diferente de `NAO_DETERMINADA` por conta própria. O único caminho é o formulário de avaliação da divergência, que **exige** o nome do profissional; a anotação é gravada com esse nome e reaplicada às análises seguintes com `avaliado_por` preenchido.

**Motivo.** D-030 estabeleceu que o motor classifica a situação e nunca a intenção. A aplicação é onde a tentação de "resolver" isso aparece — um botão de "marcar como erro" sem assinatura seria trivial de escrever. O `CHECK` do esquema recusa, e a camada de serviço recusa antes, com uma mensagem que explica por quê.

**Alternativas.** Deixar o registro anônimo, já que a aplicação é local e de uso individual. Rejeitado: a afirmação "isto foi um erro de conciliação" é ato clínico, e ato clínico sem autor não é ato clínico.

**Impacto.** Duas barreiras independentes, verificadas por teste: o serviço e o banco.

---

## D-035 — `conciliacao_par` apaga em cascata com o medicamento

**Data:** 09/09/2026

**Decisão.** `conciliacao_par.item_prescrito_id` e `item_relatado_id` passaram a ter `ON DELETE CASCADE`.

**Motivo.** Defeito real, encontrado pela verificação independente da Fase 6. Sem a cascata, remover um medicamento **depois** de uma análise gravada era impossível: a linha de pareamento ainda apontava para ele e o banco recusava a exclusão. Na prática o farmacêutico ficava preso ao primeiro resultado — corrigir um item exigiria apagar o atendimento inteiro. A verificação funcional não pegou, porque removia antes de analisar.

Um pareamento é uma afirmação sobre **duas linhas específicas**: se uma deixa de existir, o pareamento perdeu o objeto. O cabeçalho da conciliação permanece, e a tela sempre mostra o recálculo ao vivo.

**Alternativas.** `ON DELETE SET NULL` — rejeitado: o `CHECK` que exige ao menos um dos dois lados falharia. Apagar os pares na camada de serviço — rejeitado: a regra pertence ao esquema, onde ninguém a esquece.

**Impacto.** A conciliação **gravada** é um retrato do momento e fica desatualizada quando o atendimento muda. A aplicação diz isso ao remover um item, e a tela nunca mostra o retrato velho — mostra o recálculo.

---

## D-036 — A aplicação não tem SQL clínico, e isso é verificado no código-fonte

**Data:** 09/09/2026

**Decisão.** `app/web.py` não contém nenhuma consulta SQL. Todo acesso ao conhecimento farmacológico passa por `app/busca.py` ou pelos motores; toda escrita passa por `app/servicos.py`. A verificação independente **lê o código-fonte** e reprova se `web.py` mencionar qualquer tabela de interação ou regra, ou contiver sintaxe de SQL.

**Motivo.** A especificação proíbe reimplementar regra na interface, e essa proibição não se sustenta por disciplina: sustenta-se por teste. Uma consulta SQL numa rota é o primeiro passo para a segunda implementação da regra — começa como "só um `SELECT` para mostrar a gravidade" e termina com a tela discordando do motor.

Junto vai um teste mais forte, e é o que dá nome ao eixo 1 da verificação independente: o resultado exibido na tela é comparado, achado a achado, com o que `conciliar_atendimento` devolve chamado diretamente. Se a interface produzisse resultado próprio, os dois divergiriam.

**Alternativas.** Confiar na revisão de código. Rejeitado pelo motivo acima.

**Impacto.** Três invariantes de arquitetura verificadas automaticamente: interface sem SQL, templates sem cálculo de prioridade ou gravidade, e serviços que chamam os motores em vez de reimplementá-los.

---

## D-037 — O alvo da Fase 7 é existência de interação documentada; os outros ficam fora, com número ao lado

**Data:** 09/09/2026

**Decisão.** Dos alvos possíveis, apenas dois são treinados: **A — existência de interação documentada** (alvo principal) e **C2 — tipo farmacocinético × farmacodinâmico** (secundário, declarado como rótulo derivado por regex de uma fonte só). Ficam fora, cada um com a medição que o desqualifica: relevância do alerta (0 anotações humanas), gravidade (38.459 de 94.770 pares graduados e um único graduador), prioridade (calculada pelas nossas próprias regras), mecanismo e efeito clínico (texto livre sem vocabulário fechado), necessidade de revisão (112.520 linhas todas `PENDENTE`, alvo sem variação) e reação adversa (VigiMed não carregado).

**Motivo.** A especificação exige auditoria do rótulo antes de escolher o alvo, e a auditoria muda a resposta. Dois casos merecem registro. **Relevância**: a tabela `anotacao_profissional` existe, tem chave estável e assinatura — e está **vazia**. Zero anotações não se extrapolam; a análise de poder indica algo entre 400 e 1.000 avaliações de dois farmacêuticos independentes. **Gravidade**: só o DDInter gradua, logo `vw_conflito_gravidade` devolve zero não por concordância entre bases, mas por existir um graduador só — a consistência do rótulo é estruturalmente imensurável neste acervo, e um alvo ordinal cuja consistência não pode ser medida não pode ser validado.

**Alternativas.** (a) Usar `prioridade` como proxy de relevância — rejeitado: mediria fidelidade a `rules/_prioridade.py`, não utilidade clínica, e a especificação proíbe. (b) Tratar `NAO_DETERMINADA` como classe de gravidade — rejeitado: "não sei" não é grau, e o modelo passaria a prever ausência de informação. (c) Simular anotações — rejeitado: inventar evidência clínica.

**Impacto.** Dois alvos treinados e seis recusados **com número**. A recusa documentada é resultado da fase, não falha dela. Confirma e reforça D-015 com medição própria.

---

## D-038 — Os atributos de grafo saem do modelo publicado, por vazamento medido

**Data:** 09/09/2026

**Decisão.** O bloco de atributos derivado do grafo de interações (grau, vizinhos comuns, Jaccard, Adamic-Adar, ligação preferencial) fica **fora** do modelo publicado. O espaço de atributos publicado tem 130 colunas, nenhuma começando por `g_`, e `tests/teste_ml.py` reprova se alguma voltar.

**Motivo.** Medido, não suposto. Com split por par (ambos os fármacos vistos no treino) os atributos de grafo levam a AUC de 0,86 para **0,944** — e é esse número que a literatura reporta. Com split por fármaco, aplicados a fármaco inédito, o mesmo modelo desaba para **AUC 0,3415**, isto é, **pior que o acaso**: para o fármaco novo o grau é zero, os vizinhos comuns são zero, e os coeficientes aprendidos sobre essas colunas passam a apontar na direção errada. A heurística de grafo pura (Adamic-Adar) dá AUC **0,5000 exata** no regime frio, porque não existe um único vizinho em comum a explorar. Grau e vizinhos comuns são contagem de arestas — ou seja, de rótulos positivos — disfarçada de atributo.

**Alternativas.** (a) Manter o grafo e usar o modelo só em fármaco conhecido — rejeitado: fármaco conhecido é justamente aquele cuja interação já está documentada, onde previsão não acrescenta nada. (b) Treinar uma GNN — rejeitado com a medição que o §14 da especificação exige antes de qualquer treino: **1.137 das 2.094 substâncias têm grau zero** e, entre as 957 conectadas, o grafo é denso (20,7% dos pares possíveis já são aresta) e tem componente única. Onde há estrutura, quase todos são vizinhos de quase todos; onde o projeto é cego, não há aresta para propagar.

**Impacto.** A AUC publicada cai de 0,944 para 0,7382, e essa queda é o preço de reportar o número que descreve o uso real. O bloco de grafo continua implementado em `_features.py` porque é a ablação que sustenta esta decisão.


*Números remedidos em 10/09/2026 — ver **D-048**. Os valores citados acima são os que se conheciam quando esta decisão foi tomada; os deslocamentos são da ordem de 0,001 de AUC e nenhuma conclusão mudou.*
---

## D-039 — A unidade do dataset é o par canônico, não a linha de interação

**Data:** 09/09/2026

**Decisão.** Uma linha de treino por **par canônico de substâncias** (`a_id < b_id`). As 112.520 linhas de `interacao_substancia` viram 94.770 observações.

**Motivo.** 17.750 pares (18,7%) são afirmados pelas duas bases e por isso têm duas linhas. Treinar por linha daria peso 2 a esses e peso 1 ao resto — o modelo aprenderia "este par aparece em duas compilações", que é propriedade do processo de compilação, não farmacologia. O número de fontes não é descartado: vira o rótulo auxiliar `n_fontes`, usado no teste de rótulo mais duro (positivo só quando as duas bases afirmam), nunca como atributo de entrada.

**Alternativas.** (a) Treinar por linha — rejeitado acima. (b) Treinar por achado — rejeitado: achado depende de paciente, e existência de interação é propriedade do par; misturar contexto de paciente num alvo geral é o que a especificação §12 proíbe.

**Impacto.** O `CHECK (substancia_a_id < substancia_b_id)` do esquema já garantia a canonicidade; a auditoria confirmou **zero** pares invertidos e **zero** duplicatas exatas. Os atributos são obrigatoriamente simétricos (contagem de lados, soma, mín/máx, ou-lógico), e o autoteste de `_features.py` verifica par por par que `construir(a,b) == construir(b,a)`.

---

## D-040 — O negativo é presumido, e o modelo estima documentação, não risco

**Data:** 09/09/2026

**Decisão.** O rótulo negativo é declarado como **"não afirmado por estas duas bases"**, e o que o modelo estima é a probabilidade de o par **estar documentado**, não de o par ser perigoso. Essa frase entra no texto que iria à tela, no campo `limitacoes` da tabela `modelo` e no relatório da fase.

**Motivo.** Nenhuma das duas fontes publica ausência de interação: elas listam o que afirmam. Ausência de linha significa uma de três coisas que o dado não distingue — foram estudadas e não interagem; nunca foram estudadas juntas; interagem e a base ainda não registrou. É aprendizado com positivos e não-rotulados. A explicabilidade confirmou a consequência: os três atributos mais importantes são `adm_lados_com_regra` e o número de apresentações no mercado — ou seja, **quão estudado e quão comercializado** é o fármaco. Isso prevê documentação muito bem e risco clínico não.

**Alternativas.** (a) Chamar os não afirmados de negativos sem qualificação — rejeitado: transformaria falta de cobertura em afirmação de segurança, o oposto da invariante "ausência de alerta nunca é ausência de risco". (b) Restringir o universo a pares de fármacos muito estudados — rejeitado: melhora a métrica e apaga justamente o ponto cego.

**Impacto.** Três mitigações medidas: o universo exclui as 1.137 substâncias de grau zero (onde a ausência é certamente falta de cobertura); existe o subconjunto **pareado por grau**, no qual popularidade deixa de separar as classes e a AUC do gradient boosting cai de 0,79 para **0,7221**; e a ablação `SEM_POPULARIDADE` mostra que a classe farmacológica sozinha sustenta AUC **0,7187** contra 0,7382 do modelo completo — a maior parte do sinal é farmacologia, mas não toda.


*Números remedidos em 10/09/2026 — ver **D-048**. Os valores citados acima são os que se conheciam quando esta decisão foi tomada; os deslocamentos são da ordem de 0,001 de AUC e nenhuma conclusão mudou.*
---

## D-041 — O modelo não é implantado como alerta; é implantado como fila de curadoria

**Data:** 09/09/2026

**Decisão.** Nenhuma previsão vira alerta ao farmacêutico nesta fase. Os dois modelos entram no banco com `status = EXPERIMENTAL` e `ativo = 0`, e `70_predizer.contrato_achado()` **levanta exceção** enquanto o status não for `HOMOLOGADO`. O uso liberado é outro: uma fila priorizada de pares sem documentação para verificação humana (`reports/fila_curadoria_m1.csv`).

**Motivo.** No regime realista — os dois fármacos inéditos — o modelo tem AUC 0,7382 e, no ponto de F1 máximo, **recall 0,53 e precisão 0,40**. Metade das interações documentadas passaria batido e seis de cada dez alertas seriam falsos. A especificação §19 é explícita: um modelo que só aumenta a quantidade de alertas não é melhoria. Mas a precisão **no topo** da lista é alta: entre os 0,5% de maior probabilidade, 82% eram pares realmente afirmados por fonte, contra 20,4% de linha de base. Acertar 4 em 5 nos casos de maior confiança serve para dizer a um farmacêutico o que investigar primeiro.

Há uma sutileza que decide a questão: o teste mede "o modelo recupera uma interação documentada que não lhe foi mostrada?". Em produção o modelo só seria usado em pares **sem** documentação — exatamente os que no teste contaram como falso positivo. Ali não existe verdade conhecida, e é onde a natureza presumida do negativo (D-040) cobra o preço.

**Alternativas.** (a) Exibir previsão com limiar alto — rejeitado nesta fase: sem um único farmacêutico tendo avaliado uma previsão deste modelo, exibir seria substituir validação clínica por validação computacional. (b) Não usar o modelo para nada — rejeitado: a fila de curadoria é útil e é o caminho para gerar o rótulo humano que falta.

**Impacto.** O contrato de interface fica pronto, testado e desligado. A fila de curadoria é também a saída da limitação central da fase: cada linha verificada por um farmacêutico é uma anotação humana, e é delas que depende o modelo de relevância (problema B).


*Números remedidos em 10/09/2026 — ver **D-048**. Os valores citados acima são os que se conheciam quando esta decisão foi tomada; os deslocamentos são da ordem de 0,001 de AUC e nenhuma conclusão mudou.*
---

## D-042 — Dois modelos registrados, nenhum ativo; homologar é ato humano

**Data:** 09/09/2026

**Decisão.** São registrados **dois** modelos para o mesmo problema: `1.0-boosting` (melhor métrica) e `1.0-logistica` (referência interpretável). Ambos experimentais, ambos inativos. O esquema ganhou um índice único parcial de modelo ativo por problema e um `CHECK` que só permite ativar o que estiver homologado.

**Motivo.** A especificação §23 exige que o sistema nunca substitua um modelo antigo em silêncio. Isso não se sustenta por processo: sustenta-se por índice único — publicar outro exige desativar o anterior no mesmo passo, explicitamente. Guardar as duas famílias deixa a troca futura ser uma decisão com número: a diferença entre elas é de 0,0235 de AUC no regime frio, com intervalo de confiança de bootstrap pareado [0,0160 ; 0,0309] — real, mas pequena, e paga com perda de interpretabilidade e com um artefato que depende da versão do scikit-learn.

**Alternativas.** Registrar só o vencedor — rejeitado: obrigaria a retreinar no escuro para reconsiderar.

**Impacto.** `pipeline/90_validacao.py` ganhou nove verificações novas e `tests/teste_schema.py` duas seções (invariantes 2d e 2e). O banco recusa ativar um modelo experimental, recusa dois ativos para o mesmo problema e recusa previsão revisada sem quem revisou.


*Números remedidos em 10/09/2026 — ver **D-048**. Os valores citados acima são os que se conheciam quando esta decisão foi tomada; os deslocamentos são da ordem de 0,001 de AUC e nenhuma conclusão mudou.*
---

## D-043 — Artefato em JSON quando a família permite; pickle é declarado como amarra

**Data:** 09/09/2026

**Decisão.** O modelo é gravado em JSON quando a família permite (regressão logística: média, escala, coeficientes e intercepto; tabela classe × classe: a tabela inteira). Árvores e boosting vão em pickle, com a versão do scikit-learn gravada ao lado e aviso explícito no arquivo. O **calibrador** é sempre uma tabela de pontos em JSON, nunca um objeto serializado.

**Motivo.** O sistema vai virar `ConciliadorMedicamentos.exe` (Fase 10) e um pickle amarra o arquivo a uma versão de biblioteca — daqui a dois anos o mesmo `.pkl` pode não abrir. A verificação independente prova que a escolha vale: o eixo 6 da V2 **refaz a conta da logística à mão**, lendo o JSON e multiplicando matrizes, sem importar scikit-learn, e chega à mesma probabilidade.

**Alternativas.** ONNX — rejeitado nesta fase: acrescenta dependência de conversão e não resolve o problema para o modelo de árvore com esforço proporcional ao benefício, dado que nenhum modelo está ativo.

**Impacto.** Fragilidade de artefato entra na tabela de comparação como **custo de manutenção**, não como detalhe de implementação: um modelo que só abre numa versão específica de biblioteca é mais difícil de validar por terceiro.

---

## D-044 — Nenhuma dependência nova de ML

**Data:** 09/09/2026

**Decisão.** Não foram instalados `xgboost`, `lightgbm`, `shap` nem `torch`. Gradient boosting usa `HistGradientBoostingClassifier` do scikit-learn — a mesma técnica de boosting por histograma do LightGBM. A explicação local usa **contribuição aproximada por ocultação** (recalcula a previsão com um atributo por vez no valor de referência) e o relatório a chama exatamente assim: aproximação de SHAP, **não** SHAP.

**Motivo.** Cada dependência pesa no empacotamento, e nenhuma delas acrescentaria capacidade que altere a conclusão da fase. Para a família linear a contribuição por atributo é **exata** (coeficiente × valor padronizado), sem biblioteca nenhuma.

**Alternativas.** Instalar `shap` para o modelo de árvore — reconsiderável quando algum modelo for homologado; hoje seria dependência para explicar previsão que não é exibida.

**Impacto.** O texto do projeto nunca chama de SHAP o que não é SHAP. A diferença importa: SHAP exato média todas as ordens de entrada dos atributos; a ocultação uma-a-uma não.

---

## D-045 — Carga incremental significa idempotência, e origem alterada é recusada

**Data:** 09/09/2026 · Defeito encontrado ao rodar a bateria completa da Fase 7.

**Decisão.** "Carga incremental" passa a significar uma coisa precisa e testável: **reexecutar o pipeline sobre a mesma origem não muda uma linha**. E se um arquivo do acervo mudar, a carga incremental **para** e exige `--recriar` (`_comum.OrigemAlterada`), em vez de tentar reconciliar.

**Motivo.** O modo incremental estava documentado e nunca funcionou: `20_substancias.py` fazia um `INSERT INTO substancia` puro e abortava na primeira substância já existente. Como ninguém conseguia chegar à segunda execução, três defeitos que só aparecem nela ficaram invisíveis:

| Defeito | Efeito na 2ª execução |
|---|---|
| `INSERT INTO substancia` / `interacao_substancia` sem `OR IGNORE` | abortava a carga |
| `regra_separacao` sem chave de unicidade | **duplicava as 59 regras** |
| `auditoria_conflito` sem chave de unicidade | duplicava as 4 linhas |
| `abrir_carga` inserindo sempre | 11 linhas de `carga` por execução |
| `fechar_carga` sobrescrevendo | apagava os números do lote original |

E um quinto, que já estava **no banco** antes de qualquer reexecução: sem chave de unicidade, `regra_separacao` acumulou **12 cópias exatas** já na primeira carga. Cinco entradas do DrugBank — acetato, sulfato, gluconato, cloreto e brometo de zinco — caem na mesma substância brasileira pela chave candidata, e cada uma gravava as mesmas regras. `brometo de zinco` tinha **15 linhas para 3 regras**. As tabelas irmãs (`regra_administracao`, `interacao_item`, `interacao_habito`) tinham `UNIQUE` e por isso nunca inflaram. O número publicado de regras de separação passa de **71 para 59**, e o de regras com intervalo declarado, de **61 para 49**.

**Por que recusar origem alterada, em vez de reconciliar.** Reconciliar exigiria tratar remoção de linha, renomeação de substância, renormalização de chave e sobrescrita de campo curado — cada um com uma decisão clínica embutida. Feito pela metade, é exatamente como dado errado entra em silêncio, que é o que este projeto inteiro existe para evitar. O `hash_arquivo` já estava na tabela `carga` para dar esse aviso; agora ele dá. Reconciliação de fonte alterada é trabalho próprio, com curadoria, e não um efeito colateral de rodar o pipeline de novo.

**Alternativas.** (a) `INSERT OR IGNORE` em tudo e seguir em frente — rejeitado: com origem alterada, mantém silenciosamente o valor velho (`n_produtos_ativos` congelado, por exemplo), que é resposta errada sem aviso. (b) `UPSERT` — rejeitado pelo mesmo motivo, com o agravante de sobrescrever curadoria. (c) Corrigir só o texto da documentação e deixar o modo quebrado — rejeitado: `--recriar` apaga `modelo` e `predicao`, obrigando a reconstruir 20 minutos de camada de ML a cada revalidação do banco.

**Impacto.**

- `_comum.py` ganhou `OrigemAlterada`, `inserir_unico()` e a semântica de lote em `abrir_carga`/`fechar_carga`. **`inserir_unico` resolve um erro silencioso que estava espalhado:** `cur.lastrowid` depois de um `INSERT OR IGNORE` que ignorou devolve o id da inserção anterior — vários ETLs se protegiam com `if cur.rowcount:`, o que evita o id errado mas pula tudo o que vem depois.
- Duas chaves de unicidade novas no esquema, com o conteúdo inteiro da afirmação na chave — assim contradição real dentro da fonte continua produzindo duas linhas (D-023), e só cópia idêntica é colapsada.
- `tests/teste_idempotencia.py`: tira uma fotografia das 44 tabelas, roda os 11 ETLs e compara. **Resultado: 44 tabelas idênticas.**
- `tests/teste_regressao.py` ganhou 7 travas, incluindo uma que **lê o código-fonte** e reprova `INSERT INTO` cru em qualquer das 13 tabelas de afirmação.
- A impressão digital dos dados usada pela Fase 7 (`59d4915db0a349e3`) **não mudou** por causa desta correção: `regra_separacao` não entra nela nem alimenta atributo de ML. (Ela mudou no dia seguinte, por outro motivo — ver **D-048**.)

---

## D-046 — A view é a única porta da previsão, e ela é fail-closed

**Data:** 10/09/2026

**Decisão.** Uma previsão só chega ao farmacêutico através de `vw_predicao_liberada`, que exige **quatro** condições simultâneas: modelo `ativo=1`, modelo `status='HOMOLOGADO'`, `limiar_alerta` declarado e atingido pela probabilidade **calibrada**, e **o par não ter interação documentada**. Previsão recusada por um farmacêutico não volta. Nenhuma dessas travas está no código de aplicação.

**Motivo.** A garantia que importa — *previsão não substitui evidência* — não pode depender de disciplina de quem escreve o motor ou a tela. Posta na view, ela vale para o motor, para a aplicação, para o relatório, para qualquer consulta futura e para qualquer pessoa que abra o banco com um cliente SQL. E a quarta condição resolve estruturalmente o conflito regra × modelo: onde há documento, a previsão nem aparece, então não há o que reconciliar, contradizer ou duplicar.

O `limiar_alerta` é **fail-closed** de propósito: `NULL` é o padrão e significa "este modelo não emite alerta nenhum". Um modelo homologado por engano, sem limiar declarado, continua produzindo zero achados. O limiar é propriedade da *versão* do modelo — escolhido na validação, gravado ao lado das métricas que o justificam.

**Alternativas.** (a) Filtrar no motor — rejeitado: uma consulta nova em outro lugar reabriria o buraco, e a Fase 6 já teve de provar por leitura de código-fonte que a tela não faz SQL clínico (D-036). (b) Deixar a previsão aparecer junto com o documento e sinalizar visualmente — rejeitado: dois alertas para o mesmo par é duplicação, e a sinalização visual é a primeira coisa que se perde num relatório impresso em preto e branco.

**Impacto.** Com nenhum modelo ativo a view devolve zero linhas, o módulo 13 do motor não produz nada e o sistema se comporta exatamente como antes de existir ML — verificado por regressão. `pipeline/90_validacao.py` ganhou 8 checagens que consultam a própria view, de modo que uma alteração futura que afrouxe qualquer trava faz a validação do banco sair com código 1.

---

## D-047 — Previsão não tem evidência, e o teto dela é INFORMATIVO

**Data:** 10/09/2026

**Decisão.** Um achado `PREVISTO` **não gera nenhuma linha em `achado_evidencia`**, e sua prioridade é `INFORMATIVO` por definição — não por cálculo. A rastreabilidade vai por `origem_afirmacao='predicao.<id>'`, e a tela diz, com todas as letras, *"Não há evidência documental para este par"*.

**Motivo.** `achado_evidencia` é "uma linha por (achado, fonte que o sustenta)". Um modelo não é fonte de evidência — e escrevê-lo ali, ainda que com um rótulo diferente, é precisamente a confusão que esta fase existe para impedir: bastaria alguém contar linhas de evidência para uma previsão passar a "ter duas evidências". A ausência é informação, e informação que o farmacêutico precisa ver.

Sobre o teto: uma previsão não tem gravidade de fonte para sustentar prioridade nenhuma. O modelo estima a probabilidade de o par **estar documentado** em alguma base — não o tamanho do dano (Fase 7, D-040). Deixá-la competir por ordem de exibição com interação documentada seria misturar previsão com fato pelo eixo mais consequente, que é o que o farmacêutico lê primeiro numa fila de balcão.

**Alternativas.** (a) Registrar o modelo como evidência com `tipo_fonte='MODELO_PREDITIVO'` — rejeitado acima. (b) Deixar a prioridade subir com a probabilidade — rejeitado: probabilidade alta de estar documentado não é gravidade alta, e a Fase 7 mostrou que metade do sinal do modelo é propensão a documentação, não farmacologia.

**Impacto.** Previsto sai da escala de prioridade em todos os lugares onde ela aparece: no painel de indicadores (contador próprio, "Previstos (sem documento)"), nos blocos da tela (bloco separado, tracejado, depois de todas as prioridades), no relatório impresso (seção própria, depois dos achados) e no texto puro. `rules/_prioridade.py` ganhou a entrada `(FARMACO_FARMACO, PREVISTA)` com a justificativa escrita ao lado, como todas as outras.

---

## D-048 — O pipeline tem de convergir numa passada, e a impressão digital tem de ver conteúdo

**Data:** 10/09/2026 · Defeito encontrado pela V1 da Fase 8.

**Decisão.** Duas coisas, que são a mesma coisa vista de dois lados.

Primeira: o pipeline passa a **convergir numa única passada**. O passo novo `pipeline/68_vincular_atc_pendente.py` refaz o vínculo substância → código ATC depois que os sinônimos INN existem.

Segunda: `ml/_comum.versao_dados()` passa a incluir o **conteúdo** das colunas que viram atributo de ML — não apenas a contagem de linhas das tabelas.

**Motivo.** `40_atc.py` casa a substância com o código ATC de 5º nível pelo esqueleto fonético do nome em inglês, usando um índice montado a partir de `substancia.chave_normalizada` **e de `substancia_sinonimo`**. Os sinônimos **INN** — os nomes em inglês que casaram 1:1 com uma substância brasileira — são criados depois, por `60_interacoes_substancia.py`. Resultado: a primeira passada perdia **6 vínculos** que a segunda encontrava. Uma reconstrução do zero dava **1.153** substâncias com ATC; a mesma reconstrução seguida de uma carga incremental dava **1.159**.

Isso é pior do que parece por dois motivos. Um: o resultado do pipeline dependia de **quantas vezes ele tinha rodado**, o que contradiz D-045, que acabara de estabelecer que reexecutar não muda nada — e não contradizia pela letra (as duas execuções seguintes eram idênticas), mas pelo espírito (o ponto fixo era alcançado na segunda passada, não na primeira). Dois: a impressão digital dos dados **não viu**. Ela olhava contagem de linhas, e `substancia` continuava com 2.094 linhas — só que 6 delas tinham ganhado um `atc_codigo`. Um experimento de ML deixou de ser reproduzível em silêncio, que é exatamente o que a impressão digital existe para impedir.

**Como apareceu.** Não por teste de carga: pela **V1 da Fase 8**, quando a AUC gravada em `modelo.metricas_json` deixou de bater com a recalculada (0,787872 contra 0,788743). Investigar essa diferença de 0,0009 levou ao vínculo ATC. Vale registrar o encadeamento, porque ele justifica a disciplina: um teste de integração de interface encontrou um defeito de ETL de três fases antes.

**Alternativas.** (a) Mover `40_atc.py` para depois de `60` — rejeitado: o nível 5 do ATC pega o nome em português da DCB e a tradução de classes depende de 40 ter rodado antes; reordenar resolveria um vínculo e quebraria outro. (b) Deixar como estava, já que a diferença é de 6 substâncias — rejeitado: o problema não é o tamanho, é o pipeline não ter ponto fixo na primeira passada, e a impressão digital não conseguir vê-lo.

**Impacto.**

- Cobertura de ATC: **1.153 → 1.159** (55,1% → 55,3%; 94,4% → 95,0% das 957 conectadas).
- **Todos os números da Fase 7 foram remedidos.** Os deslocamentos são da ordem de 0,001 de AUC e **nenhuma conclusão mudou**: o modelo escolhido continua `GRADIENT_BOOSTING / SEM_GRAFO`, floresta e boosting continuam empatados dentro do intervalo de confiança, o grafo continua produzindo AUC pior que o acaso em fármaco inédito, e a decisão de não implantar como alerta (D-041) continua de pé.

  | | antes | agora |
  |---|---:|---:|
  | AUC FRIO_FRIO (modelo escolhido) | 0,7382 | **0,7392** |
  | AUC teste | 0,7879 | 0,7887 |
  | ECE após calibração | 0,0137 | 0,0118 |
  | precisão no topo 1% | 0,772 | 0,802 |
  | impressão digital | `59d4915db0a349e3` | `9e9c85ee3ffea5e0` |

- `tests/teste_regressao.py` ganhou 3 travas de convergência; `ml/91_v1_pipeline.py` passou a exigir que **o artefato publicado** reproduza a métrica gravada, e não apenas um treino novo — foi essa distinção que expôs o defeito.
- `ml/60_registrar_modelo.py` passou a apagar as previsões do artefato anterior antes de re-registrar a mesma versão. Sem isso o `DELETE` falhava por chave estrangeira e o registro ficava dessincronizado do `.pkl` — um segundo defeito, encontrado no mesmo puxão.

**Nota sobre as decisões anteriores.** D-038, D-040, D-041 e D-042 citam os números medidos **antes** desta correção. Ficam como estão: registram o que se sabia quando a decisão foi tomada. Os valores atuais estão em `docs/ML_FASE7.md` e em `ml/saida/*.json`.

---

## D-049 — Mensagem de estado é presa ao atendimento, não à sessão

**Data:** 10/09/2026 · Defeito encontrado pela V1 da Fase 9, eixo 1.

**Decisão.** Toda mensagem de confirmação ou de erro passa a carregar o código
do atendimento que a gerou. `app/web.avisar(texto, categoria, codigo)` grava o
código na categoria; `base.html` mostra o que é da tela e **devolve o resto
para a fila**, em vez de descartar.

**Motivo.** A fila de mensagens do Flask é da **sessão do navegador**, não do
atendimento. Uma mensagem só é consumida quando alguma página renderiza, e até
lá ela espera. Com dois atendimentos abertos — duas abas, ou o farmacêutico
voltando ao paciente anterior —, a confirmação de um saía na tela do outro:

> Posologia de **Gliclazida 30 mg** salva.

…no alto da tela de uma paciente que toma varfarina e ibuprofeno. Nenhum dado
clínico vazou: o achado, o resumo, o relatório e o banco continuaram corretos, e
a V1 confirmou isso em oito conferências separadas. O que vazou foi **uma frase
sobre outro paciente**. Num sistema cuja finalidade é não confundir paciente,
isso é defeito, não cosmética.

**Alternativas.** (a) Não fazer nada, porque num navegador o `POST` é seguido do
`redirect` e a mensagem é consumida logo — rejeitado: "logo" depende de qual aba
carrega primeiro, e a hipótese de uma aba por atendimento é justamente o modo de
trabalho de um balcão com fila. (b) Filtrar e descartar o que não é da tela —
rejeitado na primeira tentativa, e o próprio teste pegou: a mensagem
*"Atendimento X não encontrado"* redireciona para a tela inicial, que não
pertence a atendimento nenhum, e some. Por isso a regra final esconde **apenas**
quando a tela atual pertence a **outro** atendimento; em tela sem atendimento,
tudo aparece.

**Impacto.** 18 chamadas de `flash` convertidas; `teste_regressao.py` reprova
`flash(` cru em qualquer rota.

---

## D-050 — Probabilidade calibrada saturada não é exibida como "100%"

**Data:** 10/09/2026 · Defeito encontrado pela **inspeção visual** da Fase 9.

**Decisão.** `rules/_prioridade.percentual_previsao()` é o único lugar que
converte a probabilidade de uma previsão em texto. Acima de 0,995 sai
**"acima de 99%"**; abaixo de 0,005, **"abaixo de 1%"**; no meio, o percentual
arredondado. O valor exato, com quatro casas, continua no painel de
rastreabilidade, agora com a explicação do que a saturação significa.

**Motivo.** A calibração isotônica satura por construção: a faixa mais alta da
validação recebe exatamente 1,0 quando **todos** os pares daquela faixa estavam
documentados. Isso é uma frequência observada num conjunto finito — não é
certeza. A tela exibia:

> o modelo estima **100%** de probabilidade de que o par esteja documentado

três parágrafos abaixo de *"Não há evidência documental para este par"*. É a
contradição mais forte que este sistema poderia produzir: a linha existe
justamente para dizer que **nenhuma fonte afirma nada**, e o número ao lado
prometia certeza absoluta. Um farmacêutico com fila no balcão lê o número.

Nenhum teste tinha pegado, e a razão importa: todos conferiam **estrutura** —
que o campo existe, que o bloco está separado, que a evidência é nenhuma.
Nenhum lia a frase. Este foi encontrado abrindo a tela e lendo.

**Alternativas.** (a) Arredondar para 0,99 — rejeitado: falsifica o número.
(b) Deixar como estava e explicar num rodapé — rejeitado: o rodapé não compete
com um "100%" em destaque.

**Impacto.** Uma definição, quatro consumidores: a explicação escrita pelo motor,
`achado.html`, `resultados.html`, `relatorio.html` e `relatorio.py`. Nenhum deles
formata percentual por conta própria, e `teste_regressao.py` reprova quem voltar
a fazê-lo. No mesmo passo, `rotulos.SUBTIPO` passou a traduzir o subtipo do
achado, que chegava à tela como `interacao prevista` — código interno cru, sem
acento, contra a regra de que todo vocabulário do banco é traduzido em
`rotulos.py`.

---

## D-051 — Um arquivo de banco, e a separação acontece na atualização

**Data:** 10/09/2026 · Fase 10.

**Decisão.** O programa usa **um** arquivo SQLite, `conciliador.db`, com
conhecimento e atendimento juntos, na pasta de dados do usuário. A separação
entre os dois — que a Fase 9 apontou como pendência — acontece no momento da
**atualização**, feita por `app/atualizacao.py`, e não no disco.

O que é distribuído é `conhecimento/conhecimento.db`: o mesmo banco com as 16
tabelas de atendimento **vazias**. Na primeira execução ele é copiado para a
pasta do usuário; numa atualização, ele é o ponto de partida e os atendimentos
do usuário são trazidos para dentro dele.

**Motivo — e ele foi medido, não suposto.** A alternativa óbvia era
`conhecimento.db` + `atendimentos.db`, com `ATTACH`. Contando as chaves
estrangeiras do esquema:

| | |
|---|---:|
| chaves estrangeiras que cruzam a fronteira | **8** |
| direção | todas ATENDIMENTO → CONHECIMENTO |
| views que cruzam a fronteira | **0** |

As oito: `atendimento_medicamento.substancia_id`,
`atendimento_medicamento.apresentacao_id`, `paciente_alergia.substancia_id`,
`paciente_condicao.doenca_id`, `atendimento_item.item_id`,
`conciliacao_par.substancia_id`, `achado.substancia_a_id`,
`achado.substancia_b_id`.

**O SQLite não aplica chave estrangeira entre bancos diferentes.** Separar os
arquivos desligaria as oito — e desligaria exatamente a proteção de que a
atualização mais precisa: descobrir que um atendimento antigo aponta para uma
substância que a versão nova do conhecimento não tem mais. A separação em dois
arquivos *criaria* o risco que ela deveria evitar.

Com um arquivo só, `PRAGMA foreign_key_check` responde essa pergunta, e o
resultado é uma **recusa declarada**: a atualização não acontece, o banco em
uso não é tocado, e o usuário lê o motivo. Testado — `fase10_empacotamento.py`
caso 7.d apaga de propósito uma substância em uso e confere que a atualização é
recusada.

**O custo, declarado.** Atualizar deixa de ser trocar um arquivo e passa a ser
uma migração com cinco passos (conferir, backup, montar em temporário,
verificar, trocar). É mais código do que um `copy`. É o preço de manter as oito
chaves ligadas, e ele foi pago com os olhos abertos.

**Alternativas.** (a) Dois arquivos com `ATTACH` — rejeitado pelo acima.
(b) Um arquivo, atualizado por substituição total — rejeitado: apagaria os
atendimentos, que é o defeito que a Fase 9 mandou corrigir. (c) Chaves
estrangeiras removidas do esquema para viabilizar a separação — rejeitado sem
hesitação: o projeto inteiro se apoia em invariantes estruturais, e trocar uma
garantia do banco por uma convenção de código é andar para trás.

---

## D-052 — O banco carrega a própria identidade

**Data:** 10/09/2026 · Fase 10.

**Decisão.** Tabela nova, `propriedade`, com quatro chaves:
`conhecimento.versao`, `conhecimento.digital`, `conhecimento.gerado_em` e
`esquema.versao`. Preenchida pelo passo `pipeline/80_identidade.py`, ao fim de
toda carga.

**Motivo.** Um arquivo `.db` distribuído, sozinho numa máquina qualquer, tinha
de ser capaz de responder: **de qual versão do conhecimento eu sou?** Sem isso
um alerta já mostrado a um farmacêutico não pode mais ser atribuído à versão do
conhecimento que o produziu — e a rastreabilidade, que o projeto defende desde
a Fase 1, terminaria na porta do empacotamento.

Em tabela, e não em arquivo `.json` ao lado, para não se separar do dado que
descreve. Um `conhecimento.json` acompanha o pacote — mas é manifesto de
distribuição, com sha256 do arquivo; a identidade do *conteúdo* viaja dentro.

**A impressão digital é a MESMA do ML**, calculada por
`ml/_comum.versao_dados`. Reimplementar produziria dois números que divergiriam
no primeiro detalhe, e a rastreabilidade do modelo depende de eles serem o
mesmo número. O passo 80 importa `ml/_comum.py` por caminho, sob outro nome —
os dois arquivos se chamam `_comum.py`, e um `import` simples devolveria o do
pipeline.

**Impacto.** 44 → **45 tabelas**. É alteração deliberada de esquema, e as
conferências que afirmavam 44 foram atualizadas com o motivo ao lado. A versão
do esquema (`1.0`) é o que a atualização compara para aceitar ou recusar um
conhecimento novo.
