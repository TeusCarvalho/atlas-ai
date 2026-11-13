# Segurança e privacidade

Este documento descreve controles implementados e **limites conhecidos** do Atlas AI. Um controle configurado não equivale a uma auditoria independente ou garantia de segurança.

## Modelo de implantação

**Desenvolvimento local:** frontend Vite, FastAPI e Ollama na interface de loopback (`127.0.0.1`). O Supabase, quando configurado, é um serviço externo para autenticação e armazenamento.

**Não publique diretamente** as portas 5173, 8000 ou 11434, nem configure portas ou proxy público antes de definir TLS, controle de acesso, gestão de segredos, observabilidade e rate limits.

## Gerenciamento de segredos

- Arquivos `.env`, `.env.local`, credenciais e dados pessoais **não devem ser versionados**.
- Apenas arquivos `.env.example` com valores fictícios podem ser enviados ao Git.
- No frontend, use somente a chave **publishable**; ela não concede, por si só, autorização sobre registros. A proteção efetiva depende das políticas RLS.
- **Nunca** inclua `service_role`, `sb_secret_`, tokens pessoais ou senhas em código, documentação ou capturas.
- Rotacione imediatamente qualquer credencial real que tenha sido comprometida e revise o histórico do Git; remover um arquivo do commit mais recente não o elimina automaticamente do histórico anterior.

A varredura local por expressões regulares realizada antes do primeiro commit verificou 45 arquivos e não encontrou os padrões consultados. Isso **não garante** ausência de todos os tipos de segredos; auditorias posteriores devem usar ferramentas especializadas.

## Autenticação e RLS

As tabelas `atlas_runs`, `atlas_messages`, `atlas_documents` e `atlas_chunks` usam RLS. As políticas de acesso implementadas restringem leitura e escrita por `user_id = auth.uid()` e, no caso dos chunks, verificam também o documento associado. A RPC de busca vetorial usa `SECURITY INVOKER`.

As rotas de histórico e documentos exigem identidade quando o Supabase está configurado; testes sem token retornaram **HTTP 401** em `/api/history` e `/api/research/documents`.

**Validação já realizada:** duas contas acessaram a interface e apresentaram históricos distintos. **Teste ainda pendente:** tentativa de leitura cruzada e acesso direto a recursos da outra conta pela API, usando duas credenciais válidas de teste. Não utilize credenciais de terceiros, nem publique JWTs em tickets ou logs.

> **Atenção ao modo local:** se Supabase URL e chave não estiverem configuradas, o backend oferece modo de desenvolvimento local, com capacidades limitadas e sem autenticação remota. Essa condição reforça a proibição de expor o servidor em rede pública.

## Tratamento de dados

| Fluxo | Onde os dados ficam | Observações |
| --- | --- | --- |
| Chat | Memória local e, quando habilitado, `atlas_messages` no Supabase | Mensagens vinculadas à conta |
| Economia | Resultados em memória e resumos em `atlas_runs` | Dados-base de IPCA são públicos |
| Atlas Data | DataFrame em memória durante a sessão | Arquivo original não é armazenado no Supabase pelo fluxo atual |
| Deep Research | Texto extraído e embeddings no Supabase | Arquivo original descartado; **conteúdo extraído continua persistido** |
| Model Lab | Memória da aba/retorno da API | Benchmarks não persistidos no Supabase |

Evite usar informações sigilosas, dados pessoais ou documentos corporativos no RAG sem revisar base legal, finalidade, políticas de acesso e retenção.

## Proteções e controles a ampliar

1. **Teste de acesso entre contas via API** com dois usuários de teste.
2. **Proteção contra senhas vazadas**: a auditoria do Supabase apontou que estava desativada; verificar a disponibilidade de ativação no plano.
3. **Auditoria de dependências**: o `npm audit` indicou zero vulnerabilidades detectadas no teste local da v12, mas precisa ser reexecutado periodicamente.
4. **Rate limiting e quotas** para uploads, consultas e benchmarks.
5. **Política de exclusão/retenção** dos trechos e embeddings no Supabase, além das mensagens e execuções persistidas.
6. **Análise de prompt injection** em documentos enviados para RAG e manipulações de dados.
7. **Implantação segura** com HTTPS, isolamento de serviços, logs apropriados e revisão de permissões.

## Como reportar um problema

Enquanto o repositório estiver privado, comunique vulnerabilidades diretamente ao responsável pelo projeto. Não abra issues públicas contendo tokens, senhas, dados reais ou caminhos internos de usuários.

Para instruções de validação, consulte [VALIDACAO.md](VALIDACAO.md).
