import { setup, makeBooking } from '../lib/booking.js';
export { setup };

// ~10K requests
export const options = {
  scenarios: {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 200,
      timeUnit: '1s',
      preAllocatedVUs: 700,
      maxVUs: 1000,
      stages: [
        { target: 600, duration: '5s' },   // 2K
        { target: 900, duration: '8s' },   // 6K
        { target: 500, duration: '3s' },   // 2K
      ],
    },
  },
};

export default function (data) {
  makeBooking(data);
}
