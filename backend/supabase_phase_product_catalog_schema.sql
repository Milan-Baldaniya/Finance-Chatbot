-- Phase 1: Product Catalog Tables
-- Run this in Supabase SQL Editor before importing insurer/product data.

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

create table if not exists public.insurance_companies (
  id uuid primary key default gen_random_uuid(),
  company_name text not null,
  company_slug text unique not null,
  insurer_category text not null check (
    insurer_category in ('life', 'general', 'standalone_health', 'reinsurance')
  ),
  ownership_type text check (
    ownership_type is null or ownership_type in ('public', 'private')
  ),
  irdai_registration_no text,
  established_year int,
  headquarters text,
  website text,
  background text,
  market_position text,
  key_segments text[],
  status text not null default 'active' check (
    status in ('active', 'inactive', 'merged', 'discontinued')
  ),
  source_document text,
  source_page_refs text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.insurance_products (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references public.insurance_companies(id) on delete cascade,
  product_name text not null,
  product_slug text not null,
  plan_code text,
  product_category text not null check (
    product_category in ('life', 'health', 'motor', 'travel', 'home', 'commercial', 'reinsurance')
  ),
  product_type text,
  distribution_channel text check (
    distribution_channel is null
    or distribution_channel in ('online', 'offline', 'agent', 'bancassurance', 'direct', 'mixed')
  ),
  launch_year int,
  current_status text not null default 'active' check (
    current_status in ('active', 'discontinued', 'legacy', 'upcoming', 'suspended')
  ),
  status_reason text,
  short_description text,
  min_entry_age text,
  max_entry_age text,
  eligibility_summary text,
  policy_term text,
  premium_payment_term text,
  min_sum_assured text,
  max_sum_assured text,
  premium_range text,
  tax_benefits text,
  source_document text,
  source_page_refs text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(company_id, product_slug)
);

create table if not exists public.product_features (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.insurance_products(id) on delete cascade,
  feature_title text,
  feature_description text not null,
  feature_type text check (
    feature_type is null
    or feature_type in ('core_feature', 'optional_feature', 'digital_feature', 'network_feature', 'financial_feature', 'policy_feature')
  ),
  display_order int not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.product_benefits (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.insurance_products(id) on delete cascade,
  benefit_type text not null,
  benefit_description text not null,
  applies_to text check (
    applies_to is null or applies_to in ('base_plan', 'rider', 'variant', 'optional_addon')
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.product_conditions (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.insurance_products(id) on delete cascade,
  condition_type text not null,
  condition_title text,
  condition_description text not null,
  severity text check (
    severity is null or severity in ('informational', 'important', 'restrictive', 'compliance_critical')
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.product_riders_addons (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.insurance_products(id) on delete cascade,
  rider_name text not null,
  rider_type text,
  description text,
  is_optional boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.product_claim_performance (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.insurance_products(id) on delete cascade,
  metric_name text not null,
  metric_value text not null,
  metric_year text,
  metric_context text,
  source_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.product_ideal_customer_profiles (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.insurance_products(id) on delete cascade,
  profile_summary text not null,
  customer_life_stage text[],
  income_segment text[],
  risk_profile text[],
  recommended_for text[],
  not_recommended_for text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.product_versions (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.insurance_products(id) on delete cascade,
  version_no int not null,
  change_type text not null check (
    change_type in ('created', 'updated', 'discontinued', 'reactivated', 'corrected', 'imported')
  ),
  change_summary text not null,
  changed_fields jsonb,
  effective_from date,
  effective_to date,
  changed_by uuid,
  approved_by uuid,
  approval_status text not null default 'draft' check (
    approval_status in ('draft', 'pending_review', 'approved', 'rejected')
  ),
  source_type text check (
    source_type is null or source_type in ('pdf_import', 'admin_manual_update', 'insurer_website', 'irdai_update', 'system_correction')
  ),
  source_reference text,
  created_at timestamptz not null default now(),
  unique(product_id, version_no)
);

create table if not exists public.product_import_batches (
  id uuid primary key default gen_random_uuid(),
  source_document_name text not null,
  source_document_version text,
  source_file_url text,
  import_status text not null default 'pending' check (
    import_status in ('pending', 'processing', 'completed', 'failed', 'partially_completed')
  ),
  total_companies_detected int not null default 0,
  total_products_detected int not null default 0,
  total_products_added int not null default 0,
  total_products_updated int not null default 0,
  total_products_removed int not null default 0,
  import_notes text,
  created_by uuid,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create table if not exists public.product_change_log (
  id uuid primary key default gen_random_uuid(),
  product_id uuid references public.insurance_products(id) on delete cascade,
  action text not null check (
    action in ('create', 'update', 'delete', 'soft_delete', 'approve', 'reject', 'restore')
  ),
  field_name text,
  old_value text,
  new_value text,
  performed_by uuid,
  performed_at timestamptz not null default now(),
  reason text
);

create index if not exists insurance_companies_category_idx on public.insurance_companies(insurer_category);
create index if not exists insurance_companies_status_idx on public.insurance_companies(status);
create index if not exists insurance_products_company_id_idx on public.insurance_products(company_id);
create index if not exists insurance_products_category_idx on public.insurance_products(product_category);
create index if not exists insurance_products_type_idx on public.insurance_products(product_type);
create index if not exists insurance_products_status_idx on public.insurance_products(current_status);
create index if not exists product_features_product_id_idx on public.product_features(product_id);
create index if not exists product_benefits_product_id_idx on public.product_benefits(product_id);
create index if not exists product_conditions_product_id_idx on public.product_conditions(product_id);
create index if not exists product_riders_addons_product_id_idx on public.product_riders_addons(product_id);
create index if not exists product_claim_performance_product_id_idx on public.product_claim_performance(product_id);
create index if not exists product_ideal_customer_profiles_product_id_idx on public.product_ideal_customer_profiles(product_id);
create index if not exists product_versions_product_id_idx on public.product_versions(product_id);
create index if not exists product_change_log_product_id_idx on public.product_change_log(product_id);

drop trigger if exists set_insurance_companies_updated_at on public.insurance_companies;
create trigger set_insurance_companies_updated_at
before update on public.insurance_companies
for each row execute function public.set_updated_at();

drop trigger if exists set_insurance_products_updated_at on public.insurance_products;
create trigger set_insurance_products_updated_at
before update on public.insurance_products
for each row execute function public.set_updated_at();

drop trigger if exists set_product_features_updated_at on public.product_features;
create trigger set_product_features_updated_at
before update on public.product_features
for each row execute function public.set_updated_at();

drop trigger if exists set_product_benefits_updated_at on public.product_benefits;
create trigger set_product_benefits_updated_at
before update on public.product_benefits
for each row execute function public.set_updated_at();

drop trigger if exists set_product_conditions_updated_at on public.product_conditions;
create trigger set_product_conditions_updated_at
before update on public.product_conditions
for each row execute function public.set_updated_at();

drop trigger if exists set_product_riders_addons_updated_at on public.product_riders_addons;
create trigger set_product_riders_addons_updated_at
before update on public.product_riders_addons
for each row execute function public.set_updated_at();

drop trigger if exists set_product_claim_performance_updated_at on public.product_claim_performance;
create trigger set_product_claim_performance_updated_at
before update on public.product_claim_performance
for each row execute function public.set_updated_at();

drop trigger if exists set_product_ideal_customer_profiles_updated_at on public.product_ideal_customer_profiles;
create trigger set_product_ideal_customer_profiles_updated_at
before update on public.product_ideal_customer_profiles
for each row execute function public.set_updated_at();

alter table public.insurance_companies enable row level security;
alter table public.insurance_products enable row level security;
alter table public.product_features enable row level security;
alter table public.product_benefits enable row level security;
alter table public.product_conditions enable row level security;
alter table public.product_riders_addons enable row level security;
alter table public.product_claim_performance enable row level security;
alter table public.product_ideal_customer_profiles enable row level security;
alter table public.product_versions enable row level security;
alter table public.product_import_batches enable row level security;
alter table public.product_change_log enable row level security;

commit;
