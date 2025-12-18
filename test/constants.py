# Test Utility Constants

# Test Passwords
DEFAULT_PASSWORD = 'P@ssw0rd'

# Test Emails
TEST_EMAIL = 'test@example.com'
TEST_SELLER_EMAIL = 'seller@test.com'
TEST_BUYER_EMAIL = 'buyer@test.com'
ANOTHER_BUYER_EMAIL = 'another_buyer@test.com'
LIST_SELLER_EMAIL = 'list_seller@test.com'
EMPTY_LIST_SELLER_EMAIL = 'empty_list_seller@test.com'

# Test Names
TEST_SELLER_NAME = 'Test Seller'
TEST_BUYER_NAME = 'Test Buyer'
ANOTHER_BUYER_NAME = 'Another Buyer'
LIST_TEST_SELLER_NAME = 'List Test Seller'
EMPTY_LIST_SELLER_NAME = 'Empty List Seller'

# Event test constants
DEFAULT_VENUE_NAME = 'Default Venue'

DEFAULT_SEATING_CONFIG = {
    'rows': 25,
    'cols': 20,
    'sections': [
        {
            'name': 'A',
            'price': 1000,
            'subsections': 1,
        }
    ],
}

DEFAULT_SEATING_CONFIG_JSON = (
    '{"rows": 25, "cols": 20, "sections": [{"name": "A", "price": 1000, "subsections": 1}]}'
)
