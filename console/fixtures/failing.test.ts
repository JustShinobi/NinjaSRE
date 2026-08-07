import { describe, expect, it } from 'vitest';

import { roleFor } from '@/lib/status';

// A unit test that asserts the opposite of what the module does. It exists to
// prove that a red unit suite reddens `make verify`.
describe('the seeded failing unit test', () => {
  it('claims a failure is rendered as a success', () => {
    expect(roleFor('failed')).toBe('success');
  });
});
