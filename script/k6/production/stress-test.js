import http from 'k6/http';
import { check } from 'k6';
import { Trend, Counter } from 'k6/metrics';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

const bookingTime = new Trend('booking_time', true);
const bookingCompleted = new Counter('booking_completed');

// Stress test - find breaking point
export const options = {
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 1000,
      timeUnit: '1s',
      preAllocatedVUs: 5000,
      maxVUs: 10000,
      stages: [
        { target: 3000, duration: '10s' },
        { target: 5000, duration: '30s' },
        { target: 7000, duration: '1m' },
        { target: 3000, duration: '10s' },
      ],
      gracefulStop: '10s',
    },
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8100';
const EVENT_ID = parseInt(__ENV.EVENT_ID || '1');
const SECTIONS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'];

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

export default function (data) {
  const section = SECTIONS[Math.floor(Math.random() * SECTIONS.length)];
  const subsection = randomIntBetween(1, 10);
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

  if (res.status === 201) {
    bookingTime.add(res.timings.duration);
    bookingCompleted.add(1);
  }
}
