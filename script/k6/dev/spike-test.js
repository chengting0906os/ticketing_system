import { setup, makeBooking } from '../lib/booking.js';
export { setup };

// Spike test - sudden traffic surge (simulates ticket sale opening)
export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: 100,
      timeUnit: '1s',
      preAllocatedVUs: 2000,
      maxVUs: 4000,
      stages: [
        { target: 1000, duration: '1s' },  // Spike up
        { target: 1000, duration: '4s' },  // Sustain
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<3000'],  // 95% under 3s during spike
    http_req_failed: ['rate<0.3'],       // Allow up to 30% failures during spike
  },
};

export default function (data) {
  makeBooking(data);
}
