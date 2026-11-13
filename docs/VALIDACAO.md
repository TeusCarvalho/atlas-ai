# Plano de validação e evidências

Este documento separa **observações já realizadas** de **testes pendentes**, para evitar tratar um protótipo funcional como produção validada.

## Evidências disponíveis até a preparação da documentação

| Área | Evidência | Limite da conclusão |
| --- | --- | --- |
| Testes Python | **145/145** testes aprovados no Windows após PR #4 | Não equivalem a testes E2E ou de produção |
| Build React | `npm run build` concluído com Vite `6.4.6` no Windows | Não verifica comportamento de todas as telas |
| Dependências | `npm audit`: **0 vulnerabilidades detectadas** naquela execução | Auditoria é pontual; não garante segurança futura |
| Assistente | Cálculo de 200 para 300: **50%** | Uma pergunta validada; duração relatada de 12,12 s |
| Economia | Interface mostrou IPCA, histórico de 60 meses e projeção de 3 meses | Exatidão estatística não foi auditada externamente |
| Atlas Data | CSV com três bases; Goiânia com **200** entregas | Um arquivo e uma consulta validados |
| Deep Research | Pergunta sobre manual respondida com fontes; pergunta sem evidência recebeu abstenção | Não substitui avaliação E2E de pgvector |
| Benchmark RAG local | **8/8 critérios heurísticos aprovados** com Ollama, 7 trechos sintéticos e 8 perguntas | Recuperação por cosseno em memória; métricas de palavras-chave, sem pgvector real |
| Model Lab | `qwen3:4b-instruct` com **4/4 cenários** aprovados em uma repetição | Cenários limitados e sintéticos |
| Login com duas contas | Interfaces exibiram históricos distintos | Isolamento visual, sem tentativa direta de acesso cruzado na API |
| Acesso sem login | `/api/history` e `/api/research/documents` retornaram **HTTP 401** | Não comprova ausência de IDOR/BOLA com token válido |

## Executar os testes localmente

A partir da raiz do repositório:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

No frontend:

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
npm.cmd audit
```

Valide também a conectividade:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
curl.exe -s -o NUL -w "HTTP %{http_code}" http://127.0.0.1:8000/api/history
curl.exe -s -o NUL -w "HTTP %{http_code}" http://127.0.0.1:8000/api/research/documents
```

**Resultados esperados:** saúde da API com `status: ok` e rotas protegidas com HTTP `401` ou `403` quando não houver autenticação. Um `200` em rota protegida sem token requer investigação. Não envie chaves ou tokens para terceiros.

## Plano de regressão funcional

- [ ] Abrir frontend e confirmar conexão com o backend.
- [ ] Fazer login com uma conta de teste e consultar histórico.
- [ ] Fazer login com outra conta de teste; confirmar que cada interface mostra apenas seus dados.
- [ ] **Pendente:** testar no nível da API se a segunda conta não pode ler dados da primeira por ID, mesmo autenticada.
- [ ] Calcular variação percentual com o Assistente.
- [ ] Executar previsão econômica e conferir tabelas, gráficos e trilha de auditoria.
- [ ] Importar CSV e XLSX válidos; testar também arquivo inválido/grande.
- [ ] Consultar documento RAG com resposta presente e ausente, conferindo citações.
- [ ] Excluir documento de teste e verificar exclusão de seus trechos.
- [ ] Executar Model Lab com um modelo e depois comparar com outro, observando limitações.
- [ ] Executar `pytest`, `npm build` e `npm audit` após alterações.

Os itens listados são um **roteiro de nova execução**, não indicação de que todos os testes seguem pendentes em todos os ambientes.

## Próximas avaliações de IA

**RAG:** já existe benchmark com perguntas rotuladas e métricas heurísticas em [AVALIACAO_RAG.md](AVALIACAO_RAG.md). Ampliar o conjunto e acrescentar avaliação E2E com pgvector, autorização cruzada e revisão humana.

**Agent Studio:** avaliar seleção de ferramentas, validação de argumentos, cenários negativos e comportamento em entradas adversariais.

**Economia:** estabelecer avaliação temporal com janela de treino/teste e comparar baselines de previsão sem vazamento de futuro.

**Model Lab:** comparar modelos sob parâmetros controlados e múltiplas repetições; não interpretar aprovação em quatro cenários como medida universal de qualidade.

## Critério para publicação pública

O repositório de código pode ser preparado para portfólio após revisão de arquivos, credenciais, licenças e documentação. **Hospedar a aplicação acessível pela internet é uma etapa distinta** e exige uma avaliação de segurança própria.
