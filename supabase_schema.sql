-- ANHANGA ENVIRONMENTAL SIGNAL
-- Execute no Supabase SQL Editor uma única vez.
-- Antes de executar, substitua SEU_EMAIL_ADMIN pelo e-mail usado no Supabase Auth.

create extension if not exists pgcrypto;

create table if not exists public.environmental_events (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  created_by uuid not null references auth.users(id) on delete restrict,
  title text not null,
  event_type text not null,
  city text,
  state text,
  event_date date not null default current_date,
  summary text,
  source_url text,
  video_url text,
  published boolean not null default true
);

alter table public.environmental_events enable row level security;

-- Privilégios mínimos para a Data API.
revoke all on table public.environmental_events from anon, authenticated;
grant select on table public.environmental_events to anon;
grant select, insert, update, delete on table public.environmental_events to authenticated;

-- A função restringe operações administrativas ao e-mail definido pelo proprietário.
create or replace function public.is_anhanga_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce((auth.jwt() ->> 'email') = 'amauri.almeidasjr@gmail.com', false);
$$;

-- Reexecutável: remove políticas anteriores com os mesmos nomes.
drop policy if exists "public can read published events" on public.environmental_events;
drop policy if exists "admin can read all events" on public.environmental_events;
drop policy if exists "admin can insert events" on public.environmental_events;
drop policy if exists "admin can update events" on public.environmental_events;
drop policy if exists "admin can delete events" on public.environmental_events;

create policy "public can read published events"
on public.environmental_events
for select
using (published = true);

create policy "admin can read all events"
on public.environmental_events
for select
to authenticated
using (public.is_anhanga_admin());

create policy "admin can insert events"
on public.environmental_events
for insert
to authenticated
with check (public.is_anhanga_admin() and created_by = auth.uid());

create policy "admin can update events"
on public.environmental_events
for update
to authenticated
using (public.is_anhanga_admin())
with check (public.is_anhanga_admin());

create policy "admin can delete events"
on public.environmental_events
for delete
to authenticated
using (public.is_anhanga_admin());

-- Índice para a listagem pública por data.
create index if not exists environmental_events_event_date_idx
on public.environmental_events (event_date desc);

-- Opcional: se futuramente quiser armazenar arquivos no Storage,
-- crie um bucket público chamado anhanga-media pelo painel do Supabase.
-- Para a primeira versão, o app usa URLs de YouTube/Vimeo e não precisa desse bucket.
