import http from 'k6/http';
import { check, group } from 'k6';
import { Trend, Counter } from 'k6/metrics';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// Custom metrics
const bookingTime = new Trend('booking_time', true);
const bookingCompleted = new Counter('booking_completed');
const bookingFailed = new Counter('booking_failed');

// Test configuration - ramping-arrival-rate for precise RPS control
export const options = {
  discardResponseBodies: true,
  scenarios: {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 10,       // Start at 10 RPS
      timeUnit: '1s',
      preAllocatedVUs: 500,
      maxVUs: 1000,
      stages: [
        { target: 50, duration: '30s' },   // Ramp up to 50 RPS
        { target: 100, duration: '1m' },   // Ramp up to 100 RPS
        { target: 100, duration: '2m' },   // Stay at 100 RPS
        { target: 200, duration: '30s' },  // Spike to 200 RPS
        { target: 200, duration: '1m' },   // Stay at 200 RPS
        { target: 50, duration: '30s' },   // Ramp down to 50 RPS
      ],
      gracefulStop: '10s',
    },
  },
  thresholds: {
    'booking_time': ['p(95)<3000'],        // 95% of bookings under 3s
    'http_req_failed': ['rate<0.05'],      // Less than 5% failures
  },
};

// Configuration from environment variables
const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const EVENT_ID = parseInt(__ENV.EVENT_ID || '1');
const NUM_USERS = parseInt(__ENV.NUM_USERS || '10');

// Test data - sections and subsections
const SECTIONS = ['A', 'B', 'C'];
const SUBSECTIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

// Generate users array based on NUM_USERS
function generateUsers(count) {
  const users = [];
  for (let i = 1; i <= count; i++) {
    users.push({
      email: `b_${i}@t.com`,
      password: 'P@ssw0rd',
    });
  }
  return users;
}

// Login and get auth token
function login(baseUrl, user) {
  const payload = JSON.stringify({
    email: user.email,
    password: user.password,
  });

  const res = http.post(`${baseUrl}/api/user/login`, payload, {
    headers: { 'Content-Type': 'application/json' },
  });

  const success = check(res, {
    'login status is 200': (r) => r.status === 200,
    'has auth cookie': (r) => r.cookies['fastapiusersauth'] !== undefined,
  });

  if (!success) {
    console.error(`Login failed for ${user.email}: ${res.status}`);
    return null;
  }

  const cookieJar = http.cookieJar();
  const cookies = cookieJar.cookiesForURL(baseUrl);
  return cookies['fastapiusersauth'];
}

// Setup - runs once before test starts
export function setup() {
  console.log(`🚀 Starting k6 load test...`);
  console.log(`📍 Target: ${BASE_URL}`);
  console.log(`🎫 Event ID: ${EVENT_ID}`);
  console.log(`👥 Users: ${NUM_USERS}`);

  // Health check
  const healthRes = http.get(`${BASE_URL}/health`);
  const isHealthy = check(healthRes, {
    'API is healthy': (r) => r.status === 200,
  });

  if (!isHealthy) {
    throw new Error(`Setup failed: API health check failed with status ${healthRes.status}`);
  }

  // Login all users and collect tokens
  const users = generateUsers(NUM_USERS);
  const authTokens = [];

  for (const user of users) {
    const token = login(BASE_URL, user);
    if (token) {
      authTokens.push(token);
    }
  }

  if (authTokens.length === 0) {
    throw new Error('Setup failed: No users could login');
  }

  console.log(`✅ Setup complete: ${authTokens.length} users logged in`);

  return {
    baseUrl: BASE_URL,
    eventId: EVENT_ID,
    authTokens: authTokens,
    sections: SECTIONS,
    subsections: SUBSECTIONS,
  };
}

// Helper: Get random element from array
function randomElement(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

// Main test function - runs for each iteration
export default function (data) {
  group('reserve seats', function () {
    // Pick a random auth token
    const authToken = randomElement(data.authTokens);

    // Random section and subsection
    const section = randomElement(data.sections);
    const subsection = randomElement(data.subsections);
    const quantity = randomIntBetween(1, 4);

    const payload = JSON.stringify({
      event_id: data.eventId,
      section: section,
      subsection: subsection,
      seat_selection_mode: 'best_available',
      seat_positions: [],
      quantity: quantity,
    });

    const params = {
      headers: {
        'Content-Type': 'application/json',
        'Cookie': `fastapiusersauth=${authToken}`,
      },
      responseType: 'text',
    };

    // POST booking request
    const bookingRes = http.post(`${data.baseUrl}/api/booking`, payload, params);

    const success = check(bookingRes, {
      'booking status is 201': (r) => r.status === 201,
    });

    if (!success) {
      bookingFailed.add(1);
      return;
    }

    // GET booking to verify (optional - like reference script)
    const bookingId = bookingRes.body;
    const getParams = {
      headers: {
        'Content-Type': 'application/json',
        'Cookie': `fastapiusersauth=${authToken}`,
      },
    };

    const getRes = http.get(`${data.baseUrl}/api/booking/${bookingId}`, getParams);

    const verified = check(getRes, {
      'get booking status is 200': (r) => r.status === 200,
    });

    if (verified) {
      // Record total time (booking + verification)
      bookingTime.add(bookingRes.timings.duration + getRes.timings.duration);
      bookingCompleted.add(1);
    } else {
      bookingFailed.add(1);
    }
  });
}

// Teardown - runs once after test ends
export function teardown(data) {
  console.log('✅ k6 load test completed!');
}
