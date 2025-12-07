---@diagnostic disable: undefined-global, deprecated
--[[
Find and Reserve Consecutive Available Seats (Lua Script) - ATOMIC VERSION

Strategy:
1. Priority 1: Find N consecutive available seats (best user experience)
2. Priority 2: If no consecutive seats, return LARGEST consecutive blocks (smart fallback)
3. Fail: If not enough available seats at all
4. ATOMIC: Reserve seats immediately after finding (prevent race conditions)

Performance Optimization:
- BITFIELD batch read: Read entire row in 1 command (1 BITFIELD vs. cols × 2 GETBIT)
- For 500-seat subsection (25 rows × 20 seats): 25 BITFIELD commands vs 500+ GETBIT calls

Interface:
  KEYS[1]: Bitfield key (e.g., 'seats_bf:123:A-1')
  ARGV[1]: rows (number of rows)
  ARGV[2]: cols (seats per row)
  ARGV[3]: quantity (number of seats needed)

Returns:
- Success: JSON object with seats: {"seats": [[row, seat_num, seat_index], ...], "rows": 25, "cols": 20, "price": 0}
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

-- Helper: Reserve seats atomically using BITFIELD SET with verification
-- Returns true if ALL seats were successfully reserved (were AVAILABLE=0)
-- Returns false if ANY seat was already reserved (race condition detected)
local function reserve_seats_atomically(seats)
    -- First, verify all seats are still AVAILABLE (0)
    local verify_args = { 'BITFIELD', bf_key }
    for _, seat in ipairs(seats) do
        local seat_index = seat[3]
        local bit_offset = seat_index * 2
        table.insert(verify_args, 'GET')
        table.insert(verify_args, 'u2')
        table.insert(verify_args, bit_offset)
    end

    local current_statuses = redis.call(unpack(verify_args))

    -- Check if any seat is NOT available (race condition)
    for i, status in ipairs(current_statuses) do
        if status ~= 0 then
            -- Race condition: seat was already taken
            return false
        end
    end

    -- All seats are available, reserve them atomically
    local reserve_args = { 'BITFIELD', bf_key }
    for _, seat in ipairs(seats) do
        local seat_index = seat[3]
        local bit_offset = seat_index * 2
        table.insert(reserve_args, 'SET')
        table.insert(reserve_args, 'u2')
        table.insert(reserve_args, bit_offset)
        table.insert(reserve_args, 1)  -- 1 = RESERVED
    end

    redis.call(unpack(reserve_args))
    return true
end

-- Priority 1: Search for consecutive seats
-- Priority 2: Collect all consecutive blocks for smart fallback
local consecutive_blocks = {}

for row = 1, rows do
    -- Reset consecutive tracking for each row (seats can't span rows)
    local consecutive_count = 0
    local consecutive_seats = {}

    -- Performance optimization: Batch read entire row using BITFIELD
    -- Instead of cols × 2 GETBIT calls, use 1 BITFIELD call
    local bitfield_args = { 'BITFIELD', bf_key }
    for seat_num = 1, cols do
        local seat_index = calculate_seat_index(row, seat_num, cols)
        local bit_offset = seat_index * 2
        table.insert(bitfield_args, 'GET')      -- Append
        table.insert(bitfield_args, 'u2')       -- Append GET u2 (unsigned 2-bit integer) command
        table.insert(bitfield_args, bit_offset) -- Append
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
                -- ATOMIC: Reserve immediately after finding
                if reserve_seats_atomically(consecutive_seats) then
                    return cjson.encode({
                        seats = consecutive_seats,
                        rows = rows,
                        cols = cols,
                        price = 0
                    })
                else
                    -- Race condition: retry from beginning
                    -- Reset and continue searching for other seats
                    consecutive_count = 0
                    consecutive_seats = {}
                end
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
-- Accept any available seats (including scattered singles) when consecutive not found
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
                -- ATOMIC: Reserve immediately after finding
                if reserve_seats_atomically(result_seats) then
                    return cjson.encode({
                        seats = result_seats,
                        rows = rows,
                        cols = cols,
                        price = 0
                    })
                else
                    -- Race condition: clear and try again with remaining blocks
                    result_seats = {}
                end
            end
        end
    end
end

-- Not enough seats available
return nil
