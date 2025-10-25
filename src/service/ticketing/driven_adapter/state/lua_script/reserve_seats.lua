-- Reserve seats atomically with Check-and-Set pattern + Idempotency
-- Supports two modes: manual (specific seats) and best_available (auto-find consecutive)
--
-- Mode 1: manual - Reserve specific seats
--   ARGV[1]: key_prefix
--   ARGV[2]: event_id
--   ARGV[3]: booking_id (for idempotency)
--   ARGV[4]: "manual"
--   ARGV[5..n]: seat data in groups of 5: section, subsection, row, seat, seat_index
--   Returns: array of "seat_id:success" strings or cached result
--
-- Mode 2: best_available - Find and reserve consecutive seats
--   ARGV[1]: key_prefix
--   ARGV[2]: event_id
--   ARGV[3]: booking_id (for idempotency)
--   ARGV[4]: "best_available"
--   ARGV[5]: section_id (e.g., "A-1")
--   ARGV[6]: quantity (number of consecutive seats needed)
--   ARGV[7]: rows (max number of rows in section)
--   ARGV[8]: seats_per_row
--   Returns: "success:seat_id1,seat_id2,..." or "error:message" or cached result

local key_prefix = ARGV[1]
local event_id = ARGV[2]
local booking_id = ARGV[3]
local mode = ARGV[4]
local AVAILABLE = 0  -- 00 in binary
local RESERVED = 1   -- 01 in binary

-- 🔍 Build section-aware idempotency key
local section_id
if mode == "manual" then
    -- Extract section_id from first seat (ARGV[5] = section, ARGV[6] = subsection)
    local section = ARGV[5]
    local subsection = ARGV[6]
    section_id = section .. '-' .. subsection
elseif mode == "best_available" then
    -- section_id is directly provided in ARGV[5]
    section_id = ARGV[5]
end

local idempotency_key = key_prefix .. 'processed_booking:' .. booking_id .. ':' .. section_id
local cached_result = redis.call('GET', idempotency_key)

if cached_result then
    -- 📦 Return cached result (already processed)
    local cached_data = cjson.decode(cached_result)

    if mode == "manual" then
        -- Return array format for manual mode
        return cached_data.result
    else
        -- Return string format for best_available mode
        return cached_data.result
    end
end

-- 🎯 First time processing - continue with normal logic

-- Mode 1: Manual seat selection
if mode == "manual" then
    local seat_count = (#ARGV - 4) / 5  -- 🔧 調整索引 (新增了 booking_id)
    local results = {}
    local section_changes = {}

    for i = 0, seat_count - 1 do
        local base_idx = 5 + i * 5  -- 🔧 調整索引 (從 4 改為 5)
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

    -- 💾 Cache result for idempotency (TTL: 7 days = 604800 seconds, adjust per event duration in production)
    local cache_data = {
        result = results,
        timestamp = timestamp,
        mode = "manual"
    }
    redis.call('SETEX', idempotency_key, 604800, cjson.encode(cache_data))

    return results

-- Mode 2: Best available (find consecutive seats)
elseif mode == "best_available" then
    local section_id = ARGV[5]  -- 🔧 調整索引 (從 4 改為 5)
    local quantity = tonumber(ARGV[6])  -- 🔧 調整索引 (從 5 改為 6)
    local rows = tonumber(ARGV[7])  -- 🔧 調整索引 (從 6 改為 7)
    local seats_per_row = tonumber(ARGV[8])  -- 🔧 調整索引 (從 7 改為 8)

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

        local success_result = 'success:' .. table.concat(found_seats, ',')

        -- 💾 Cache successful result for idempotency (TTL: 7 days = 604800 seconds)
        local cache_data = {
            result = success_result,
            timestamp = timestamp,
            mode = "best_available"
        }
        redis.call('SETEX', idempotency_key, 604800, cjson.encode(cache_data))

        return success_result
    else
        local error_result = 'error:No consecutive seats available'

        -- 💾 Cache failed result for idempotency (TTL: 7 days = 604800 seconds, seat scarcity is stable during event period)
        local cache_data = {
            result = error_result,
            timestamp = redis.call('TIME')[1],
            mode = "best_available"
        }
        redis.call('SETEX', idempotency_key, 604800, cjson.encode(cache_data))

        return error_result
    end
else
    return 'error:Invalid mode'
end
