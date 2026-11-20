# Preparação para publicação do Atlas AI v12

**Escopo:** publicação do **código-fonte** no GitHub. A aplicação não está preparada para hospedagem pública: frontend Vite, API FastAPI e Ollama devem continuar em `127.0.0.1` enquanto não existir arquitetura de implantação segura.

## Evidências confirmadas (19/11/2026)

- [x] Cinco módulos demonstrados e integrados; 145 testes Python aprovados na última execução compartilhada.
- [x] Benchmark local RAG: 8/8 **critérios heurísticos** aprovados. Não é avaliação de RLS/pgvector real.
- [x] Histórico GitHub: examinados **20 commits** e **60 caminhos distintos** no repositório até a v12, sem correspondências com a seleção de padrões de segredos examinada. Uma busca por padrões **não garante** ausência de credenciais, especialmente em arquivos binários ou formatos não reconhecidos.
- [x] `.env`, `frontend/.env.local` e os diretórios de build estão no `.gitignore`; exemplos `.env.example` não contêm chaves reais.
- [x] Banco Supabase reativado e confirmado **ACTIVE_HEALTHY** durante a verificação.
- [x] As quatro tabelas `atlas_runs`, `atlas_messages`, `atlas_documents` e `atlas_chunks` estavam com RLS ligado; a função `match_atlas_chunks` estava com `SECURITY INVOKER`.
- [x] Teste **transacional** no Postgres: com dois usuários existentes e papel `authenticated` simulado, cada conta enxergou somente seu próprio registro, documento e chunk de teste; a RPC vetorial retornou **1 resultado do próprio documento e 0 do documento da outra conta**. O teste foi encerrado com `ROLLBACK`; confirmamos 0 registros temporários persistidos.

### Limites do teste de banco

Esse teste exercitou **as políticas RLS e a função pgvector reais**, mas não usou dois tokens JWT emitidos pelo Supabase nem percorreu as rotas FastAPI/HTTP. Portanto **não substitui** um teste E2E de IDOR/BOLA com duas contas reais no navegador.

O Supabase Security Advisor também apontou **Leaked Password Protection Disabled**: [orientações oficiais](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection). Ativar no Dashboard se o plano disponibilizar; se não, registrar essa limitação antes de hospedar a aplicação publicamente.

## Verificação local antes de tornar público

Na raiz do repositório, após `git pull origin main`:

```powershell
# Varredura de arquivos rastreados e histórico Git local (não exibe segredos)
.\.venv\Scripts\python.exe scripts\audit_publication.py

# Regressão do backend
.\.venv\Scripts\python.exe -m pytest -q

# Compilação e auditoria do frontend
cd frontend
npm.cmd ci
npm.cmd run build
npm.cmd audit --audit-level=high
cd ..
```

A checagem de **arquivos rastreados** roda também no CI. A checagem **histórica** completa deve ser executada em um clone com o histórico completo. O script é heurístico; complemente com scanner dedicado (como Gitleaks) e inspeção manual. Ele **não imprime valores encontrados**, somente tipo, caminho e referência curta do commit.

**Se qualquer ferramenta reportar credenciais reais, não publique**. Revogue/rotacione as chaves antes de tratar a limpeza do histórico; apagar um arquivo no commit novo não elimina cópias antigas.

## Checklist de publicação

- [ ] Executar os comandos acima em um clone local com histórico completo e conferir o resultado.
- [ ] Testar acesso entre contas A e B com **dois logins reais**, verificando o retorno 404 para `POST /api/history/read` com um `run_id` da outra conta, sem copiar tokens em chats ou relatórios.
- [ ] Revisar a licença proposta em `LICENSE`: **MIT**, permissiva, permite uso e redistribuição com aviso de copyright. Confirmar se essa é a escolha desejada.
- [ ] Capturar telas com **dados de demonstração exclusivamente fictícios**: Assistente, Economics, Atlas Data, Deep Research e Model Lab. Não incluir e-mails, JWT, nomes de clientes, relatórios corporativos ou IDs de projetos.
- [ ] Incorporar as capturas ao README e conferir a navegação no GitHub.
- [ ] Verificar manualmente configurações de GitHub Secret Scanning/Dependabot e Supabase Auth.
- [ ] Somente então usar GitHub → Settings → General → Danger Zone → Change repository visibility → Public.

A publicação do repositório é uma escolha do responsável pelo projeto; **não acontece automaticamente** ao aprovar um PR.

## Teste HTTP entre contas (ainda pendente)

No navegador local, com duas contas de **teste** sob seu controle, gere um registro com a conta A e guarde apenas o UUID desse registro. Depois, com login válido da conta B, envie `POST /api/history/read` com o ID de A, pelo mesmo frontend autenticado, sem compartilhar tokens. O resultado esperado é `404` e nenhuma informação de A. Consulte `docs/VALIDACAO.md` para o checklist geral.

## Decisão de lançamento

**Código de portfólio:** pode ser disponibilizado após auditoria histórica local, escolha explícita da licença e revisão das capturas/README.

**Aplicação web pública:** **não aprovada nesta arquitetura**. Exige HTTPS, autenticação obrigatória, isolamento do Ollama, limites de requisição/uso, tratamento de segredos, observabilidade, política de retenção e testes HTTP reais entre contas.
