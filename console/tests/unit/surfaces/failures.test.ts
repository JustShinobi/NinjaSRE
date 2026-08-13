import { describe, expect, it } from 'vitest';

import { readFailure } from '@/surfaces/failures';

/**
 * What an operator is told when something the deployment does fails.
 *
 * The rule this file holds is one sentence: **no exception message from the
 * gateway is ever the headline in the console**. It reached four surfaces at
 * once — the dashboard band, the run list, the run detail, and the notification
 * bell all rendered `InvestigatorNotConfigured: ... Set NINJASRE_INVESTIGATOR
 * to 'module:factory'` verbatim — which is a sentence addressed to whoever
 * deploys the thing, shown to whoever opened the console, on a screen that has
 * a button leading to the fix.
 *
 * The raw text is not thrown away. It moves behind "technical detail", where
 * the person who does deploy the thing can still read it.
 */

describe('a failure the console recognises', () => {
  it('says what is wrong in the reader’s terms and where to fix it', () => {
    const read = readFailure(
      'InvestigatorNotConfigured: No investigation runtime is configured. Set ' +
        "NINJASRE_INVESTIGATOR to 'module:factory' — a callable returning the runner.",
      'en',
    );

    expect(read.known).toBe(true);
    expect(read.title).toBe('Investigations are not switched on yet');
    expect(read.href).toBe('/first-run?step=model');
    expect(read.action).not.toBe('');
  });

  it('keeps the raw text, exactly, behind the technical detail', () => {
    const raw =
      "InvestigatorNotConfigured: Set NINJASRE_INVESTIGATOR to 'module:factory'";

    expect(readFailure(raw, 'en').technical).toBe(raw);
  });

  it('never leaks the setting name into anything a shell renders as a headline', () => {
    const read = readFailure(
      "InvestigatorNotConfigured: Set NINJASRE_INVESTIGATOR to 'module:factory'",
      'en',
    );

    expect(read.title).not.toContain('NINJASRE_INVESTIGATOR');
    expect(read.title).not.toContain('InvestigatorNotConfigured');
    expect(read.action).not.toContain('NINJASRE_INVESTIGATOR');
    expect(read.action).not.toContain('InvestigatorNotConfigured');
  });

  it('recognises a missing credential and sends somebody to the step that stores one', () => {
    const read = readFailure(
      'CredentialNotConfigured: nothing is stored for prometheus/payments',
      'en',
    );

    expect(read.known).toBe(true);
    expect(read.href).toBe('/first-run?step=credential');
  });

  it('recognises a datastore that is not answering, and offers nowhere to click', () => {
    // There is no console screen that fixes a database being down, and a button
    // that led somewhere unhelpful would be worse than none.
    const read = readFailure(
      'StoreUnavailable: could not connect to the database',
      'en',
    );

    expect(read.known).toBe(true);
    expect(read.href).toBe('');
  });

  it('translates, rather than carrying English into another locale', () => {
    const read = readFailure('InvestigatorNotConfigured: whatever it said', 'pt-BR');

    expect(read.title).not.toBe('Investigations are not switched on yet');
    expect(read.title).not.toBe('');
  });
});

describe('a failure the console does not recognise', () => {
  it('still refuses to print an exception as the headline', () => {
    const read = readFailure('ZeroDivisionError: division by zero', 'en');

    expect(read.known).toBe(false);
    expect(read.title).not.toContain('ZeroDivisionError');
    expect(read.technical).toBe('ZeroDivisionError: division by zero');
  });

  it('leaves a sentence somebody wrote for a person alone', () => {
    // The test that keeps this from turning every summary into "it failed": a
    // run whose summary is a real summary must survive unedited, or the
    // translation layer costs more than the problem it solves.
    const summary = 'The checkout database ran out of connections at 02:14.';
    const read = readFailure(summary, 'en');

    expect(read.known).toBe(false);
    expect(read.title).toBe(summary);
    expect(read.technical).toBe('');
  });

  it('treats an empty summary as nothing to say rather than as a failure', () => {
    expect(readFailure('', 'en').title).toBe('');
    expect(readFailure('   ', 'en').technical).toBe('');
  });
});
