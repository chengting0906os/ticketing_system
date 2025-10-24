-- ============================================================================
-- ScyllaDB Schema Design for Ticketing System
-- ============================================================================
-- Design Principles:
-- 1. Denormalization for read performance (ScyllaDB is optimized for reads)
-- 2. Partition keys based on access patterns (avoid hot partitions)
-- 3. Clustering keys for natural ordering and range queries
-- 4. TTL for temporary data (reserved tickets expire after 10 minutes)
-- 5. Materialized views / Secondary indexes only when absolutely necessary
-- ============================================================================

-- Create keyspace (run once)
-- Note: Using replication_factor=2 for development (requires at least 2 nodes)
-- Note: Tablets disabled to enable LWT (Lightweight Transactions) support for atomic operations
CREATE KEYSPACE IF NOT EXISTS ticketing_system
    WITH REPLICATION = {
        'class': 'NetworkTopologyStrategy',
        'datacenter1': 2  -- 2 replicas (can scale to 3 in production)
    } AND TABLETS = {'enabled': false};

USE ticketing_system;

-- ============================================================================
-- USER TABLE
-- ============================================================================
-- Access patterns:
-- 1. Get user by ID (primary key lookup) - fastest
-- 2. Get user by email (secondary index) - login scenario
-- 3. List users by role (scan - admin only, infrequent)
-- ============================================================================

CREATE TABLE IF NOT EXISTS "user" (
    id BIGINT,
    email TEXT,
    hashed_password TEXT,
    name TEXT,
    role TEXT,  -- 'buyer' | 'seller' | 'admin'
    created_at TIMESTAMP,
    is_active BOOLEAN,
    is_superuser BOOLEAN,
    is_verified BOOLEAN,
    PRIMARY KEY (id)
);

-- Secondary index for email lookup (login)
CREATE INDEX IF NOT EXISTS users_email_idx ON "user" (email);

-- ============================================================================
-- EVENT TABLE
-- ============================================================================
-- Access patterns:
-- 1. Get event by ID (primary key lookup)
-- 2. List events by seller_id (denormalized - avoid JOIN)
-- 3. List active events (filtering by status)
-- ============================================================================

CREATE TABLE IF NOT EXISTS "event" (
    id BIGINT,
    name TEXT,
    description TEXT,
    seller_id BIGINT,
    seller_name TEXT,  -- Denormalized for display
    is_active BOOLEAN,
    status TEXT,  -- 'available' | 'sold_out' | 'cancelled'
    venue_name TEXT,
    seating_config TEXT,  -- JSON string (ScyllaDB doesn't have native JSON type)
    PRIMARY KEY (id)
);

-- Secondary index for seller queries
CREATE INDEX IF NOT EXISTS events_seller_id_idx ON "event" (seller_id);

-- ============================================================================
-- BOOKING TABLE
-- ============================================================================
-- Access patterns:
-- 1. Get booking by ID (primary key lookup)
-- 2. List bookings by buyer_id (partition by buyer_id for efficiency)
-- 3. List bookings by event_id (for seller view)
-- 4. Filter by status (processing, pending_payment, completed, cancelled, failed)
--
-- Strategy: Use buyer_id as partition key, id as clustering key
-- This optimizes for the most common query (user viewing their bookings)
-- ============================================================================

CREATE TABLE IF NOT EXISTS "booking" (
    id BIGINT,
    buyer_id BIGINT,
    event_id BIGINT,
    section TEXT,
    subsection INT,
    seat_positions LIST<TEXT>,  -- ['1-1', '1-2', '1-3'] (row-seat pairs)
    quantity INT,
    total_price BIGINT,
    status TEXT,  -- 'processing' | 'pending_payment' | 'completed' | 'cancelled' | 'failed'
    seat_selection_mode TEXT,  -- 'manual' | 'auto'
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    paid_at TIMESTAMP,
    -- Denormalized fields for display (avoid JOINs)
    buyer_name TEXT,
    buyer_email TEXT,
    event_name TEXT,
    venue_name TEXT,
    seller_id BIGINT,  -- Denormalized for seller queries (avoid N+1)
    seller_name TEXT,
    -- Denormalized ticket details (avoid separate ticket queries)
    tickets_data LIST<FROZEN<MAP<TEXT, TEXT>>>,  -- [{'id': '123', 'row': '1', 'seat': '1', 'price': '1000', 'status': 'sold'}, ...]
    PRIMARY KEY (id)
);

-- Index for buyer queries (list my bookings)
CREATE INDEX IF NOT EXISTS bookings_buyer_id_idx ON "booking" (buyer_id);

-- Index for event queries (seller view)
CREATE INDEX IF NOT EXISTS bookings_event_id_idx ON "booking" (event_id);

-- Index for seller queries (CRITICAL: eliminates N+1 query problem)
CREATE INDEX IF NOT EXISTS bookings_seller_id_idx ON "booking" (seller_id);

-- ============================================================================
-- TICKET TABLE
-- ============================================================================
-- Access patterns:
-- 1. Get tickets by event_id (list all tickets for an event)
-- 2. Get tickets by (event_id, section, subsection) - section view
-- 3. Get ticket by unique seat (event_id, section, subsection, row_number, seat_number)
-- 4. Get tickets by buyer_id (my tickets)
-- 5. Reserve/Release tickets atomically (BATCH with LWT)
--
-- Strategy: Partition by (event_id, section, subsection) for locality
-- Clustering by (row_number, seat_number) for natural ordering
-- ============================================================================

CREATE TABLE IF NOT EXISTS "ticket" (
    event_id BIGINT,
    section TEXT,
    subsection INT,
    row_number INT,
    seat_number INT,
    id BIGINT,  -- Global unique ID
    price BIGINT,
    status TEXT,  -- 'available' | 'reserved' | 'sold'
    buyer_id BIGINT,
    reserved_at TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY ((event_id, section, subsection), row_number, seat_number)
) WITH CLUSTERING ORDER BY (row_number ASC, seat_number ASC);

-- Index for buyer queries (my tickets)
CREATE INDEX IF NOT EXISTS tickets_buyer_id_idx ON "ticket" (buyer_id);

-- ============================================================================
-- MATERIALIZED VIEW: tickets_by_buyer
-- ============================================================================
-- Optimized view for "Get all my tickets" query
-- Denormalized with event info for display
-- ============================================================================

CREATE MATERIALIZED VIEW IF NOT EXISTS tickets_by_buyer AS
    SELECT *
    FROM "ticket"
    WHERE buyer_id IS NOT NULL
      AND event_id IS NOT NULL
      AND section IS NOT NULL
      AND subsection IS NOT NULL
      AND row_number IS NOT NULL
      AND seat_number IS NOT NULL
    PRIMARY KEY (buyer_id, event_id, section, subsection, row_number, seat_number)
    WITH CLUSTERING ORDER BY (event_id ASC, section ASC, subsection ASC, row_number ASC, seat_number ASC);
