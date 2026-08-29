-- Extra logical databases for the co-located services.
-- The app DB itself is created by POSTGRES_DB.
CREATE DATABASE langfuse;
CREATE DATABASE bifrost;
CREATE DATABASE mcpgw;

-- Keycloak stores its tables in a dedicated schema inside the app DB.
\connect returnguard
CREATE SCHEMA IF NOT EXISTS keycloak;

-- Useful extensions on the app DB (pgvector deliberately NOT used — Qdrant is the vector store).
\connect returnguard
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
