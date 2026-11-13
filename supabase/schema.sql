-- Execute no SQL Editor do projeto Supabase, após conferir o projeto correto.
-- Nenhum dado pessoal/arquivo Excel é armazenado; somente metadados e resultados.
create table if not exists public.atlas_runs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  category text not null check (category in ('economia', 'relatorio', 'dataset')),
  title text not null check (length(title) between 1 and 160),
  summary text not null default '',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists atlas_runs_user_created_idx on public.atlas_runs(user_id, created_at desc);

create table if not exists public.atlas_messages (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  channel text not null check (channel in ('assistente', 'dados', 'research')),
  role text not null check (role in ('user', 'assistant')),
  body text not null,
  tools jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists atlas_messages_user_created_idx on public.atlas_messages(user_id, created_at desc);

alter table public.atlas_runs enable row level security;
alter table public.atlas_messages enable row level security;

revoke all on table public.atlas_runs from public, anon;
revoke all on table public.atlas_messages from public, anon;
revoke all on table public.atlas_runs from authenticated;
revoke all on table public.atlas_messages from authenticated;
grant select, insert on table public.atlas_runs to authenticated;
grant select, insert on table public.atlas_messages to authenticated;

-- Policies owner-scoped. Não concedemos UPDATE/DELETE nesta versão.
drop policy if exists "atlas_runs_owner_select" on public.atlas_runs;
create policy "atlas_runs_owner_select" on public.atlas_runs for select to authenticated
using ((select auth.uid()) = user_id);
drop policy if exists "atlas_runs_owner_insert" on public.atlas_runs;
create policy "atlas_runs_owner_insert" on public.atlas_runs for insert to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "atlas_messages_owner_select" on public.atlas_messages;
create policy "atlas_messages_owner_select" on public.atlas_messages for select to authenticated
using ((select auth.uid()) = user_id);
drop policy if exists "atlas_messages_owner_insert" on public.atlas_messages;
create policy "atlas_messages_owner_insert" on public.atlas_messages for insert to authenticated
with check ((select auth.uid()) = user_id);

-- Compatibilidade com instalacoes antigas (v9): habilita o canal research
-- sem remover registros anteriores. Nao e necessario reaplicar no banco
-- Atlas Agent Studio ja corrigido.
alter table public.atlas_messages
  drop constraint if exists atlas_messages_channel_check;
alter table public.atlas_messages
  add constraint atlas_messages_channel_check
  check (channel in ('assistente', 'dados', 'research'));
