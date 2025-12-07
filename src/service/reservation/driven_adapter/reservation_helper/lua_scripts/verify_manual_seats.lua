---@diagnostic disable: undefined-global, deprecated
--[[
Verify and Reserve Manual Seats Selection (Lua Script) - ATOMIC VERSION

Verifies specified seats are available and reserves them atomically.
Config (rows, cols, price) is passed as ARGV to avoid cross-slot key access.

KEYS[1]: Bitfield key (e.g., '{e:1:s:A-1}:seats_bf')

ARGV[1]: cols (seats per row, e.g., '20')
ARGV[2]: price (section price, e.g., '1800')
ARGV[3+]: seat_ids in "row-seat" format (e.g., '1-5', '1-6', '1-7')

Returns:
- Success: JSON {"seats": [[row, seat_num, seat_index, seat_id], ...], "cols": 20, "price": 1800}
- Failure: Error string with reason

Note: Redis Cluster requires all KEYS to have same hash tag.
      This script uses only KEYS[1] to avoid cross-slot errors.
--]]

local bf_key = KEYS[1]
local cols = tonumber(ARGV[1])
local price = tonumber(ARGV[2])

-- Collect seat_ids from ARGV[3] onwards
local seat_ids = {}
for i = 3, #ARGV do
    table.insert(seat_ids, ARGV[i])
end

if #seat_ids == 0 then
    return redis.error_reply('NO_SEATS: No seat IDs provided')
end

-- Validate: Maximum 4 tickets per booking
local MAX_TICKETS = 4
if #seat_ids > MAX_TICKETS then
    return redis.error_reply('INVALID_QUANTITY: Maximum ' .. MAX_TICKETS .. ' tickets allowed')
end

-- Validate cols is provided
if not cols or cols <= 0 then
    return redis.error_reply('INVALID_CONFIG: cols must be provided and positive')
end

-- ========== STEP 1: Parse seat IDs and calculate indices ==========
local function calculate_seat_index(row, seat_num, spr)
    return (row - 1) * spr + (seat_num - 1)
end

local seats_to_reserve = {}
for _, seat_id in ipairs(seat_ids) do
    -- Parse "row-seat" format (e.g., "1-5")
    local dash_pos = string.find(seat_id, '-')
    if not dash_pos then
        return redis.error_reply('INVALID_FORMAT: Invalid seat_id format: ' .. seat_id)
    end

    local row = tonumber(string.sub(seat_id, 1, dash_pos - 1))
    local seat_num = tonumber(string.sub(seat_id, dash_pos + 1))

    if not row or not seat_num then
        return redis.error_reply('INVALID_FORMAT: Cannot parse seat_id: ' .. seat_id)
    end

    local seat_index = calculate_seat_index(row, seat_num, cols)
    local full_seat_id = row .. '-' .. seat_num

    table.insert(seats_to_reserve, {row, seat_num, seat_index, full_seat_id})
end

-- ========== STEP 2: Verify all seats are available ==========
-- Build BITFIELD command for batch verification
local bitfield_args = { 'BITFIELD', bf_key }
for _, seat in ipairs(seats_to_reserve) do
    local seat_index = seat[3]
    local offset = seat_index * 2
    table.insert(bitfield_args, 'GET')
    table.insert(bitfield_args, 'u2')
    table.insert(bitfield_args, offset)
end

local statuses = redis.call(unpack(bitfield_args))

-- Check each seat status
for i, status in ipairs(statuses) do
    if status ~= 0 then
        local seat = seats_to_reserve[i]
        local seat_id = seat[4]
        local status_name = (status == 1) and 'RESERVED' or 'SOLD'
        return redis.error_reply('SEAT_UNAVAILABLE: Seat ' .. seat_id .. ' is already ' .. status_name)
    end
end

-- ========== STEP 3: ATOMIC RESERVE - Set all seats to RESERVED ==========
-- Build BITFIELD SET command
local reserve_args = { 'BITFIELD', bf_key }
for _, seat in ipairs(seats_to_reserve) do
    local seat_index = seat[3]
    local offset = seat_index * 2
    table.insert(reserve_args, 'SET')
    table.insert(reserve_args, 'u2')
    table.insert(reserve_args, offset)
    table.insert(reserve_args, 1)  -- 1 = RESERVED
end

redis.call(unpack(reserve_args))

-- ========== SUCCESS: Return reserved seats with config ==========
return cjson.encode({
    seats = seats_to_reserve,
    cols = cols,
    price = price or 0
})
