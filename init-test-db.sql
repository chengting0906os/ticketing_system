-- Init script for ticketing_system_db
-- This script runs when the PostgreSQL container is first created

-- Create schema if needed (optional, uncomment if you use a specific schema)
-- CREATE SCHEMA IF NOT EXISTS ticketing;

-- Set timezone (optional)
SET timezone = 'UTC';

-- Create extension for UUID generation if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- You can add initial table creation here if needed
-- For example:
-- CREATE TABLE IF NOT EXISTS events (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     name VARCHAR(255) NOT NULL,
--     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
-- );

-- Add any seed data or initial configuration
-- INSERT INTO ... VALUES ...;

-- Grant permissions if needed
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO py_arch_lab;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO py_arch_lab;

-- Log that initialization is complete
DO $$
BEGIN
    RAISE NOTICE 'Database initialization complete';
END $$;