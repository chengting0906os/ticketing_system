import { setup, makeBooking } from '../lib/booking.js';
export { setup };

// ~50K requests, spike to 5000 RPS
export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: 1000,
      timeUnit: '1s',
      preAllocatedVUs: 5000,
      maxVUs: 10000,
      stages: [
        { target: 5000, duration: '1s' },   // 6K (spike up fast)
        { target: 5000, duration: '9s' },  // 50K (sustain peak)
      ],
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<5000'],  // 95% under 5s during spike
    http_req_failed: ['rate<0.3'],       // Allow up to 30% failures during spike
  },
};

export default function (data) {
  makeBooking(data);
}
