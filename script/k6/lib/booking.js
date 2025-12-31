import http from 'k6/http';
import { Counter } from 'k6/metrics';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// Custom metrics for tracking response types
export const bookingAccepted = new Counter('booking_accepted');
export const insufficientSeats = new Counter('insufficient_seats');

// 200 = login, 202 = booking accepted, 400 = seats unavailable (all expected)
http.setResponseCallback(http.expectedStatuses(200, 202, 400));

// API_HOST: cloud uses port 80 (http://alb-dns), local uses port 8100 (http://localhost:8100)
export const BASE_URL = __ENV.API_HOST || 'http://localhost:8100';
export const EVENT_ID = parseInt(__ENV.EVENT_ID || '1');
export const SECTIONS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'];

// MAX_SUBSECTION is REQUIRED: 50k=10, 100k=20, 200k=40
if (!__ENV.MAX_SUBSECTION) {
  throw new Error('MAX_SUBSECTION is required! Use: -e MAX_SUBSECTION=10 (50k), 20 (100k), or 40 (200k)');
}
export const MAX_SUBSECTION = parseInt(__ENV.MAX_SUBSECTION);

function login(baseUrl) {
  const res = http.post(`${baseUrl}/api/user/login`, JSON.stringify({
    email: 'b_1@t.com',
    password: 'P@ssw0rd',
  }), { headers: { 'Content-Type': 'application/json' } });

  if (res.status !== 200) {
    throw new Error(`Login failed: ${res.status}`);
  }

  const jar = http.cookieJar();
  return jar.cookiesForURL(baseUrl)['fastapiusersauth'];
}

export function setup() {
  const token = login(BASE_URL);
  return { baseUrl: BASE_URL, eventId: EVENT_ID, token };
}

export function makeBooking(data) {
  const section = SECTIONS[Math.floor(Math.random() * SECTIONS.length)];
  const subsection = randomIntBetween(1, MAX_SUBSECTION);
  const quantity = randomIntBetween(1, 4);

  const res = http.post(`${data.baseUrl}/api/booking`, JSON.stringify({
    event_id: data.eventId,
    section: section,
    subsection: subsection,
    seat_selection_mode: 'best_available',
    seat_positions: [],
    quantity: quantity,
  }), {
    headers: {
      'Content-Type': 'application/json',
      'Cookie': `fastapiusersauth=${data.token}`,
    },
  });

  if (res.status === 202) {
    bookingAccepted.add(1);
  } else if (res.status === 400) {
    insufficientSeats.add(1);
  }
}
