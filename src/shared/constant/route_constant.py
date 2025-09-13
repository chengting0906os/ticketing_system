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

# Event routes
EVENT_BASE = f'{API_BASE}/event'
EVENT_CREATE = EVENT_BASE
EVENT_LIST = EVENT_BASE
EVENT_GET = f'{EVENT_BASE}/{{event_id}}'
EVENT_UPDATE = f'{EVENT_BASE}/{{event_id}}'
EVENT_DELETE = f'{EVENT_BASE}/{{event_id}}'

# Order routes
ORDER_BASE = f'{API_BASE}/order'
ORDER_CREATE = ORDER_BASE
ORDER_LIST = ORDER_BASE
ORDER_GET = f'{ORDER_BASE}/{{order_id}}'
ORDER_PAY = f'{ORDER_BASE}/{{order_id}}/pay'
ORDER_CANCEL = f'{ORDER_BASE}/{{order_id}}'
ORDER_MY_ORDERS = f'{ORDER_BASE}/my-orders'

# Ticket routes
TICKET_BASE = f'{API_BASE}/ticket'
