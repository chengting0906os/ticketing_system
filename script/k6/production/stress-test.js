import { setup, makeBooking } from '../lib/booking.js';
export { setup };

// Stress test - find breaking point
export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 1500,
      timeUnit: '1s',
      preAllocatedVUs: 7000,
      maxVUs: 14000,
      stages: [
        { target: 2500, duration: '5s' },
        { target: 4000, duration: '5s' },
        { target: 5500, duration: '5s' },
        { target: 7000, duration: '5s' },
      ],
      gracefulStop: '10s',
    },
  },
};

export default function (data) {
  makeBooking(data);
}
