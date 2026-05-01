-- Phase 1: Document Registry + Chunk Metadata foundation
-- Safe to run on existing projects with legacy columns.

begin;

create extension if not exists pgcrypto;
create extension if not exists vector;

-- -----------------------------
-- documents table (registry)
-- -----------------------------
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  file_name text not null,
  source_type text not null default 'pdf',
  source_group text,
  domain text,
  version integer not null default 1,
  file_hash text,
  status text not null default 'uploaded',
  total_pages integer not null default 0,
  total_chunks integer not null default 0,
  uploaded_at timestamptz not null default now(),
  processed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  summary text
);

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'documents' and column_name = 'filename'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'documents' and column_name = 'file_name'
  ) then
    alter table public.documents rename column filename to file_name;
  end if;
end $$;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'documents' and column_name = 'page_count'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'documents' and column_name = 'total_pages'
  ) then
    alter table public.documents rename column page_count to total_pages;
  end if;
end $$;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'documents' and column_name = 'chunk_count'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'documents' and column_name = 'total_chunks'
  ) then
    alter table public.documents rename column chunk_count to total_chunks;
  end if;
end $$;

alter table public.documents add column if not exists source_type text;
alter table public.documents add column if not exists source_group text;
alter table public.documents add column if not exists domain text;
alter table public.documents add column if not exists version integer;
alter table public.documents add column if not exists file_hash text;
alter table public.documents add column if not exists status text;
alter table public.documents add column if not exists total_pages integer;
alter table public.documents add column if not exists total_chunks integer;
alter table public.documents add column if not exists uploaded_at timestamptz;
alter table public.documents add column if not exists processed_at timestamptz;
alter table public.documents add column if not exists metadata jsonb;
alter table public.documents add column if not exists summary text;

-- Backfill defaults for legacy rows
update public.documents set source_type = coalesce(source_type, 'pdf');
update public.documents set version = coalesce(version, 1);
update public.documents set status = coalesce(status, 'uploaded');
update public.documents set total_pages = coalesce(total_pages, 0);
update public.documents set total_chunks = coalesce(total_chunks, 0);
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'documents' and column_name = 'created_at'
  ) then
    execute 'update public.documents set uploaded_at = coalesce(uploaded_at, created_at, now())';
  else
    update public.documents set uploaded_at = coalesce(uploaded_at, now());
  end if;
end $$;
update public.documents set metadata = coalesce(metadata, '{}'::jsonb);

alter table public.documents alter column source_type set default 'pdf';
alter table public.documents alter column source_type set not null;
alter table public.documents alter column version set default 1;
alter table public.documents alter column version set not null;
alter table public.documents alter column status set default 'uploaded';
alter table public.documents alter column status set not null;
alter table public.documents alter column total_pages set default 0;
alter table public.documents alter column total_pages set not null;
alter table public.documents alter column total_chunks set default 0;
alter table public.documents alter column total_chunks set not null;
alter table public.documents alter column uploaded_at set default now();
alter table public.documents alter column uploaded_at set not null;
alter table public.documents alter column metadata set default '{}'::jsonb;
alter table public.documents alter column metadata set not null;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'documents_status_allowed_chk'
  ) then
    alter table public.documents
      add constraint documents_status_allowed_chk
      check (
        status in (
          'uploaded',
          'processing',
          'processed',
          'processed_with_warnings',
          'failed_extraction',
          'needs_ocr',
          'embedding_pending',
          'embedding_failed'
        )
      );
  end if;
end $$;

create unique index if not exists documents_file_hash_version_uniq
  on public.documents (file_hash, version)
  where file_hash is not null;

create index if not exists documents_source_group_idx on public.documents (source_group);
create index if not exists documents_status_idx on public.documents (status);

-- -----------------------------
-- document_chunks table
-- -----------------------------
create table if not exists public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  chunk_index integer not null,
  page_start integer,
  page_end integer,
  section_title text,
  chunk_text text not null,
  token_count integer,
  chunk_type text,
  embedding vector(384),
  embedding_model text,
  embedding_dimension integer,
  embedded_at timestamptz,
  search_vector tsvector,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'document_chunks' and column_name = 'page_number'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'document_chunks' and column_name = 'page_start'
  ) then
    alter table public.document_chunks rename column page_number to page_start;
  end if;
end $$;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'document_chunks' and column_name = 'content'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public' and table_name = 'document_chunks' and column_name = 'chunk_text'
  ) then
    alter table public.document_chunks rename column content to chunk_text;
  end if;
end $$;

