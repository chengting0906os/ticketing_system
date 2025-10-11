import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Stress test - push system beyond normal capacity
export const options = {
  stages: [
    { duration: '1m', target: 50 },    // Ramp up to 50 users
    { duration: '2m', target: 100 },   // Ramp up to 100 users
    { duration: '3m', target: 200 },   // Push to 200 users
    { duration: '2m', target: 300 },   // Push to 300 users (stress)
    { duration: '1m', target: 400 },   // Push to 400 users (breaking point?)
    { duration: '5m', target: 400 },   // Sustain stress
    { duration: '2m', target: 0 },     // Ramp down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<5000'], // Relaxed threshold under stress
    'http_req_failed': ['rate<0.2'], // Allow up to 20% failures under stress
  },
};

const bookingSuccessRate = new Rate('booking_success_rate');
const bookingDuration = new Trend('booking_duration');

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const EVENT_ID = parseInt(__ENV.EVENT_ID || '1');

const SECTIONS = ['A', 'B', 'C'];
const SUBSECTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const USERS = Array.from({ length: 10 }, (_, i) => ({
  email: `b_${i + 1}@t.com`,
  password: 'P@ssw0rd',
}));

let authToken = null;

function randomElement(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function login() {
  const user = USERS[__VU % USERS.length];
  const loginRes = http.post(
    `${BASE_URL}/api/user/login`,
    JSON.stringify({
      email: user.email,
      password: user.password,
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  if (loginRes.status === 200 && loginRes.cookies['fastapiusersauth']) {
    const cookieJar = http.cookieJar();
    const cookies = cookieJar.cookiesForURL(BASE_URL);
    return cookies['fastapiusersauth'];
  }
  return null;
}

export default function () {
  if (!authToken) {
    authToken = login();
    if (!authToken) return;
  }

  const section = randomElement(SECTIONS);
  const subsection = randomElement(SUBSECTIONS);

  const bookingRes = http.post(
    `${BASE_URL}/api/booking`,
    JSON.stringify({
      event_id: EVENT_ID,
      section: section,
      subsection: subsection,
      seat_selection_mode: 'best_available',
      seat_positions: [],
      quantity: 2,
    }),
    {
      headers: {
        'Content-Type': 'application/json',
        'Cookie': `fastapiusersauth=${authToken}`,
      },
    }
  );

  const success = check(bookingRes, {
    'booking created': (r) => r.status === 201,
  });

  bookingSuccessRate.add(success);
  bookingDuration.add(bookingRes.timings.duration);

  if (!success && (bookingRes.status === 401 || bookingRes.status === 403)) {
    authToken = login();
  }

  sleep(Math.random() * 1 + 0.5); // 0.5-1.5s
}

export function teardown() {
  console.log('✅ Stress test completed - system limits identified');
}
