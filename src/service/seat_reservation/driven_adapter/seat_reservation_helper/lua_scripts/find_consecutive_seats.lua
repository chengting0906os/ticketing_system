---@diagnostic disable: undefined-global, deprecated
--[[
Find Consecutive Available Seats (Lua Script)

Strategy:
1. Priority 1: Find N consecutive available seats (best user experience)
2. Priority 2: If no consecutive seats, return LARGEST consecutive blocks (smart fallback)
3. Fail: If not enough available seats at all

Performance Optimization:
- BITFIELD batch read: Read entire row in 1 command (1 BITFIELD vs. seats_per_row × 2 GETBIT)
- For 500-seat subsection (25 rows × 20 seats): 25 BITFIELD commands vs 500+ GETBIT calls

KEYS[1]: Bitfield key (e.g., 'seats_bf:123:A-1')

ARGV[1]: rows (number of rows)
ARGV[2]: seats_per_row (seats per row)
ARGV[3]: quantity (number of seats needed)

Returns:
- Priority 1: JSON array of consecutive seats [[row, seat_num, seat_index], ...]
- Priority 2: JSON array of largest consecutive blocks (minimizes fragmentation)
- Failure: nil (not enough available seats)
--]]

-- Redis-provided globals: redis, cjson, KEYS, ARGV
local bf_key = KEYS[1]
local rows = tonumber(ARGV[1])
local seats_per_row = tonumber(ARGV[2])
local quantity = tonumber(ARGV[3])

-- Validate: Maximum 4 tickets per booking
local MAX_TICKETS = 4
if quantity > MAX_TICKETS then
    return redis.error_reply('INVALID_QUANTITY: Maximum ' .. MAX_TICKETS .. ' tickets allowed')
end

-- Helper: Calculate seat index
local function calculate_seat_index(row, seat_num, seats_per_row_arg)
    return (row - 1) * seats_per_row_arg + (seat_num - 1)
end

-- Priority 1: Search for consecutive seats
-- Priority 2: Collect all consecutive blocks for smart fallback
local consecutive_blocks = {}

for row = 1, rows do
    -- Reset consecutive tracking for each row (seats can't span rows)
    local consecutive_count = 0
    local consecutive_seats = {}

    -- 🚀 Performance optimization: Batch read entire row using BITFIELD
    -- Instead of seats_per_row × 2 GETBIT calls, use 1 BITFIELD call
    local bitfield_args = { 'BITFIELD', bf_key }
    for seat_num = 1, seats_per_row do
        local seat_index = calculate_seat_index(row, seat_num, seats_per_row)
        local bit_offset = seat_index * 2
        table.insert(bitfield_args, 'GET')      -- Append
        table.insert(bitfield_args, 'u2')       -- Append GET u2 (unsigned 2-bit integer) command
        table.insert(bitfield_args, bit_offset) -- Append
    end

    -- Execute BITFIELD: 1 command instead of seats_per_row × 2 GETBIT
    local seat_statuses = redis.call(unpack(bitfield_args)) -- Note: Redis uses Lua 5.1, which has unpack (not table.unpack)

    -- Process each seat status
    for seat_num = 1, seats_per_row do
        local seat_index = calculate_seat_index(row, seat_num, seats_per_row)
        local status = seat_statuses[seat_num] -- 0=AVAILABLE, 1=RESERVED, 2=SOLD

        local is_available = (status == 0)
        if is_available then
            consecutive_count = consecutive_count + 1
            table.insert(consecutive_seats, { row, seat_num, seat_index })
            if consecutive_count == quantity then
                return cjson.encode(consecutive_seats)
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

-- ⚠️ Priority 2: Smart fallback - use largest consecutive blocks
-- Accept any available seats (including scattered singles) when consecutive not found
if #consecutive_blocks > 0 then
    table.sort(consecutive_blocks, function(a, b) -- Sort blocks by size (largest first)
        return a.count > b.count
    end)

    -- Combine largest blocks to reach quantity
    -- Input: consecutive_blocks = [{count: 3, seats: [[1,3,2], [1,4,3], [1,5,4]]}, {count: 2, seats: [[2,8,27], [2,9,28]]}]
    -- Output: JSON string "[[1,3,2],[1,4,3],[1,5,4]]" (if quantity=3)
    local result_seats = {}
    for _, block in ipairs(consecutive_blocks) do -- _: index (ignored), block: {count: 3, seats: [[1,3,2], ...]}
        for _, seat in ipairs(block.seats) do     -- _: index (ignored), seat: {1, 3, 2} (row, seat_num, seat_index)
            table.insert(result_seats, seat)
            if #result_seats == quantity then     -- #: length operator, returns number of elements in array / python len()
                return cjson.encode(result_seats) -- Return: JSON string like "[[1,3,2],[1,4,3],[1,5,4]]"
            end
        end
    end
end

-- ❌ Not enough seats available
return nil