alter table public.document_chunks add column if not exists chunk_index integer;
alter table public.document_chunks add column if not exists page_start integer;
alter table public.document_chunks add column if not exists page_end integer;
alter table public.document_chunks add column if not exists section_title text;
alter table public.document_chunks add column if not exists chunk_text text;
alter table public.document_chunks add column if not exists token_count integer;
alter table public.document_chunks add column if not exists chunk_type text;
alter table public.document_chunks add column if not exists embedding_model text;
alter table public.document_chunks add column if not exists embedding_dimension integer;
alter table public.document_chunks add column if not exists embedded_at timestamptz;
alter table public.document_chunks add column if not exists search_vector tsvector;
alter table public.document_chunks add column if not exists metadata jsonb;
alter table public.document_chunks add column if not exists created_at timestamptz;

update public.document_chunks set metadata = coalesce(metadata, '{}'::jsonb);
update public.document_chunks set created_at = coalesce(created_at, now());
update public.document_chunks set chunk_type = coalesce(chunk_type, 'body');
update public.document_chunks set page_end = coalesce(page_end, page_start);
update public.document_chunks set embedding_dimension = coalesce(embedding_dimension, 384) where embedding is not null;

with ranked as (
  select id, row_number() over (partition by document_id order by created_at, id) - 1 as rn
  from public.document_chunks
)
update public.document_chunks dc
set chunk_index = ranked.rn
from ranked
where dc.id = ranked.id and dc.chunk_index is null;

alter table public.document_chunks alter column chunk_index set not null;
alter table public.document_chunks alter column chunk_text set not null;
alter table public.document_chunks alter column metadata set default '{}'::jsonb;
alter table public.document_chunks alter column metadata set not null;
alter table public.document_chunks alter column created_at set default now();
alter table public.document_chunks alter column created_at set not null;

-- Text search maintenance trigger
create or replace function public.document_chunks_search_vector_trigger()
returns trigger
language plpgsql
as $$
begin
  new.search_vector := to_tsvector('english', coalesce(new.chunk_text, ''));
  return new;
end;
$$;

drop trigger if exists trg_document_chunks_search_vector on public.document_chunks;
create trigger trg_document_chunks_search_vector
before insert or update of chunk_text
on public.document_chunks
for each row
execute function public.document_chunks_search_vector_trigger();

update public.document_chunks
set search_vector = to_tsvector('english', coalesce(chunk_text, ''))
where search_vector is null;

create index if not exists document_chunks_document_id_idx on public.document_chunks (document_id);
create index if not exists document_chunks_embedded_at_idx on public.document_chunks (embedded_at);
create index if not exists document_chunks_search_vector_idx on public.document_chunks using gin (search_vector);
create index if not exists document_chunks_embedding_ivfflat_idx
  on public.document_chunks using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

-- -----------------------------
-- Retrieval RPCs (Phase 4/5)
-- -----------------------------
create or replace function public.match_document_chunks(
  query_embedding vector(384),
  match_count integer default 15,
  similarity_threshold double precision default 0.65,
  source_group_filter text default null,
  document_id_filter uuid default null
)
returns table (
  chunk_id uuid,
  document_id uuid,
  document_title text,
  source_group text,
  section_title text,
  page_start integer,
  page_end integer,
  chunk_text text,
  similarity double precision,
  metadata jsonb
)
language sql
stable
as $$
  select
    dc.id as chunk_id,
    d.id as document_id,
    d.title as document_title,
    d.source_group,
    dc.section_title,
    dc.page_start,
    dc.page_end,
    dc.chunk_text,
    (1 - (dc.embedding <=> query_embedding))::double precision as similarity,
    dc.metadata
  from public.document_chunks dc
  join public.documents d on d.id = dc.document_id
  where dc.embedding is not null
    and (source_group_filter is null or d.source_group = source_group_filter)
    and (document_id_filter is null or d.id = document_id_filter)
    and (1 - (dc.embedding <=> query_embedding)) >= similarity_threshold
  order by dc.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function public.keyword_match_document_chunks(
  query_text text,
  match_count integer default 15,
  source_group_filter text default null,
  document_id_filter uuid default null
)
returns table (
  chunk_id uuid,
  document_id uuid,
  document_title text,
  source_group text,
  section_title text,
  page_start integer,
  page_end integer,
  chunk_text text,
  keyword_score double precision,
  metadata jsonb
)
language sql
stable
as $$
  select
    dc.id as chunk_id,
    d.id as document_id,
    d.title as document_title,
    d.source_group,
    dc.section_title,
    dc.page_start,
    dc.page_end,
    dc.chunk_text,
    ts_rank(dc.search_vector, plainto_tsquery('english', query_text))::double precision as keyword_score,
    dc.metadata
  from public.document_chunks dc
  join public.documents d on d.id = dc.document_id
  where dc.search_vector @@ plainto_tsquery('english', query_text)
    and (source_group_filter is null or d.source_group = source_group_filter)
    and (document_id_filter is null or d.id = document_id_filter)
  order by keyword_score desc
  limit match_count;
$$;

commit;
