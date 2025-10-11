import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const bookingSuccessRate = new Rate('booking_success_rate');
const bookingDuration = new Trend('booking_duration');
const authFailures = new Counter('auth_failures');
const sectionErrors = new Counter('section_errors');

// Test configuration
export const options = {
  stages: [
    { duration: '30s', target: 10 },   // Ramp up to 10 users
    { duration: '1m', target: 50 },    // Ramp up to 50 users
    { duration: '2m', target: 50 },    // Stay at 50 users
    { duration: '30s', target: 100 },  // Spike to 100 users
    { duration: '1m', target: 100 },   // Stay at 100 users
    { duration: '30s', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    'http_req_duration': ['p(95)<3000'], // 95% of requests should be below 3s
    'booking_success_rate': ['rate>0.95'], // 95% success rate
    'http_req_failed': ['rate<0.05'], // Less than 5% failures
  },
};

// Configuration
const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const EVENT_ID = parseInt(__ENV.EVENT_ID || '1');

// Test data - match database seeded data
const SECTIONS = ['A', 'B', 'C'];
const SUBSECTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
const USERS = [
  { email: 'b_1@t.com', password: 'P@ssw0rd' },
  { email: 'b_2@t.com', password: 'P@ssw0rd' },
  { email: 'b_3@t.com', password: 'P@ssw0rd' },
  { email: 'b_4@t.com', password: 'P@ssw0rd' },
  { email: 'b_5@t.com', password: 'P@ssw0rd' },
  { email: 'b_6@t.com', password: 'P@ssw0rd' },
  { email: 'b_7@t.com', password: 'P@ssw0rd' },
  { email: 'b_8@t.com', password: 'P@ssw0rd' },
  { email: 'b_9@t.com', password: 'P@ssw0rd' },
  { email: 'b_10@t.com', password: 'P@ssw0rd' },
];

// Global token storage (one per VU)
let authToken = null;

// Helper: Get random element from array
function randomElement(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// Helper: Login and get auth token
function login() {
  const user = USERS[__VU % USERS.length]; // Distribute users across VUs

  const loginPayload = JSON.stringify({
    email: user.email,
    password: user.password,
  });

  const loginRes = http.post(`${BASE_URL}/api/user/login`, loginPayload, {
    headers: { 'Content-Type': 'application/json' },
  });

  const loginSuccess = check(loginRes, {
    'login status is 200': (r) => r.status === 200,
    'has auth cookie': (r) => r.cookies['fastapiusersauth'] !== undefined,
  });

  if (!loginSuccess) {
    authFailures.add(1);
    console.error(`Login failed for ${user.email}: ${loginRes.status} - ${loginRes.body}`);
    return null;
  }

  // Extract cookie
  const cookieJar = http.cookieJar();
  const cookies = cookieJar.cookiesForURL(BASE_URL);
  return cookies['fastapiusersauth'];
}

// Setup function - runs once per VU at start
export function setup() {
  console.log('🚀 Starting k6 load test...');
  console.log(`📍 Target: ${BASE_URL}`);
  console.log(`🎫 Event ID: ${EVENT_ID}`);
  console.log(`👥 Users: ${USERS.length}`);

  // Health check
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'API is healthy': (r) => r.status === 200,
  });

  return { baseUrl: BASE_URL, eventId: EVENT_ID };
}

// Main test function - runs repeatedly for each VU
export default function (data) {
  // Login once per VU session (reuse token)
  if (!authToken) {
    authToken = login();
    if (!authToken) {
      return; // Skip iteration if login failed
    }
  }

  // Generate random booking request
  const section = randomElement(SECTIONS);
  const subsection = randomElement(SUBSECTIONS);
  const quantity = Math.floor(Math.random() * 3) + 1; // 1-3 seats

  const bookingPayload = JSON.stringify({
    event_id: data.eventId,
    section: section,
    subsection: subsection,
    seat_selection_mode: 'best_available',
    seat_positions: [],
    quantity: quantity,
  });

  // Send booking request with auth cookie
  const bookingRes = http.post(`${BASE_URL}/api/booking`, bookingPayload, {
    headers: {
      'Content-Type': 'application/json',
      'Cookie': `fastapiusersauth=${authToken}`,
    },
    tags: { name: 'CreateBooking' },
  });

  // Check response
  const success = check(bookingRes, {
    'booking status is 201': (r) => r.status === 201,
    'booking has id': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });

  // Record metrics
  bookingSuccessRate.add(success);
  bookingDuration.add(bookingRes.timings.duration);

  // Handle failures
  if (!success) {
    if (bookingRes.status === 401 || bookingRes.status === 403) {
      // Re-login on auth failure
      authToken = login();
    } else if (bookingRes.status === 404) {
      sectionErrors.add(1);
      console.warn(`Section not found: ${section}-${subsection}`);
    } else {
      console.error(`Booking failed: ${bookingRes.status} - ${bookingRes.body.substring(0, 200)}`);
    }
  }

  // Think time - simulate user behavior
  sleep(Math.random() * 2 + 1); // 1-3 seconds
}

// Teardown function - runs once at end
export function teardown(data) {
  console.log('✅ k6 load test completed!');
}
