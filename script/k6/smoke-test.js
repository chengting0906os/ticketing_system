import http from 'k6/http';
import { check, sleep } from 'k6';

// Smoke test - minimal load to verify basic functionality
export const options = {
  vus: 1, // 1 virtual user
  duration: '30s',
  thresholds: {
    'http_req_duration': ['p(99)<1000'], // 99% of requests should be below 1s
    'http_req_failed': ['rate<0.01'], // Less than 1% failures
  },
};

const BASE_URL = __ENV.API_URL || 'http://localhost:8000';

export default function () {
  // Health check
  const healthRes = http.get(`${BASE_URL}/health`);
  check(healthRes, {
    'health check status is 200': (r) => r.status === 200,
    'health check is healthy': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.status === 'healthy';
      } catch (e) {
        return false;
      }
    },
  });

  sleep(1);

  // Login
  const loginRes = http.post(
    `${BASE_URL}/api/user/login`,
    JSON.stringify({
      email: 'b_1@t.com',
      password: 'P@ssw0rd',
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(loginRes, {
    'login status is 200': (r) => r.status === 200,
  });

  sleep(1);
}

export function teardown() {
  console.log('✅ Smoke test completed - basic functionality verified');
}
