-- Run this in the Supabase SQL Editor

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    role text not null check (role in ('investor', 'developer')),
    username text unique not null,
    password_hash text not null,
    email text unique not null,
    phone text,
    created_at timestamptz default now()
);

-- Investor "Deal Criteria": sector + amount you invest
create table if not exists deal_criteria (
    id uuid primary key default gen_random_uuid(),
    investor_id uuid not null references users(id) on delete cascade,
    sector text not null,
    min_amount numeric,
    max_amount numeric,
    created_at timestamptz default now()
);

-- Developer "Pitch your idea"
create table if not exists pitches (
    id uuid primary key default gen_random_uuid(),
    developer_id uuid not null references users(id) on delete cascade,
    title text not null,
    category text not null,
    problem text not null,
    solution text not null,
    fund_ask numeric not null,
    equity_offered numeric not null,
    creation_link text,           -- optional
    created_at timestamptz default now()
);

-- Messages between investors and developers
create table if not exists messages (
    id uuid primary key default gen_random_uuid(),
    sender_id uuid not null references users(id) on delete cascade,
    receiver_id uuid not null references users(id) on delete cascade,
    pitch_id uuid references pitches(id) on delete set null,
    body text not null,
    created_at timestamptz default now()
);
