import { setup, makeBooking } from '../lib/booking.js';
export { setup };

// ~20K requests (2x local)
export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 400,
      timeUnit: '1s',
      preAllocatedVUs: 1400,
      maxVUs: 2000,
      stages: [
        { target: 1200, duration: '5s' },  // 4K
        { target: 1800, duration: '8s' },  // 12K
        { target: 1000, duration: '3s' },  // 4K
      ],
    },
  },
};

export default function (data) {
  makeBooking(data);
}
