---@diagnostic disable: undefined-global, deprecated
--[[
Verify Manual Seats Selection (Lua Script)

Fetches config and verifies specified seats are available.
Returns validated seat data with config for atomic reservation.

KEYS[1]: Bitfield key (e.g., 'seats_bf:1:A-1')
KEYS[2]: Event state key (e.g., 'event_state:1')

ARGV[1]: event_id (e.g., '1')
ARGV[2]: section (e.g., 'A')
ARGV[3]: subsection (e.g., '1')
ARGV[4+]: seat_ids in "row-seat" format (e.g., '1-5', '1-6', '1-7')

Returns:
- Success: JSON {"seats": [[row, seat_num, seat_index, seat_id], ...], "cols": 20, "price": 1800}
- Failure: Error string with reason
--]]

local bf_key = KEYS[1]
local event_state_key = KEYS[2]
local event_id = ARGV[1]
local section = ARGV[2]
local subsection = ARGV[3]

-- Collect seat_ids from ARGV[4] onwards
local seat_ids = {}
for i = 4, #ARGV do
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

-- ========== STEP 1: Fetch config from event_state JSON ==========
local json_path = '$.sections.' .. section .. '.subsections.' .. subsection

local subsection_result = redis.call('JSON.GET', event_state_key, json_path)
if not subsection_result then
    return redis.error_reply('CONFIG_NOT_FOUND: No config for event=' .. event_id .. ' section=' .. section .. '-' .. subsection)
end

local subsection_array = cjson.decode(subsection_result)
local subsection_config = subsection_array[1]
local cols = subsection_config.cols

-- Fetch section price
local price_path = '$.sections.' .. section .. '.price'
local price_result = redis.call('JSON.GET', event_state_key, price_path)
local price = 0
if price_result then
    local price_array = cjson.decode(price_result)
    price = price_array[1]
end

-- ========== STEP 2: Parse seat IDs and calculate indices ==========
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

-- ========== STEP 3: Verify all seats are available ==========
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

-- ========== SUCCESS: Return validated seats with config ==========
return cjson.encode({
    seats = seats_to_reserve,
    cols = cols,
    price = price
})
