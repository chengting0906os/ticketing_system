-- Reserve seats atomically with Check-and-Set pattern
-- Supports two modes: manual (specific seats) and best_available (auto-find consecutive)
--
-- Mode 1: manual - Reserve specific seats
--   ARGV[1]: key_prefix
--   ARGV[2]: event_id
--   ARGV[3]: "manual"
--   ARGV[4..n]: seat data in groups of 5: section, subsection, row, seat, seat_index
--   Returns: array of "seat_id:success" strings
--
-- Mode 2: best_available - Find and reserve consecutive seats
--   ARGV[1]: key_prefix
--   ARGV[2]: event_id
--   ARGV[3]: "best_available"
--   ARGV[4]: section_id (e.g., "A-1")
--   ARGV[5]: quantity (number of consecutive seats needed)
--   ARGV[6]: rows (max number of rows in section)
--   ARGV[7]: seats_per_row
--   Returns: "success:seat_id1,seat_id2,..." or "error:message"

local key_prefix = ARGV[1]
local event_id = ARGV[2]
local mode = ARGV[3]
local AVAILABLE = 0  -- 00 in binary
local RESERVED = 1   -- 01 in binary

-- Mode 1: Manual seat selection
if mode == "manual" then
    local seat_count = (#ARGV - 3) / 5
    local results = {}
    local section_changes = {}

    for i = 0, seat_count - 1 do
        local base_idx = 4 + i * 5
        local section = ARGV[base_idx]
        local subsection = ARGV[base_idx + 1]
        local row = ARGV[base_idx + 2]
        local seat = ARGV[base_idx + 3]
        local seat_index = tonumber(ARGV[base_idx + 4])

        local section_id = section .. '-' .. subsection
        local seat_id = section .. '-' .. subsection .. '-' .. row .. '-' .. seat
        local bf_key = key_prefix .. 'seats_bf:' .. event_id .. ':' .. section_id
        local offset = seat_index * 2

        -- Check current status
        local bit0 = redis.call('GETBIT', bf_key, offset)
        local bit1 = redis.call('GETBIT', bf_key, offset + 1)
        local current_status = bit0 * 2 + bit1

        -- Only reserve if AVAILABLE
        if current_status == AVAILABLE then
            -- Set to RESERVED (01 binary)
            -- offset is bit0 (LSB), offset+1 is bit1 (MSB)
            -- For RESERVED=1: bit0*2 + bit1 = 0*2 + 1 = 1
            redis.call('SETBIT', bf_key, offset, 0)      -- bit0 = 0
            redis.call('SETBIT', bf_key, offset + 1, 1)  -- bit1 = 1
            results[i + 1] = seat_id .. ':1'

            if not section_changes[section_id] then
                section_changes[section_id] = 0
            end
            section_changes[section_id] = section_changes[section_id] + 1
        else
            results[i + 1] = seat_id .. ':0'
        end
    end

    -- Update statistics
    local timestamp = redis.call('TIME')[1]
    for section_id, count in pairs(section_changes) do
        local stats_key = key_prefix .. 'section_stats:' .. event_id .. ':' .. section_id
        redis.call('HINCRBY', stats_key, 'available', -count)
        redis.call('HINCRBY', stats_key, 'reserved', count)
        redis.call('HSET', stats_key, 'updated_at', timestamp)
    end

    return results

-- Mode 2: Best available (find consecutive seats)
elseif mode == "best_available" then
    local section_id = ARGV[4]
    local quantity = tonumber(ARGV[5])
    local rows = tonumber(ARGV[6])
    local seats_per_row = tonumber(ARGV[7])

    local bf_key = key_prefix .. 'seats_bf:' .. event_id .. ':' .. section_id

    -- Parse section_id
    local section_parts = {}
    for part in string.gmatch(section_id, '([^-]+)') do
        table.insert(section_parts, part)
    end
    local section = section_parts[1]
    local subsection = section_parts[2]

    local found_seats = {}
    local found = false

    -- Loop through each row to find consecutive seats
    for row = 1, rows do
        local consecutive_count = 0
        local consecutive_start_seat = 0

        for seat = 1, seats_per_row do
            local seat_index = (row - 1) * seats_per_row + (seat - 1)
            local offset = seat_index * 2

            local bit0 = redis.call('GETBIT', bf_key, offset)
            local bit1 = redis.call('GETBIT', bf_key, offset + 1)
            local current_status = bit0 * 2 + bit1

            if current_status == AVAILABLE then
                if consecutive_count == 0 then
                    consecutive_start_seat = seat
                end
                consecutive_count = consecutive_count + 1

                if consecutive_count == quantity then
                    -- Found! Reserve them atomically
                    for i = 0, quantity - 1 do
                        local reserve_seat = consecutive_start_seat + i
                        local reserve_index = (row - 1) * seats_per_row + (reserve_seat - 1)
                        local reserve_offset = reserve_index * 2

                        -- Set to RESERVED (01 binary): bit0=0, bit1=1
                        redis.call('SETBIT', bf_key, reserve_offset, 0)
                        redis.call('SETBIT', bf_key, reserve_offset + 1, 1)

                        local seat_id = section .. '-' .. subsection .. '-' .. row .. '-' .. reserve_seat
                        table.insert(found_seats, seat_id)
                    end

                    found = true
                    break
                end
            else
                consecutive_count = 0
                consecutive_start_seat = 0
            end
        end

        if found then
            break
        end
    end

    if found then
        -- Update statistics
        local timestamp = redis.call('TIME')[1]
        local stats_key = key_prefix .. 'section_stats:' .. event_id .. ':' .. section_id
        redis.call('HINCRBY', stats_key, 'available', -quantity)
        redis.call('HINCRBY', stats_key, 'reserved', quantity)
        redis.call('HSET', stats_key, 'updated_at', timestamp)

        return 'success:' .. table.concat(found_seats, ',')
    else
        return 'error:No consecutive seats available'
    end
else
    return 'error:Invalid mode'
end
