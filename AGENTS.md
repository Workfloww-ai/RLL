# Project Guidelines & Agent Instructions

This repository contains an enterprise-grade full-stack sales analytics platform for **Rajasthan Liquor Limited (RLL)**, structured into three primary sub-systems:
1. **Backend (`backend/`)**: FastAPI, Pydantic, Supabase PostgreSQL, and ETL processing pipelines.
2. **Web Frontend (`Web/`)**: React, Vite, TypeScript, and Tailwind CSS web application.
3. **Mobile Application (`mobile/`)**: React-based mobile application interface.

All coding agents operating on this repository must strictly adhere to the following architectural, security, and directory organization rules.

---

## 1. Environment & Configuration Security
* **No `.env` File Reading or Writing:** Do not attempt to read, write, edit, or modify `.env` or configuration credential files.
* **No Hardcoded Secrets:** Never hardcode API keys, service role keys, JWT secrets, or connection strings in source code. Always consume configuration through standard environment variables or backend settings modules (`backend/core/config.py`).

---

## 2. Enterprise-Grade Architecture & Quality
* **Scalable & Modular Standards:** Build performant, modular solutions following enterprise design patterns.
* **Strict Separation of Concerns:**
  - **Routers (`backend/api/v1/`)**: Handle HTTP request/response parsing, parameter extraction, and status codes only.
  - **Service Layer (`backend/services/`)**: Encapsulate all business logic, data processing, and workflow orchestration.
  - **Database Layer (`backend/db/`)**: Manage database connections, SQL queries, and RPC procedure calls.
* **Type Safety & Data Models:** Use strict Pydantic models on the backend (`backend/models/`) and TypeScript interfaces on the web (`Web/src/types.ts`) and mobile apps (`mobile/src/types.ts`).

---

## 3. Database Queries & Supabase Security
* **Explicit Columns Only (No `SELECT *`):** Never execute wildcard `SELECT *` database queries. Always explicitly specify required column names (e.g., `client.table("depots").select("depot_id, depot_name")`) to minimize memory usage, prevent over-fetching, and ensure schema safety.
* **Strict Backend API Routing:** **Do not invoke Supabase directly from Frontend (`Web/`) or Mobile (`mobile/`) apps.** All database interactions must be securely routed through backend API endpoints under `/api/v1/`.

---

## 4. Backend Architecture (`backend/`)
* **Dedicated Database Access Layer (`backend/db/`)**: All raw database queries, RPC invocations, and table helpers must reside inside dedicated files under `backend/db/` (e.g., `backend/db/supabase_client.py`).
* **Service Layer Decoupling (`backend/services/`)**: Business services (e.g., `analytics_service.py`, `import_pipeline.py`, `master_service.py`) must consume database methods via `backend/db/` and remain decoupled from direct low-level queries.
* **Domain Model Definitions (`backend/models/`)**: Keep data models and validation Pydantic classes cleanly separated into modular domain files (`analytics.py`, `master.py`, `transactional.py`, `user.py`).

---

## 5. Web Frontend Guidelines (`Web/`)
* **Single-File Component Packaging:** Keep page-level and component logic consolidated within a single clean file (e.g., `Web/src/pages/TerritoryManagement.tsx` or `Web/src/features/signup/SignupPage.tsx`) instead of splitting tightly coupled UI elements across multiple files unnecessarily.
* **Feature Directory Organization:** Group new web features into dedicated feature directories under `Web/src/features/<featurename>/` or `Web/src/pages/` instead of overcrowding root application folders.

---

## 6. Mobile Application Guidelines (`mobile/`)
* **Feature-Based Directory Structure:** Structure new mobile screens and features inside dedicated directories under `mobile/src/features/<featurename>/` (e.g., `mobile/src/features/dashboard/`).
* **Single-File Screen Components:** Keep screen components self-contained per feature module to reduce file fragmentation and improve maintainability.
* **Backend API Integration:** Mobile applications must interact exclusively with backend REST APIs (`/api/v1/mobile/...`) using authentication tokens.
