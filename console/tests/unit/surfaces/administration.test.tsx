import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import {
  AdministrationScreen,
  principalIdentity,
} from '@/surfaces/screens/administration';

import { serveScenario } from '../support/dataset';

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

/**
 * What the Principals panel's second line says for one record.
 *
 * A service account this deployment created — the bootstrap administrator is
 * the one every deployment has — carries no email by design. "Not recorded"
 * beside its name used to read as something this deployment forgot, rather
 * than as what the record actually is.
 */
describe('a principal’s identity line', () => {
  it('shows the email when the deployment recorded one', () => {
    expect(
      principalIdentity('en', {
        email: 'avery.lockhart@example.invalid',
        kind: 'user',
        user_id: 'user-operator',
      }),
    ).toBe('avery.lockhart@example.invalid');
  });

  it('says what a service account is, in English, rather than leaving it blank', () => {
    expect(
      principalIdentity('en', {
        email: '',
        kind: 'service_account',
        user_id: 'bootstrap-administrator',
      }),
    ).toBe('A service account created at deploy, with no email.');
  });

  it('says the same thing in Brazilian Portuguese', () => {
    expect(
      principalIdentity('pt-BR', {
        email: '',
        kind: 'service_account',
        user_id: 'bootstrap-administrator',
      }),
    ).toBe('Conta de serviço criada no deploy, sem e-mail.');
  });

  it('falls back to the raw id for a blank-email principal that is not a service account', () => {
    expect(
      principalIdentity('en', { email: '', kind: 'user', user_id: 'user-mystery' }),
    ).toBe('user-mystery');
  });
});

/**
 * Administration absorbing Audit as a second tab, beside its own People and
 * access content — both already gated on an administrator's own permission,
 * so neither tab has to hide itself from a viewer who could reach the other.
 */
describe('Audit absorbed as a tab', () => {
  beforeEach(() => {
    vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
    serveScenario('populated');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  async function render_(params: Record<string, string> = {}): Promise<void> {
    render(await AdministrationScreen(await surfaceContext(params)));
  }

  it('names the area Administration, whichever tab is open', async () => {
    await render_({ tab: 'audit' });

    expect(screen.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'administration',
    );
    expect(screen.getByTestId('page-header')).toHaveTextContent('Administration');
  });

  it('offers both tabs, People first', async () => {
    await render_();

    const tabs = screen.getAllByTestId('tab-link');
    expect(tabs.map((tab) => tab.getAttribute('data-tab'))).toEqual([
      'people',
      'audit',
    ]);
  });

  it('defaults to People', async () => {
    await render_();

    expect(screen.getAllByTestId('principal').length).toBeGreaterThan(0);
    expect(screen.queryByTestId('row-list')).toBeNull();
  });

  it('shows the audit trail on its own tab', async () => {
    await render_({ tab: 'audit' });

    expect(screen.getByTestId('row-list')).toBeInTheDocument();
    expect(screen.queryByTestId('principal')).toBeNull();
  });
});
