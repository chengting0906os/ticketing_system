-- Init script for ticketing_system_db
-- This script runs when the PostgreSQL container is first created

-- Set timezone
SET timezone = 'UTC';

-- =============================================================================
-- Create Test Databases for pytest
-- =============================================================================

-- Main test database
CREATE DATABASE ticketing_system_test_db;

-- Test databases for parallel pytest-xdist workers (gw0-gw7)
CREATE DATABASE ticketing_system_test_db_gw0;
CREATE DATABASE ticketing_system_test_db_gw1;
CREATE DATABASE ticketing_system_test_db_gw2;
CREATE DATABASE ticketing_system_test_db_gw3;
CREATE DATABASE ticketing_system_test_db_gw4;
CREATE DATABASE ticketing_system_test_db_gw5;
CREATE DATABASE ticketing_system_test_db_gw6;
CREATE DATABASE ticketing_system_test_db_gw7;

-- =============================================================================
-- Setup Extensions for All Databases
-- =============================================================================

-- Main database
\c ticketing_system_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Test databases
\c ticketing_system_test_db;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\c ticketing_system_test_db_gw0;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\c ticketing_system_test_db_gw1;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\c ticketing_system_test_db_gw2;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\c ticketing_system_test_db_gw3;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\c ticketing_system_test_db_gw4;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\c ticketing_system_test_db_gw5;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\c ticketing_system_test_db_gw6;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\c ticketing_system_test_db_gw7;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- Log Completion
-- =============================================================================

\c ticketing_system_db;
DO $$
BEGIN
    RAISE NOTICE '✅ Database initialization complete';
    RAISE NOTICE '📦 Created databases:';
    RAISE NOTICE '   - ticketing_system_db (main)';
    RAISE NOTICE '   - ticketing_system_test_db (test)';
    RAISE NOTICE '   - ticketing_system_test_db_gw0-gw7 (parallel test workers)';
END $$;