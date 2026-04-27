-- Supabase setup for authenticated profiles and user-owned chat history.
-- Run this in the Supabase SQL editor for the project used by backend/.env.

create extension if not exists pgcrypto;

create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  date_of_birth date not null,
  age_band text not null,
  gender text not null,
  residential_status text not null,
  annual_income_band text not null,
  occupation_type text not null,
  is_smoker boolean not null default false,
  has_preexisting_conditions boolean not null default false,
  preexisting_conditions text[] not null default '{}',
  primary_insurance_goal text not null,
  life_stage_dependents text[] not null default '{}',
  vehicle_status text,
  has_existing_long_term_tp_policy boolean,
  onboarding_completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

alter table public.user_profiles
  add column if not exists life_stage_dependents text[] not null default '{}',
  add column if not exists vehicle_status text,
  add column if not exists has_existing_long_term_tp_policy boolean;

alter table public.chat_messages
  add column if not exists user_id uuid references auth.users(id) on delete cascade;

create index if not exists idx_chat_sessions_user_id_created_at
  on public.chat_sessions(user_id, created_at desc);

create index if not exists idx_chat_messages_session_user_created_at
  on public.chat_messages(session_id, user_id, created_at);

alter table public.user_profiles enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;

drop policy if exists "Users can read their own profile" on public.user_profiles;
create policy "Users can read their own profile"
  on public.user_profiles for select
  using (auth.uid() = user_id);

drop policy if exists "Users can write their own profile" on public.user_profiles;
create policy "Users can write their own profile"
  on public.user_profiles for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "Users can read their own sessions" on public.chat_sessions;
create policy "Users can read their own sessions"
  on public.chat_sessions for select
  using (auth.uid() = user_id);

drop policy if exists "Users can write their own sessions" on public.chat_sessions;
create policy "Users can write their own sessions"
  on public.chat_sessions for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "Users can read their own messages" on public.chat_messages;
create policy "Users can read their own messages"
  on public.chat_messages for select
  using (auth.uid() = user_id);

drop policy if exists "Users can write their own messages" on public.chat_messages;
create policy "Users can write their own messages"
  on public.chat_messages for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
