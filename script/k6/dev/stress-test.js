import { setup, makeBooking } from '../lib/booking.js';
export { setup };

// Stress test - stepped increase to find breaking point
export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 600,
      timeUnit: '1s',
      preAllocatedVUs: 1000,
      maxVUs: 2000,
      stages: [
        { target: 700, duration: '5s' },
        { target: 800, duration: '5s' },
        { target: 900, duration: '5s' },
        { target: 1000, duration: '5s' },
      ],
      gracefulStop: '10s',
    },
  },
};

export default function (data) {
  makeBooking(data);
}
