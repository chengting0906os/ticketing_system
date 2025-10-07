-- Initialize seats atomically in Kvrocks
-- This script creates seat bitfields, metadata, section stats, and configurations in a single atomic operation
--
-- ARGV[1]: key_prefix (for test isolation)
-- ARGV[2]: event_id
-- ARGV[3..n]: seat data in groups of 6: section, subsection, row, seat_num, seat_index, price
--
-- Returns: number of successfully initialized seats

local key_prefix = ARGV[1]
local event_id = ARGV[2]
local timestamp = redis.call('TIME')[1]

local seat_count = (#ARGV - 2) / 6
local success_count = 0
local section_stats = {}
local section_configs = {}

-- Initialize all seats
for i = 0, seat_count - 1 do
    local base_idx = 3 + i * 6
    local section, subsection, row, seat_num, seat_index, price =
        ARGV[base_idx],
        ARGV[base_idx + 1],
        ARGV[base_idx + 2],
        ARGV[base_idx + 3],
        ARGV[base_idx + 4],
        ARGV[base_idx + 5]

    local section_id = section .. '-' .. subsection
    local bf_key = key_prefix .. 'seats_bf:' .. event_id .. ':' .. section_id
    local meta_key = key_prefix .. 'seat_meta:' .. event_id .. ':' .. section_id .. ':' .. row
    local offset = tonumber(seat_index) * 2

    -- Set seat status bits to 00 (available)
    redis.call('SETBIT', bf_key, offset, 0)
    redis.call('SETBIT', bf_key, offset + 1, 0)

    -- Store seat metadata (price)
    redis.call('HSET', meta_key, seat_num, price)

    -- Accumulate section statistics
    section_stats[section_id] = (section_stats[section_id] or 0) + 1

    -- Track section configuration (rows and seats_per_row)
    if not section_configs[section_id] then
        section_configs[section_id] = {
            max_row = tonumber(row),
            seats_per_row = tonumber(seat_num)
        }
    else
        section_configs[section_id].max_row = math.max(
            section_configs[section_id].max_row,
            tonumber(row)
        )
        section_configs[section_id].seats_per_row = math.max(
            section_configs[section_id].seats_per_row,
            tonumber(seat_num)
        )
    end

    success_count = success_count + 1
end

-- Create section indexes and statistics
for section_id, count in pairs(section_stats) do
    -- Add section to event's section index
    redis.call('ZADD', key_prefix .. 'event_sections:' .. event_id, 0, section_id)

    -- Initialize section statistics
    redis.call('HSET',
        key_prefix .. 'section_stats:' .. event_id .. ':' .. section_id,
        'section_id', section_id,
        'event_id', event_id,
        'available', count,
        'reserved', 0,
        'sold', 0,
        'total', count,
        'updated_at', timestamp
    )

    -- Store section configuration
    local config = section_configs[section_id]
    redis.call('HSET',
        key_prefix .. 'section_config:' .. event_id .. ':' .. section_id,
        'rows', config.max_row,
        'seats_per_row', config.seats_per_row
    )
end

return success_count
