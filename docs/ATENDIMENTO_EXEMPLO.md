# Atendimento de exemplo — saída real do sistema

Gerado por `tests/teste_ponta_a_ponta.py`, que executa um atendimento
completo **pela aplicação**, por requisições HTTP reais. A
farmacologia vem do banco; a paciente é sintética.

O caso: idosa em uso de anticoagulante que se automedicou com
anti-inflamatório, e que relata dose diferente da prescrita para o
anti-hipertensivo. Um dos itens não é reconhecido pelo cadastro, de
propósito — para mostrar como o sistema declara o que não avaliou.

```
========================================================================
CONCILIAÇÃO MEDICAMENTOSA — atendimento 20260910-001
========================================================================
Paciente: Dona Marlene (caso sintético)  ·  76 anos
Sexo: Feminino
Farmacêutico: Farm. Ana Souza  ·  CRF-AM 12345
Iniciado em: 2026-09-10 17:43:44   ·   Relatório gerado em: 10/09/2026 às 13:43
Motor: conciliacao-1.0

RESUMO
  Medicamentos analisados ......... 6
  Achados ......................... 16
    críticos ...................... 0
    altos ......................... 1
    moderados ..................... 5
    baixos ........................ 3
    informativos .................. 7
  Divergências de conciliação ..... 5
  Informações insuficientes ....... 2
  Itens não avaliados ............. 8
  Revisão profissional necessária . SIM

FARMACOTERAPIA
  · Varfarina 5 mg (Prescrito (receita apresentada))
      5 mg · 1x/dia · 20:00
      princípio ativo: varfarina
  · Varfarina 5 mg (Relatado pelo paciente)
      5 mg · 1x/dia · 20:00
      princípio ativo: varfarina
  · Losartana 50 mg (Prescrito (receita apresentada))
      50 mg · 2x/dia · 08:00, 20:00
      princípio ativo: losartana
  · Losartana 50 mg (Relatado pelo paciente)
      100 mg · 1x/dia · 08:00
      princípio ativo: losartana
  · Ibuprofeno 600 mg (Relatado pelo paciente)
      600 mg · 3x/dia · 08:00, 14:00, 22:00
      princípio ativo: ibuprofeno
  · um chá que a vizinha indicou (Relatado pelo paciente)   [NÃO RECONHECIDO]
      posologia não informada

CONDIÇÕES CLÍNICAS
  · hipertensão arterial

ALERGIAS
  · dipirona  (urticária e inchaço nos lábios)

ACHADOS

  --- ALTO (1) ---
  · Interação entre Ibuprofeno 600 mg e Varfarina 5 mg
      módulo: Interação entre medicamentos
      gravidade da fonte: Maior   |   confiança do sistema: Média
      situação da informação: Documentado
      efeito esperado: Varfarina pode aumentar os efeitos anticoagulantes de ibuprofeno.
      por que apareceu: Ibuprofeno 600 mg e Varfarina 5 mg estão na farmacoterapia atual do paciente. 2 fonte(s) do acervo registram interação entre os dois: DDInter / db_drug_interactions.
      fonte: DDInter / db_drug_interactions

  --- MODERADO (5) ---
  · Divergência de conciliação: ibuprofeno (so no relato)
      módulo: Divergência de conciliação
      gravidade da fonte: Não se aplica   |   confiança do sistema: Média
      situação da informação: Documentado
      por que apareceu: O paciente relata usar e não consta da prescrição apresentada (origem declarada: AUTOMEDICACAO). O sistema classifica a situação; a intencionalidade permanece NÃO DETERMINADA até que um profissional identificado a registre.
      fonte: Listas do atendimento
  · Divergência de conciliação: losartana (dose diferente)
      módulo: Divergência de conciliação
      gravidade da fonte: Não se aplica   |   confiança do sistema: Média
      situação da informação: Documentado
      por que apareceu: A dose prescrita (50 mg) difere da relatada (100 mg). Diferença não é erro: pode ser ajuste posterior. A intencionalidade só pode ser decidida por um profissional. O sistema classifica a situação; a intencionalidade permanece NÃO DETERMINADA até que um profissional identificado a registre.
      fonte: Listas do atendimento
  · Divergência de conciliação: losartana (frequencia diferente)
      módulo: Divergência de conciliação
      gravidade da fonte: Não se aplica   |   confiança do sistema: Média
      situação da informação: Documentado
      por que apareceu: A frequência prescrita (2x/dia) difere da relatada (1x/dia). Diferença não é erro: pode ser ajuste posterior. A intencionalidade só pode ser decidida por um profissional. O sistema classifica a situação; a intencionalidade permanece NÃO DETERMINADA até que um profissional identificado a registre.
      fonte: Listas do atendimento
  · Interação entre Ibuprofeno 600 mg e Losartana 50 mg
      módulo: Interação entre medicamentos
      gravidade da fonte: Moderada   |   confiança do sistema: Média
      situação da informação: Documentado
      efeito esperado: O metabolismo de losartana pode ser reduzido quando combinado com ibuprofeno.
      por que apareceu: Ibuprofeno 600 mg e Losartana 50 mg estão na farmacoterapia atual do paciente. 2 fonte(s) do acervo registram interação entre os dois: DDInter / db_drug_interactions.
      fonte: DDInter / db_drug_interactions
  · Varfarina 5 mg × ervas com ação anticoagulante
      módulo: Medicamento e planta ou chá
      gravidade da fonte: Maior   |   confiança do sistema: Baixa
      situação da informação: Extraído automaticamente — sem revisão
      efeito esperado: Ervas com ação anticoagulante ou antiplaquetária somam-se ao medicamento e aumentam o risco de sangramento.
      por que apareceu: Varfarina 5 mg interage com ervas com ação anticoagulante segundo DrugBank - interacoes com alimento. O paciente declarou usar este item, então a interação é atual.
      fonte: DrugBank - interacoes com alimento

  --- BAIXO (3) ---
  · Divergência de conciliação: losartana (horario diferente)
      módulo: Divergência de conciliação
      gravidade da fonte: Não se aplica   |   confiança do sistema: Média
      situação da informação: Documentado
      por que apareceu: A horário prescrita (08:00, 20:00) difere da relatada (08:00). Diferença não é erro: pode ser ajuste posterior. A intencionalidade só pode ser decidida por um profissional. O sistema classifica a situação; a intencionalidade permanece NÃO DETERMINADA até que um profissional identificado a registre.
      fonte: Listas do atendimento
  · Interação entre Losartana 50 mg e Varfarina 5 mg
      módulo: Interação entre medicamentos
      gravidade da fonte: Não graduada pela fonte   |   confiança do sistema: Média
      situação da informação: Não determinado pela fonte
      efeito esperado: O metabolismo de losartana pode ser reduzido quando combinado com varfarina.
      por que apareceu: Losartana 50 mg e Varfarina 5 mg estão na farmacoterapia atual do paciente. 2 fonte(s) do acervo registram interação entre os dois: DDInter / db_drug_interactions. NENHUMA fonte graduou a gravidade deste par. O sistema não atribui gravidade por conta própria.
      fonte: DDInter / db_drug_interactions
  · Ibuprofeno 600 mg × consumo de álcool
      módulo: Medicamento e hábito
      gravidade da fonte: Moderada   |   confiança do sistema: Baixa
      situação da informação: Extraído automaticamente — sem revisão
      efeito esperado: O álcool soma-se ao efeito do medicamento e aumenta o risco de sedação, lesão gástrica ou hepática, conforme o fármaco.
      por que apareceu: O paciente declarou consumo de álcool como atual e usa Ibuprofeno 600 mg. DrugBank - interacoes com alimento registra interação entre os dois.
      fonte: DrugBank - interacoes com alimento

  --- INFORMATIVO (7) ---
  · Divergência de conciliação: um chá que a vizinha indicou (sem correspondencia)
      módulo: Divergência de conciliação
      gravidade da fonte: Não se aplica   |   confiança do sistema: Média
      situação da informação: Não determinado pela fonte
      por que apareceu: O item não pôde ser ligado a nenhuma substância do cadastro (NAO_RECONHECIDO), então não pôde ser conciliado com segurança. O sistema classifica a situação; a intencionalidade permanece NÃO DETERMINADA até que um profissional identificado a registre.
      fonte: Listas do atendimento
  · Alimento exigido sem refeicao proxima — Ibuprofeno 600 mg
      módulo: Horário de administração
      gravidade da fonte: Não graduada pela fonte   |   confiança do sistema: Baixa
      situação da informação: Extraído automaticamente — sem revisão
      por que apareceu: Ibuprofeno 600 mg deve ser tomado junto do alimento, mas a refeição mais próxima (almoço, 12:00) está a 120 min. (observado 2 h) Este achado agrupa 1 detecção(ões) do mesmo problema por caminhos diferentes (MOTOR_DE_HORARIOS_DA_FASE_4); todas as evidências foram preservadas.
      fonte: DrugBank - interacoes com alimento
  · Varfarina 5 mg × folhosos verdes (vitamina K)
      módulo: Medicamento e alimento
      gravidade da fonte: Maior   |   confiança do sistema: Baixa
      situação da informação: Extraído automaticamente — sem revisão
      efeito esperado: Alimentos ricos em vitamina K reduzem o efeito do anticoagulante.
      por que apareceu: Varfarina 5 mg interage com folhosos verdes (vitamina K) segundo DrugBank - interacoes com alimento. O paciente NÃO declarou usar este item: isto é orientação preventiva a repassar, não alerta sobre uso atual.
      fonte: DrugBank - interacoes com alimento
  · Varfarina 5 mg × toranja
      módulo: Medicamento e alimento
      gravidade da fonte: Moderada   |   confiança do sistema: Baixa
      situação da informação: Extraído automaticamente — sem revisão
      efeito esperado: A toranja inibe a CYP3A4 intestinal e aumenta a exposição ao medicamento.
      por que apareceu: Varfarina 5 mg interage com toranja segundo DrugBank - interacoes com alimento. O paciente NÃO declarou usar este item: isto é orientação preventiva a repassar, não alerta sobre uso atual.
      fonte: DrugBank - interacoes com alimento
  · Varfarina 5 mg × erva-de-são-joão
      módulo: Medicamento e planta ou chá
      gravidade da fonte: Maior   |   confiança do sistema: Baixa
      situação da informação: Extraído automaticamente — sem revisão
      efeito esperado: A erva-de-são-joão induz a CYP3A4 e reduz o efeito do medicamento.
      por que apareceu: Varfarina 5 mg interage com erva-de-são-joão segundo DrugBank - interacoes com alimento. O paciente NÃO declarou usar este item: isto é orientação preventiva a repassar, não alerta sobre uso atual.
      fonte: DrugBank - interacoes com alimento
  · Como tomar: Ibuprofeno 600 mg
      módulo: Como tomar
      gravidade da fonte: Não se aplica   |   confiança do sistema: Baixa
      situação da informação: Extraído automaticamente — sem revisão
      sugestão da fonte: Tomar junto com alimento.
      por que apareceu: A fonte DrugBank - interacoes com alimento estabelece uma regra de administração (COM_ALIMENTO) para Ibuprofeno 600 mg. É orientação a repassar ao paciente, não problema detectado.
      fonte: DrugBank - interacoes com alimento
  · Como tomar: Losartana 50 mg
      módulo: Como tomar
      gravidade da fonte: Não se aplica   |   confiança do sistema: Baixa
      situação da informação: Extraído automaticamente — sem revisão
      sugestão da fonte: Pode ser tomado com ou sem alimento.
      por que apareceu: A fonte DrugBank - interacoes com alimento estabelece uma regra de administração (INDIFERENTE_ALIMENTO) para Losartana 50 mg. É orientação a repassar ao paciente, não problema detectado.
      fonte: DrugBank - interacoes com alimento

DIVERGÊNCIAS DE CONCILIAÇÃO
  · um chá que a vizinha indicou — Sem correspondência no cadastro
      intencionalidade: Não determinada
  · ibuprofeno — O paciente usa, não consta da prescrição
      prescrito: —   |   relatado: Ibuprofeno 600 mg
      intencionalidade: Não determinada
  · losartana — Dose diferente
      prescrito: 50 mg   |   relatado: 100 mg
      intencionalidade: Não determinada
      registrado por Farm. Ana Souza em 2026-09-10 17:43:44: Paciente dobrou a dose por conta própria.
  · losartana — Frequência diferente
      prescrito: 2x/dia   |   relatado: 1x/dia
      intencionalidade: Não determinada
  · losartana — Horário diferente
      prescrito: 08:00, 20:00   |   relatado: 08:00
      intencionalidade: Não determinada

O QUE O SISTEMA NÃO AVALIOU
  · A fonte não graduou a gravidade (1)
      – Losartana 50 mg × Varfarina 5 mg
  · Substância sem cobertura na base (2)
      – Losartana 50 mg
      – Ibuprofeno 600 mg
  · Medicamento não reconhecido (2)
      – um chá que a vizinha indicou
      – um chá que a vizinha indicou
  · Módulo sem fonte disponível (3)
      – (módulo de reação adversa)
      – (módulo de medicamento × exame laboratorial)
      – (critério de medicamento inadequado para idoso)

LIMITAÇÕES DESTA ANÁLISE
  · Reação adversa não é avaliada: a base do VigiMed ainda não foi carregada (prevista para fase posterior, ver DECISIONS D-005).
  · Paciente com 65 anos ou mais e nenhum critério de inadequação geriátrica carregado: a idade não influencia a priorização.
  · 1 medicamento(s) não reconhecidos: nenhum módulo os avaliou (um chá que a vizinha indicou).
  · 2 verificação(ões) de cobertura falharam por ausência de dado na fonte, não por erro do sistema.
  · 1 interação(ões) documentadas sem gravidade graduada em NENHUMA fonte do acervo. Ficam em prioridade baixa por honestidade, não por serem pouco importantes.
  · 8 achado(s) vêm de extração automática ainda não revisada por farmacêutico.

REVISÃO DO PROFISSIONAL
  · Interação entre Ibuprofeno 600 mg e Varfarina 5 mg — revisado por Farm. Ana Souza em 2026-09-10 17:43:44
      Orientada a suspender o anti-inflamatório por conta própria e procurar o prescritor.

FONTES USADAS NESTE RELATÓRIO
  · DrugBank - interacoes com alimento — 8 evidência(s)
  · Listas do atendimento — 5 evidência(s)
  · DDInter — 3 evidência(s)
  · db_drug_interactions — 3 evidência(s)

------------------------------------------------------------------------
Este relatório é apoio à decisão. Nenhuma conduta foi alterada automaticamente;
toda decisão terapêutica permanece com o profissional.
```
