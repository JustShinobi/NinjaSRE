import { describe, expect, it } from 'vitest';

import { principalIdentity } from '@/surfaces/screens/administration';

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
