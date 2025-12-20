---@diagnostic disable: undefined-global, deprecated
--[[
Find and Reserve Consecutive Available Seats (Atomic Lua Script)

This script combines find + reserve in a single atomic operation to prevent race conditions.
Without atomicity, concurrent requests could find the same "available" seats before any
reservation is written, leading to double-booking.

Strategy:
1. Priority 1: Find N consecutive available seats (best user experience)
2. Priority 2: If no consecutive seats, use LARGEST consecutive blocks (smart fallback)
3. Fail: If not enough available seats at all
4. Reserve: Immediately mark found seats as RESERVED (atomic with find)

Performance Optimization:
- BITFIELD batch read: Read entire row in 1 command (1 BITFIELD vs. cols × 2 GETBIT)
- For 500-seat subsection (25 rows × 20 seats): 25 BITFIELD commands vs 500+ GETBIT calls

Interface:
  KEYS[1]: Bitfield key (e.g., 'seats_bf:123:A-1')
  ARGV[1]: rows (number of rows)
  ARGV[2]: cols (seats per row)
  ARGV[3]: quantity (number of seats needed)

Returns:
- Success: JSON object with seats: {"seats": [[row, seat_num, seat_index], ...], "rows": 25, "cols": 20}
- Failure: nil (not enough available seats)
--]]

-- Redis-provided globals: redis, cjson, KEYS, ARGV
local bf_key = KEYS[1]
local rows = tonumber(ARGV[1])
local cols = tonumber(ARGV[2])
local quantity = tonumber(ARGV[3])

-- Validate: Maximum 4 tickets per booking
local MAX_TICKETS = 4
if quantity > MAX_TICKETS then
    return redis.error_reply('INVALID_QUANTITY: Maximum ' .. MAX_TICKETS .. ' tickets allowed')
end

-- Helper: Calculate seat index
local function calculate_seat_index(row, seat_num, spr)
    return (row - 1) * spr + (seat_num - 1)
end

-- Helper: Reserve seats atomically (mark as RESERVED = 1)
local function reserve_seats(seats)
    for _, seat in ipairs(seats) do
        local seat_index = seat[3] -- third element is seat_index
        local bit_offset = seat_index * 2
        redis.call('BITFIELD', bf_key, 'SET', 'u2', bit_offset, 1) -- 01 = RESERVED
    end
end

-- Priority 1: Search for consecutive seats
-- Priority 2: Collect all consecutive blocks for smart fallback
local consecutive_blocks = {}

for row = 1, rows do
    -- Reset consecutive tracking for each row (seats can't span rows)
    local consecutive_count = 0
    local consecutive_seats = {}

    -- Performance optimization: Batch read entire row using BITFIELD
    local bitfield_args = { 'BITFIELD', bf_key }
    for seat_num = 1, cols do
        local seat_index = calculate_seat_index(row, seat_num, cols)
        local bit_offset = seat_index * 2
        table.insert(bitfield_args, 'GET')
        table.insert(bitfield_args, 'u2')
        table.insert(bitfield_args, bit_offset)
    end

    -- Execute BITFIELD: 1 command instead of cols × 2 GETBIT
    local seat_statuses = redis.call(unpack(bitfield_args))

    -- Process each seat status
    for seat_num = 1, cols do
        local seat_index = calculate_seat_index(row, seat_num, cols)
        local status = seat_statuses[seat_num] -- 0=AVAILABLE, 1=RESERVED, 2=SOLD

        local is_available = (status == 0)
        if is_available then
            consecutive_count = consecutive_count + 1
            table.insert(consecutive_seats, { row, seat_num, seat_index })
            if consecutive_count == quantity then
                -- ATOMIC: Reserve immediately before returning
                reserve_seats(consecutive_seats)
                return cjson.encode({
                    seats = consecutive_seats,
                    rows = rows,
                    cols = cols
                })
            end
        else
            -- Save the consecutive block if it exists
            if consecutive_count > 0 then
                table.insert(consecutive_blocks, {
                    count = consecutive_count,
                    seats = consecutive_seats
                })
            end
            -- Reset consecutive counter
            consecutive_count = 0
            consecutive_seats = {}
        end
    end

    -- Don't forget to save the last block in the row
    if consecutive_count > 0 then
        table.insert(consecutive_blocks, {
            count = consecutive_count,
            seats = consecutive_seats
        })
    end
end

-- Priority 2: Smart fallback - use largest consecutive blocks
if #consecutive_blocks > 0 then
    table.sort(consecutive_blocks, function(a, b)
        return a.count > b.count
    end)

    -- Combine largest blocks to reach quantity
    local result_seats = {}
    for _, block in ipairs(consecutive_blocks) do
        for _, seat in ipairs(block.seats) do
            table.insert(result_seats, seat)
            if #result_seats == quantity then
                -- ATOMIC: Reserve immediately before returning
                reserve_seats(result_seats)
                return cjson.encode({
                    seats = result_seats,
                    rows = rows,
                    cols = cols
                })
            end
        end
    end
end

-- Not enough seats available
return nil
