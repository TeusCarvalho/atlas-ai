-- Consulta de inspeção, sem alterações. Execute após schema.sql no SQL Editor.
select schemaname, tablename, rowsecurity
from pg_tables where schemaname = 'public' and tablename in ('atlas_runs','atlas_messages')
order by tablename;

select tablename, policyname, cmd, roles, qual, with_check
from pg_policies where schemaname = 'public' and tablename in ('atlas_runs','atlas_messages')
order by tablename, cmd;
