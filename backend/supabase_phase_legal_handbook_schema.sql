-- Phase 2: Legal / Handbook Tables
-- Run this in Supabase SQL Editor after Phase 1 if you want structured legal guidance.

begin;

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.law_sources (
  id uuid primary key default gen_random_uuid(),
  source_name text not null,
  source_type text not null default 'pdf',
  version_label text,
  effective_from date,
  effective_to date,
  is_active boolean not null default true,
  notes text,
  created_at timestamptz not null default now()
);

create table if not exists public.legal_categories (
  id uuid primary key default gen_random_uuid(),
  category_name text not null,
  category_code text unique,
  description text,
  display_order int,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.legal_instruments (
  id uuid primary key default gen_random_uuid(),
  category_id uuid references public.legal_categories(id),
  instrument_name text not null,
  instrument_type text check (
    instrument_type is null
    or instrument_type in ('act', 'amendment_act', 'regulation', 'circular', 'framework', 'rule')
  ),
  year int,
  regulator_or_authority text,
  purpose text,
  applicability text,
  current_status text not null default 'active',
  source_id uuid references public.law_sources(id),
  valid_from date,
  valid_to date,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.legal_provisions (
  id uuid primary key default gen_random_uuid(),
  instrument_id uuid references public.legal_instruments(id),
  provision_code text,
  provision_title text not null,
  provision_type text check (
    provision_type is null
    or provision_type in ('section', 'rule', 'regulation', 'requirement', 'principle', 'guideline')
  ),
  summary text,
  practical_meaning text,
  applies_to text[],
  is_active boolean not null default true,
  source_id uuid references public.law_sources(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.regulatory_requirements (
  id uuid primary key default gen_random_uuid(),
  provision_id uuid references public.legal_provisions(id),
  requirement_name text not null,
  requirement_description text,
  applicable_entity text check (
    applicable_entity is null
    or applicable_entity in ('insurer', 'agent', 'broker', 'posp', 'corporate_agent', 'surveyor', 'policyholder', 'all')
  ),
  requirement_value text,
  unit text,
  deadline_days int,
  frequency text,
  is_mandatory boolean not null default true,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.intermediary_types (
  id uuid primary key default gen_random_uuid(),
  intermediary_name text not null,
  represents text,
  max_insurers text,
  min_qualification text,
  training_requirement text,
  key_compliance text,
  min_net_worth text,
  licence_requirement text,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.policyholder_rights (
  id uuid primary key default gen_random_uuid(),
  right_name text not null,
  right_category text,
  description text,
  applicable_insurance_type text[],
  time_limit text,
  refund_or_compensation_rule text,
  escalation_available boolean not null default true,
  related_provision_id uuid references public.legal_provisions(id),
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.grievance_channels (
  id uuid primary key default gen_random_uuid(),
  tier_no int,
  forum_name text not null,
  access_method text,
  time_limit text,
  max_compensation text,
  scope text,
  next_escalation_id uuid references public.grievance_channels(id),
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.violation_types (
  id uuid primary key default gen_random_uuid(),
  violation_category text not null,
  example_violation text,
  responsible_party text,
  related_provision_id uuid references public.legal_provisions(id),
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.penalties (
  id uuid primary key default gen_random_uuid(),
  violation_type_id uuid references public.violation_types(id),
  penalty_title text not null,
  penalty_description text,
  max_penalty_amount numeric,
  penalty_unit text not null default 'INR',
  consequence text,
  authority text not null default 'IRDAI',
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.legal_change_log (
  id uuid primary key default gen_random_uuid(),
  entity_table text not null,
  entity_id uuid not null,
  change_type text check (
    change_type is null
    or change_type in ('added', 'updated', 'removed', 'reinstated', 'superseded')
  ),
  old_value jsonb,
  new_value jsonb,
  change_reason text,
  effective_date date,
  source_reference text,
  changed_by uuid,
  created_at timestamptz not null default now()
);

create index if not exists legal_categories_code_idx on public.legal_categories(category_code);
create index if not exists legal_instruments_category_id_idx on public.legal_instruments(category_id);
create index if not exists legal_instruments_source_id_idx on public.legal_instruments(source_id);
create index if not exists legal_instruments_type_idx on public.legal_instruments(instrument_type);
create index if not exists legal_provisions_instrument_id_idx on public.legal_provisions(instrument_id);
create index if not exists legal_provisions_code_idx on public.legal_provisions(provision_code);
create index if not exists legal_provisions_source_id_idx on public.legal_provisions(source_id);
create index if not exists regulatory_requirements_provision_id_idx on public.regulatory_requirements(provision_id);
create index if not exists regulatory_requirements_entity_idx on public.regulatory_requirements(applicable_entity);
create index if not exists policyholder_rights_related_provision_id_idx on public.policyholder_rights(related_provision_id);
create index if not exists grievance_channels_tier_no_idx on public.grievance_channels(tier_no);
create index if not exists violation_types_related_provision_id_idx on public.violation_types(related_provision_id);
create index if not exists penalties_violation_type_id_idx on public.penalties(violation_type_id);
create index if not exists legal_change_log_entity_idx on public.legal_change_log(entity_table, entity_id);

drop trigger if exists set_legal_instruments_updated_at on public.legal_instruments;
create trigger set_legal_instruments_updated_at
before update on public.legal_instruments
for each row execute function public.set_updated_at();

drop trigger if exists set_legal_provisions_updated_at on public.legal_provisions;
create trigger set_legal_provisions_updated_at
before update on public.legal_provisions
for each row execute function public.set_updated_at();

alter table public.law_sources enable row level security;
alter table public.legal_categories enable row level security;
alter table public.legal_instruments enable row level security;
alter table public.legal_provisions enable row level security;
alter table public.regulatory_requirements enable row level security;
alter table public.intermediary_types enable row level security;
alter table public.policyholder_rights enable row level security;
alter table public.grievance_channels enable row level security;
alter table public.violation_types enable row level security;
alter table public.penalties enable row level security;
alter table public.legal_change_log enable row level security;

commit;
