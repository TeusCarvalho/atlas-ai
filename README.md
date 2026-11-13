
# Atlas Agent Studio v12 — Auditoria e correções prioritárias

Esta é uma **atualização de manutenção**, não um novo módulo de IA. Preserva os cinco módulos da v11.

## Correções incluídas
- Atualização do Vite para **6.4.6**, versão com correções de segurança publicadas para a linha 6.
- `supabase/schema.sql` agora também aceita mensagens do canal `research` em novas instalações; o banco online do Atlas já havia sido corrigido e **não requer execução de SQL novamente**.
- Regras explícitas de `.gitignore` para impedir que `.env` do frontend seja incluído no Git.
- Novos testes de regressão sobre instalação, RLS e configurações locais.
- Scripts `npm run audit:prod` e `npm run audit:all` para auditar dependências instaladas.

## O que NÃO foi validado e continua pendente

1. `npm install` / `npm run build` / `npm audit` com as dependências reais no Windows.
2. Teste de duas contas reais para verificar isolamento RLS.
3. Avaliação de RAG baseada em perguntas rotuladas e documentos de referência.
4. Confirmação de segurança de acesso remoto. **Não exponha** Vite, FastAPI nem Ollama na internet.
5. Confirmação de proteção contra senhas vazadas no Supabase, se disponível no plano.

## Atualização rápida no Windows

