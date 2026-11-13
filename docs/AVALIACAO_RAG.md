# Avaliação local do Deep Research (RAG)

Este benchmark usa o manual **fictício** `exemplos/manual_operacional_rag.md` e **8 perguntas rotuladas**: cinco respondíveis e três sem resposta disponível. O objetivo é verificar comportamentos mensuráveis e identificar casos que exigem revisão humana.

## Executar no Windows

Com o Ollama funcionando e os modelos `qwen3:4b-instruct` e `nomic-embed-text` instalados, execute na pasta principal:

```powershell
# Abra o PowerShell na raiz do repositório atlas-ai
.\.venv\Scripts\python.exe scripts\evaluate_rag_local.py
```

Na primeira execução informada em Windows, o benchmark aprovou **8/8 critérios heurísticos** (5 casos respondíveis e 3 abstenções). Isso é evidência de comportamento naquele conjunto, não prova de qualidade geral.

Os resultados aparecem no PowerShell e ficam registrados em `relatorios/avaliacao_rag_local.json`, pasta ignorada pelo Git. **Não compartilhe relatórios com dados privados**. O manual incluído no projeto contém apenas dados inventados.

## O que é medido

- **Cobertura de evidências recuperadas:** proporção das expressões esperadas presentes nos trechos selecionados.
- **Cobertura da resposta:** proporção de expressões esperadas presentes no texto gerado, normalizando acentos e permitindo alternativas cadastradas.
- **Citações válidas:** referências `[Fonte N]` no corpo da resposta correspondem aos trechos selecionados. A lista automática de fontes no rodapé não conta como citação do modelo.
- **Abstenção:** o modelo identifica, por expressões como "não consta" ou "não há evidência", perguntas sem informação suficiente.
- **Tempo:** duração observada por pergunta.

**Essas métricas são heurísticas textuais, não juízes semânticos.** Uma paráfrase correta pode ser marcada incorretamente como falha; uma resposta que mencione palavras esperadas pode continuar factualmente errada. Analise o JSON antes de concluir que a resposta é confiável.

## Limitações técnicas

- A avaliação usa **embeddings e geração reais do Ollama** por meio das funções do Atlas.
- A recuperação é feita **em memória**, por similaridade cosseno, sem acessar a RPC `match_atlas_chunks` no Supabase. Isso protege o banco durante o teste, mas **não valida pgvector nem RLS**.
- O manual é dividido em seções sintéticas para avaliação; o upload real de Markdown usa a segmentação normal do Deep Research.
- O conjunto de oito perguntas é pequeno e fictício; os resultados dependem da configuração do modelo e da máquina.
- O benchmark retorna código de saída diferente de zero se alguma métrica heurística falhar. Isso indica **revisão**, não necessariamente defeito técnico.

## Testes sem Ollama

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\test_rag_eval.py
```

Esses testes verificam as métricas com exemplos simulados, incluindo referências inválidas e abstenção. São independentes dos testes de geração real.

**Próxima evolução:** avaliação E2E separada com duas contas de teste e documentos fictícios realmente indexados no Supabase, medindo o retorno da RPC pgvector e a autorização cruzada.
