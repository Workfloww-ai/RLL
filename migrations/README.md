# Database Migrations

This folder contains all SQL database migration scripts for the RLL application.

## Migration Files

1. [`000_full_schema_recovery_uuid.sql`](file:///Users/monalikagoel/Documents/RLL/RLL/migrations/000_full_schema_recovery_uuid.sql)
   - Complete database schema definition using UUID primary keys, default tables, partition tables, and daily/monthly refresh stored procedures.

2. [`002_roles_and_user_hierarchy_uuid.sql`](file:///Users/monalikagoel/Documents/RLL/RLL/migrations/002_roles_and_user_hierarchy_uuid.sql)
   - Role & user hierarchy mapping migration, converting role IDs to UUIDs and seeding standard system roles (`Leader`, `TSM`, `ASE`, `Admin`).

3. [`003_rls_policies.sql`](file:///Users/monalikagoel/Documents/RLL/RLL/migrations/003_rls_policies.sql)
   - Enables Row Level Security (RLS) across all public tables and defines read/write security policies for authenticated users and system services.

## How to Apply Migrations

### Option A: Supabase SQL Editor
1. Log into your Supabase Dashboard project.
2. Go to **SQL Editor**.
3. Execute the SQL scripts in numeric sequence (`000` -> `002` -> `003`).

### Option B: Supabase CLI
```bash
supabase db push
```