1. Faça backup de `C:\\Users\\Pessoal\\PycharmProjects\\atlas-agent-toolcalling`.
2. Pare os terminais do frontend e backend com `Ctrl+C`.
3. Extraia a atualização rápida na raiz do projeto, substituindo apenas os arquivos contidos no ZIP.
4. Preserve `.env`, `frontend/.env.local`, `.venv`, dados e relatórios.
5. No terminal principal:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\start_api_windows.ps1
```

6. No outro terminal:

```powershell
cd "C:\\Users\\Pessoal\\PycharmProjects\\atlas-agent-toolcalling\\frontend"
npm install
npm run build
npm run audit:all
npm run dev
```

**Não use `npm audit fix --force`** sem revisar as mudanças.
Se o audit ainda reportar vulnerabilidades, registre o relatório e corrija os pacotes afetados.

## Critério de conclusão
A v12 ficará validada quando `pytest`, `npm run build`, auditoria npm, regressão do login, histórico, RAG, Model Lab e testes entre contas forem concluídos.


---

# Atlas Agent Studio v11 — Model Lab

**Nova funcionalidade:** laboratório para comparar modelos **já instalados no Ollama** em quatro cenários de avaliação controlada. A v11 preserva **Economia, Modelos (previsão do IPCA), Auditoria, Assistente, Atlas Data, Histórico, Deep Research/RAG, Supabase Auth e pgvector**.

## Entrega e limites de validação

- **123 testes automatizados Python aprovados** no ambiente de desenvolvimento (os 102 testes anteriores + 21 novos testes do Model Lab).
- Código React/JSX verificado sintaticamente com parser TypeScript. **A compilação `npm run build` ainda precisa ser realizada no seu Windows**; o ambiente de criação não conseguiu instalar as dependências do npm.
- Benchmarks reais exigem Ollama instalado na máquina do usuário; **não foram medidas velocidades reais da RX 6600 LE neste ambiente**.
- **Nenhuma migração SQL para a v11**: os dados existentes da v9 e da v10 permanecem no Supabase. O Model Lab **não grava resultados ou prompts no banco** e os mantém apenas no estado da aba aberta no navegador.
- A aplicação é **local**, com FastAPI em `127.0.0.1:8000`, Vite em `127.0.0.1:5173` e Ollama em `127.0.0.1:11434`. Não exponha os serviços à internet sem revisar a arquitetura de segurança.

## 1. Atualização rápida (recomendada)

O projeto existente do usuário fica em:

`C:\Users\Pessoal\PycharmProjects\atlas-agent-toolcalling`

1. Faça uma cópia de segurança dessa pasta.
2. Pare os terminais do FastAPI e Vite com `Ctrl+C`.
3. Extraia `atlas-agent-v11-atualizacao-rapida.zip` **diretamente sobre a raiz** `atlas-agent-toolcalling`, substituindo os arquivos correspondentes.
4. **Não apague ou sobrescreva** `.env`, `frontend/.env.local`, `.venv`, `relatorios` ou outros arquivos pessoais. Eles não fazem parte do ZIP.
5. **Não execute `supabase/schema.sql` nem `supabase/rag_v10.sql` novamente:** a atualização v11 não modifica o banco.

**Terminal 1 — FastAPI**

```powershell
cd "C:\Users\Pessoal\PycharmProjects\atlas-agent-toolcalling"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_api_windows.ps1
```

**Terminal 2 — React**

```powershell
cd "C:\Users\Pessoal\PycharmProjects\atlas-agent-toolcalling\frontend"
npm install
npm run build
npm run dev
```

Abra http://127.0.0.1:5173, entre com sua conta Supabase e selecione **Model Lab** no menu.

## 2. Primeiro benchmark

1. Confira que o Ollama está funcionando. `ollama ps` mostra modelos carregados. Os modelos instalados aparecem em `ollama list`.
2. Na aba **Model Lab**, clique em **Atualizar**. A aplicação detecta os modelos instalados. O modelo de embeddings `nomic-embed-text` não é exibido como opção de chat.
3. Escolha **qwen3:4b-instruct** e **1 repetição**.
4. Clique em **Executar benchmark**. A aplicação fará **4 chamadas** sequenciais ao Ollama e mostrará: aprovação, duração, tokens gerados, tokens/segundo, tempo de carga e motivo de parada.
5. Opcional: escolha também `qwen3:4b`, caso esteja instalado; com dois modelos e uma repetição, serão **8 chamadas** sequenciais. Como sua GPU tem 8 GB de VRAM, comparar um modelo por vez é uma alternativa se houver uso elevado de memória.
6. Envie uma captura da tabela e do resumo para analisarmos o resultado.

## 3. O que o Model Lab avalia

| Cenário | Critério automatizado | Limitação |
|---|---|---|
| Seguir instrução | Responder **ATLAS**, exatamente | Não é avaliação geral de linguagem. |
| Tool calling | Solicitar `calcular_variacao_percentual` com argumentos `120` e `150` | A função **não é executada**; é avaliada a escolha da ferramenta e parâmetros. |
| Fidelidade ao contexto | Citar assinatura digital do encarregado e `[Fonte 1]` | **RAG simulado** com um trecho fornecido; não exercita recuperação vetorial real. |
| Abstenção | Admitir que a fonte não informa preço do diesel | Critério heurístico, não prova ausência de alucinação em outras perguntas. |

Cada cenário retorna aprovado/não aprovado. O percentual é **taxa de aprovação nesses testes específicos**, não uma nota geral de qualidade de IA ou medida científica de acurácia.

### Métricas de desempenho

- **Duração da requisição:** tempo observado pelo backend Python, incluindo espera e transmissão local.
- **Tempo do Ollama:** duração reportada no campo `total_duration` (não é necessariamente igual ao tempo do Python).
- **Carregamento:** `load_duration`; pode ser maior na primeira execução.
- **Velocidade de geração (tokens/s):** `eval_count / eval_duration`, usando a duração em segundos. Se o Ollama não fornecer `eval_duration`, a métrica não aparece.
- **VRAM reportada por Ollama:** obtida de `/api/ps` somente para modelos carregados; **não é a utilização total da GPU**.

Os testes usam `temperature: 0`, `num_predict: 160`, `think: false`, `keep_alive: 1m`, sem streaming e com prompts fixos. Alguns modelos podem não oferecer tool calling ou não respeitar `think: false`; nesse caso, o resultado pode indicar falha de compatibilidade em vez de baixa qualidade geral.

## 4. Aprendizado de Engenharia de IA

- **LLMOps e Evals:** diferencie *taxa de aprovação em cenários específicos* de *qualidade genérica*; avalie limitações de heurísticas de comparação.
- **Latência vs. throughput:** a primeira resposta pode incluir carga do modelo; velocidade em tokens/s não equivale a tempo total percebido.
- **Orquestração de testes:** execuções limitadas e sequenciais para reduzir pressão de GPU.
- **Segurança de agentes:** os testes de seleção de ferramenta **não executam ferramentas** e não permitem chamadas a URLs arbitrárias.

Referência: documentação oficial da API Ollama: https://docs.ollama.com/api ou https://github.com/ollama/ollama/blob/main/docs/api.md

## 5. Checklist de regressão

- Login Supabase continua funcionando.
- Dados antigos do Histórico continuam disponíveis.
- Deep Research ainda responde com trechos e fontes (já validado anteriormente pelo usuário).
- Economia e Atlas Data continuam funcionando.
- A aba Model Lab lista somente os modelos locais detectados, e um benchmark conclui sem HTTP 500.
- `npm run build` conclui no Windows.

**Pendências antes da publicação:** testes de isolamento entre usuários reais, avaliação de RAG com dados de referência, auditoria do `npm audit`, proteção contra senhas vazadas, revisão de dados sensíveis, otimização da UX, e implantação segura. Não publique os serviços Ollama/FastAPI diretamente na internet.
