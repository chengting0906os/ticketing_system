import http from 'k6/http';
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

export const bookingTime = new Trend('booking_time', true);
export const bookingCompleted = new Counter('booking_completed');

// API_HOST: cloud uses port 80 (http://alb-dns), local uses port 8100 (http://localhost:8100)
export const BASE_URL = __ENV.API_HOST || 'http://localhost:8100';
export const EVENT_ID = parseInt(__ENV.EVENT_ID || '1');
export const SECTIONS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'];
export const MAX_SUBSECTION = parseInt(__ENV.MAX_SUBSECTION || '10');  // 200k uses 40

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

  check(res, { 'success': (r) => r.status >= 200 && r.status < 500 });

  if (res.status === 202) {
    bookingTime.add(res.timings.duration);
    bookingCompleted.add(1);
  }
}
