-- Minimal schema for moderation audit events.
-- Apply once on the remote Postgres used by the project.

create table if not exists moderation_events (
    id bigserial primary key,
    created_at timestamptz not null default now(),
    request_id text not null unique,
    user_id bigint not null,
    action text not null,
    field text not null,
    text_raw text not null,
    text_norm text not null,
    decision text not null,
    categories jsonb not null default '[]'::jsonb,
    reason_short text,
    policy_version text not null,
    prompt_version text not null,
    model text not null
);

create index if not exists idx_moderation_events_created_at on moderation_events (created_at desc);
create index if not exists idx_moderation_events_user_created_at on moderation_events (user_id, created_at desc);
create index if not exists idx_moderation_events_decision_created_at on moderation_events (decision, created_at desc);

