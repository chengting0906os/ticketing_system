-- update_event_stats.sql
-- Trigger function to automatically update event statistics when ticket status changes
--
-- This trigger maintains:
-- 1. event.stats (JSONB) - Event-level statistics (available, reserved, sold, total)
-- 2. subsection_stats table - Subsection-level statistics
--
-- Triggered on: INSERT, UPDATE (status) on ticket table
-- Update strategy: Differential (+/-) updates for performance
--

CREATE OR REPLACE FUNCTION update_event_stats()
RETURNS TRIGGER AS $$
DECLARE
    old_status TEXT;
    new_status TEXT;
    event_id_val INT;
    section_val TEXT;
    subsection_val INT;
BEGIN
    -- Determine event_id, section, subsection, and status based on operation
    IF TG_OP = 'UPDATE' THEN
        event_id_val := NEW.event_id;
        section_val := NEW.section;
        subsection_val := NEW.subsection;
        old_status := OLD.status;
        new_status := NEW.status;
    ELSIF TG_OP = 'INSERT' THEN
        event_id_val := NEW.event_id;
        section_val := NEW.section;
        subsection_val := NEW.subsection;
        old_status := NULL;
        new_status := NEW.status;
    END IF;

    -- Only update if status actually changed (idempotency)
    IF old_status IS DISTINCT FROM new_status THEN
        -- ===== Update event-level stats (differential +/-) =====
        -- Use || operator to merge JSONB objects (much cleaner than nested jsonb_set)
        UPDATE event
        SET stats = COALESCE(stats, '{"available": 0, "reserved": 0, "sold": 0, "total": 0}'::jsonb) || jsonb_build_object(
            'available', COALESCE((stats->>'available')::int, 0)
                + CASE WHEN new_status = 'available' THEN 1 ELSE 0 END
                - CASE WHEN old_status = 'available' THEN 1 ELSE 0 END,
            'reserved', COALESCE((stats->>'reserved')::int, 0)
                + CASE WHEN new_status = 'reserved' THEN 1 ELSE 0 END
                - CASE WHEN old_status = 'reserved' THEN 1 ELSE 0 END,
            'sold', COALESCE((stats->>'sold')::int, 0)
                + CASE WHEN new_status = 'sold' THEN 1 ELSE 0 END
                - CASE WHEN old_status = 'sold' THEN 1 ELSE 0 END,
            'total', COALESCE((stats->>'total')::int, 0)
                + CASE WHEN TG_OP = 'INSERT' THEN 1 ELSE 0 END,  -- INSERT: +1
            'updated_at', EXTRACT(EPOCH FROM NOW())::bigint
        )
        WHERE id = event_id_val;

        -- ===== Update subsection_stats table (UPSERT) =====
        INSERT INTO subsection_stats (event_id, section, subsection, price, available, reserved, sold, updated_at)
        VALUES (
            event_id_val,
            section_val,
            subsection_val,
            COALESCE(NEW.price, OLD.price),  -- Get price from ticket
            CASE WHEN new_status = 'available' THEN 1 ELSE 0 END,
            CASE WHEN new_status = 'reserved' THEN 1 ELSE 0 END,
            CASE WHEN new_status = 'sold' THEN 1 ELSE 0 END,
            EXTRACT(EPOCH FROM NOW())::bigint
        )
        ON CONFLICT (event_id, section, subsection) DO UPDATE
        SET
            available = subsection_stats.available
                + CASE WHEN new_status = 'available' THEN 1 ELSE 0 END
                - CASE WHEN old_status = 'available' THEN 1 ELSE 0 END,
            reserved = subsection_stats.reserved
                + CASE WHEN new_status = 'reserved' THEN 1 ELSE 0 END
                - CASE WHEN old_status = 'reserved' THEN 1 ELSE 0 END,
            sold = subsection_stats.sold
                + CASE WHEN new_status = 'sold' THEN 1 ELSE 0 END
                - CASE WHEN old_status = 'sold' THEN 1 ELSE 0 END,
            updated_at = EXTRACT(EPOCH FROM NOW())::bigint;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger (only for INSERT and UPDATE, not DELETE)
CREATE TRIGGER ticket_status_change_trigger
AFTER INSERT OR UPDATE OF status ON ticket
FOR EACH ROW
EXECUTE FUNCTION update_event_stats();
