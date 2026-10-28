SELECT 'CREATE DATABASE narrative_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'narrative_test')
\gexec