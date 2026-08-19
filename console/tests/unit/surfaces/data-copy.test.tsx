import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CopyAction, CopyValue } from '@/surfaces/screens/data-copy';

/**
 * One value, and the one control that puts it on the clipboard.
 *
 * The Data screen's webhook addresses are the reason this exists: a string an
 * operator has to paste, character for character, into a system this console
 * does not configure.
 */

const LABELS = { copy: 'Copy the raw payload', copied: 'Copied' } as const;

describe('a copyable value', () => {
  it('shows the value in full', () => {
    render(
      <CopyValue value="/webhooks/alertmanager" labels={LABELS} testId="address" />,
    );

    expect(screen.getByTestId('address')).toHaveTextContent('/webhooks/alertmanager');
  });

  it('copies the exact value in one click, and says it did', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    render(
      <CopyValue value="/webhooks/alertmanager" labels={LABELS} testId="address" />,
    );
    await userEvent.click(screen.getByTestId('address-copy'));

    expect(writeText).toHaveBeenCalledWith('/webhooks/alertmanager');
    expect(await screen.findByText(LABELS.copied)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('says nothing was copied when the clipboard refuses', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('refused'));
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    render(
      <CopyValue value="/webhooks/alertmanager" labels={LABELS} testId="address" />,
    );
    await userEvent.click(screen.getByTestId('address-copy'));

    expect(await screen.findByText(LABELS.copy)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

describe('a copy action with nothing displayed', () => {
  const LONG_BLOCK = 'webhook_configs:\n- url: https://example.invalid\n';

  it('never prints the value it copies', () => {
    render(
      <CopyAction
        value={LONG_BLOCK}
        label="Copy Alertmanager receiver YAML"
        copiedLabel="Copied"
        testId="receiver-yaml"
      />,
    );

    const button = screen.getByTestId('receiver-yaml');
    expect(button).toHaveTextContent('Copy Alertmanager receiver YAML');
    expect(button.textContent).not.toContain('webhook_configs');
  });

  it('copies the exact value in one click, and says it did', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    render(
      <CopyAction
        value={LONG_BLOCK}
        label="Copy Alertmanager receiver YAML"
        copiedLabel="Copied"
        testId="receiver-yaml"
      />,
    );
    await userEvent.click(screen.getByTestId('receiver-yaml'));

    expect(writeText).toHaveBeenCalledWith(LONG_BLOCK);
    expect(await screen.findByText('Copied')).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('says nothing was copied when the clipboard refuses', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('refused'));
    vi.stubGlobal('navigator', { clipboard: { writeText } });

    render(
      <CopyAction
        value={LONG_BLOCK}
        label="Copy Alertmanager receiver YAML"
        copiedLabel="Copied"
        testId="receiver-yaml"
      />,
    );
    await userEvent.click(screen.getByTestId('receiver-yaml'));

    expect(
      await screen.findByText('Copy Alertmanager receiver YAML'),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});

it('renders without test identifiers when it was given none', () => {
  // The component is used in two places: one that wants to be findable in a
  // test, and one that is a detail of a card. Neither should be able to render
  // a literal "undefined-copy" attribute into the page.
  const { container } = render(
    <CopyValue value="/webhooks/alertmanager" labels={LABELS} />,
  );

  expect(container.querySelector('[data-testid]')).toBeNull();
  expect(container.textContent).toContain('/webhooks/alertmanager');
});
