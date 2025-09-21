# Feature: Booking Creation
#     As a seller, I cannot create booking.
#     As a Buyer, I want to buy tickets by BEST AVAILAIBLE with 1 ticket.
#     As a Buyer, I want to buy tickets by BEST AVAILAIBLE with 4 tickets.
#     As a Buyer, I want to buy tickets by PICK YOUR OWN with 1 ticket.
#     As a Buyer, I want to buy tickets by PICK YOUR OWN with 4 ticket.
#   Background:
#     Given a seller exists:
#       | email           | password | name        | role   |
#       | seller@test.com | P@ssw0rd | Test Seller | seller |
#     Given a event exists:
#       | name         | description     | is_active | status    | seller_id | venue_name   | seating_config                                                                                                |
#       | Rock Concert | For cancel test | true      | available |         1 | Taipei Arena | {"sections": [{"name": "A", "price": 1200, "subsections": [{"number": 1, "rows": 10, "seats_per_row": 10}]}]} |
#     And a buyer exists:
#       | email          | password | name       | role  |
#       | buyer@test.com | P@ssw0rd | Test Buyer | buyer |
#   Scenario: buy tickets by BEST AVAILAIBLE with 1 ticket when available
#     When a buyer try to buy tickets with:
#       | method         | numbers of seats | seats |
#       | bese_available |                1 | []    |
#     Then a buyer got a booking with:
#       | buyer_id       | numbers of seats | seats | seller_name |
#       | bese_available |                1 | []    | Test Seller |
#     And a buyer got ticket with:
#   Scenario: buy tickets by BEST AVAILAIBLE with 4 ticket when available
#     When a buyer try to buy tickets with:
#       | method         | numbers of seats | seats |
#       | bese_available |                4 | []    |
#     Then a buyer got a booking with:
#     And a buyer got ticket with:
#   Scenario: buy tickets by PICK YOUR OWN with 1 ticket when available
#     When a buyer try to buy tickets with:
#       | method         | numbers of seats | seats     |
#       | bese_available |                1 | [A-1-1-1] |
#     Then a buyer got a booking with:
#     And a buyer got ticket with:
#   Scenario: buy tickets by PICK YOUR OWN with 4 tickets when available
#     When a buyer try to buy tickets with:
#       | method         | numbers of seats | seats     |
#       | bese_available |                1 | [A-1-1-1] |
#     Then a buyer got a a booking with:
#     And a buyer got ticket with:
