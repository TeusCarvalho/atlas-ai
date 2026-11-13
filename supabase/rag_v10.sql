-- Atlas Deep Research v10: somente tabelas novas. Nao modifica historico existente.
-- Instalar no SQL Editor do projeto Atlas Agent Studio.
create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create table if not exists public.atlas_documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  filename text not null check (char_length(filename) between 1 and 160),
  pages integer not null check (pages between 1 and 60),
  chunk_count integer not null check (chunk_count between 1 and 160),
  embedding_model text not null default 'nomic-embed-text',
  created_at timestamptz not null default now()
);
create index if not exists atlas_documents_user_created_idx
  on public.atlas_documents (user_id, created_at desc);

create table if not exists public.atlas_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.atlas_documents(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  page_number integer not null check (page_number >= 1),
  content text not null check (char_length(content) between 1 and 1200),
  embedding extensions.vector(768) not null,
  created_at timestamptz not null default now()
);
create index if not exists atlas_chunks_document_idx on public.atlas_chunks(document_id);
create index if not exists atlas_chunks_user_idx on public.atlas_chunks(user_id);

alter table public.atlas_documents enable row level security;
alter table public.atlas_chunks enable row level security;

-- Mesma politica de dono do inicio ao fim. Nenhuma permissao anon.
revoke all on public.atlas_documents from public, anon;
revoke all on public.atlas_chunks from public, anon;
grant select, insert, delete on public.atlas_documents to authenticated;
grant select, insert on public.atlas_chunks to authenticated;

-- Policies idempotentes para facilitar desenvolvimento.
drop policy if exists atlas_documents_owner_select on public.atlas_documents;
create policy atlas_documents_owner_select on public.atlas_documents for select to authenticated
  using ((select auth.uid()) = user_id);
drop policy if exists atlas_documents_owner_insert on public.atlas_documents;
create policy atlas_documents_owner_insert on public.atlas_documents for insert to authenticated
  with check ((select auth.uid()) = user_id);
drop policy if exists atlas_documents_owner_delete on public.atlas_documents;
create policy atlas_documents_owner_delete on public.atlas_documents for delete to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists atlas_chunks_owner_select on public.atlas_chunks;
create policy atlas_chunks_owner_select on public.atlas_chunks for select to authenticated
  using ((select auth.uid()) = user_id
    and exists (select 1 from public.atlas_documents d
                where d.id = document_id and d.user_id = (select auth.uid())));
drop policy if exists atlas_chunks_owner_insert on public.atlas_chunks;
create policy atlas_chunks_owner_insert on public.atlas_chunks for insert to authenticated
  with check ((select auth.uid()) = user_id
    and exists (select 1 from public.atlas_documents d
                where d.id = document_id and d.user_id = (select auth.uid())));

-- SECURITY INVOKER mantem RLS; pesquisa restringida a documentos do proprio usuario.
create or replace function public.match_atlas_chunks(
  query_embedding extensions.vector(768),
  match_count integer default 5,
  filter_document_id uuid default null
)
returns table (
  chunk_id uuid,
  document_id uuid,
  filename text,
  page_number integer,
  content text,
  similarity double precision
)
language sql stable security invoker
set search_path = ''
as $$
  select c.id, d.id, d.filename, c.page_number, c.content,
         (1 - (c.embedding operator(extensions.<=>) query_embedding))::double precision
  from public.atlas_chunks c
  join public.atlas_documents d on d.id = c.document_id
  where c.user_id = (select auth.uid())
    and d.user_id = (select auth.uid())
    and (filter_document_id is null or d.id = filter_document_id)
    and d.embedding_model = 'nomic-embed-text'
  order by c.embedding operator(extensions.<=>) query_embedding
  limit least(greatest(match_count, 1), 8);
$$;
revoke all on function public.match_atlas_chunks(extensions.vector(768), integer, uuid)
  from public, anon;
grant execute on function public.match_atlas_chunks(extensions.vector(768), integer, uuid)
  to authenticated;
