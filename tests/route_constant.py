# API Route Constants

# Base API
API_BASE = '/api'

# User routes
USER_BASE = f'{API_BASE}/user'
USER_CREATE = USER_BASE
USER_GET = f'{USER_BASE}/{{user_id}}'
USER_UPDATE = f'{USER_BASE}/{{user_id}}'
USER_DELETE = f'{USER_BASE}/{{user_id}}'

# Auth routes
AUTH_BASE = f'{API_BASE}/auth'
AUTH_LOGIN = f'{AUTH_BASE}/login'
AUTH_LOGOUT = f'{AUTH_BASE}/logout'
AUTH_REGISTER = f'{AUTH_BASE}/register'

# Product routes
PRODUCT_BASE = f'{API_BASE}/product'
PRODUCT_CREATE = PRODUCT_BASE
PRODUCT_LIST = PRODUCT_BASE
PRODUCT_GET = f'{PRODUCT_BASE}/{{product_id}}'
PRODUCT_UPDATE = f'{PRODUCT_BASE}/{{product_id}}'
PRODUCT_DELETE = f'{PRODUCT_BASE}/{{product_id}}'

# Order routes
ORDER_BASE = f'{API_BASE}/order'
ORDER_CREATE = ORDER_BASE
ORDER_LIST = ORDER_BASE
ORDER_GET = f'{ORDER_BASE}/{{order_id}}'
ORDER_PAY = f'{ORDER_BASE}/{{order_id}}/pay'
ORDER_CANCEL = f'{ORDER_BASE}/{{order_id}}'
ORDER_MY_ORDERS = f'{ORDER_BASE}/my-orders'
