import { setup, makeBooking } from '../lib/booking.js';
export { setup };

// ~58K requests
export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 500,
      timeUnit: '1s',
      preAllocatedVUs: 1400,
      maxVUs: 1400,
      stages: [
        { target: 1000, duration: '5s' },    // ~3K
        { target: 1400, duration: '50s' },  // ~65K
        { target: 1000, duration: '5s' },    // ~5K
      ],
    },
  },
};

export default function (data) {
  makeBooking(data);
}
