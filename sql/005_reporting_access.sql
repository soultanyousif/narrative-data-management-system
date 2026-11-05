SELECT format('CREATE ROLE metabase_reader LOGIN PASSWORD %L', :'reader_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'metabase_reader')
\gexec

SELECT format('ALTER ROLE metabase_reader PASSWORD %L', :'reader_password')
\gexec

GRANT CONNECT ON DATABASE narrative_dw TO metabase_reader;
GRANT USAGE ON SCHEMA reporting TO metabase_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO metabase_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA reporting GRANT SELECT ON TABLES TO metabase_reader;
REVOKE ALL ON SCHEMA core FROM metabase_reader;
REVOKE ALL ON SCHEMA staging FROM metabase_reader;