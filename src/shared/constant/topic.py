from enum import StrEnum


class Topic(StrEnum):
    TICKETING_EVENTS = 'ticketing-event'
    TICKETING_BOOKINGS = 'ticketing-booking'
    TICKETING_TICKET = 'ticketing-ticket'
    TICKETING_BOOKING_REQUEST = 'ticketing-booking-request'
    TICKETING_BOOKING_RESPONSE = 'ticketing-booking-response'
