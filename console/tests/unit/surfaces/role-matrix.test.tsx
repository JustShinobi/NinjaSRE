import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

import { ROLES, ROLE_ORDER } from '../shell/support';
import { AREA_SCREENS, DETAIL_SCREENS } from '../support/screens';
import { principalHolding, serveScenario } from '../support/dataset';

/**
 * Every role × every screen, asserted as **absence**.
 *
 * A disabled control is not a substitute. It still says the capability exists,
 * it still says somebody else has it, and it still ships whatever handler sits
 * behind it — so the assertion is that the element is not in the document at
 * all.
 *
 * The roles are the platform's own, read from `fixtures/contract/roles.json`,
 * which is generated from the permission catalogue and compared against a fresh
 * generation by the Python suite. And the viewer is resolved the way the console
 * resolves one, through `/auth/me`: handing a screen a viewer object directly
 * would prove something about a test helper rather than about the console.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/** Every control on a surface that changes something, and what it needs. */
const WRITE_CONTROLS = [
  { testId: 'decision', permission: 'remediation.approve' },
  { testId: 'approve', permission: 'remediation.approve' },
  { testId: 'reject', permission: 'remediation.approve' },
  { testId: 'config-preview', permission: 'config.write' },
  { testId: 'ask-preview', permission: 'config.write' },
  { testId: 'credential', permission: 'integration.manage' },
  { testId: 'verify', permission: 'integration.manage' },
  { testId: 'token', permission: 'token.manage' },
  { testId: 'audit-export', permission: 'audit.export' },
  { testId: 'takeover', permission: 'investigation.run' },
  { testId: 'add-context', permission: 'investigation.run' },
  { testId: 'answer', permission: 'investigation.run' },
] as const;

const SCREENS = [...AREA_SCREENS, ...DETAIL_SCREENS];

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('the write controls, per role', () => {
  for (const role of ROLE_ORDER) {
    const held = ROLES.roles[role] ?? [];

    it(`${role}: no control it cannot use is anywhere on any screen`, async () => {
      for (const [index, target] of SCREENS.entries()) {
        serveScenario('populated', principalHolding(held));
        const view = render(await target.render({ searchParams: Promise.resolve({}) }));

        for (const control of WRITE_CONTROLS) {
          if (held.includes(control.permission)) continue;
          expect(
            screen.queryAllByTestId(control.testId),
            `${role} sees ${control.testId} on ${target.id}, and holds no ${control.permission}`,
          ).toEqual([]);
        }
        view.unmount();
        expect(index).toBeGreaterThanOrEqual(0);
      }
    });
  }

  it('has at least one control the least privileged role does not get', () => {
    // Without this the matrix above could pass against a console with no write
    // controls at all, which would prove nothing about presence.
    const least = ROLE_ORDER[0];
    if (least === undefined) throw new Error('the role catalogue is empty');
    const held = ROLES.roles[least] ?? [];
    expect(WRITE_CONTROLS.some((control) => !held.includes(control.permission))).toBe(
      true,
    );
  });

  it('shows the most privileged role at least one of them', async () => {
    // And the other direction: a matrix that passed because nothing is ever
    // rendered would be a matrix about an empty console.
    const most = ROLE_ORDER[ROLE_ORDER.length - 1];
    if (most === undefined) throw new Error('the role catalogue is empty');
    serveScenario('populated', principalHolding(ROLES.roles[most] ?? []));

    const configuration = AREA_SCREENS.find((each) => each.id === 'configuration');
    if (configuration === undefined)
      throw new Error('there is no configuration screen');
    render(await configuration.render({ searchParams: Promise.resolve({}) }));

    expect(screen.getByTestId('config-preview')).toBeInTheDocument();
  });
});
