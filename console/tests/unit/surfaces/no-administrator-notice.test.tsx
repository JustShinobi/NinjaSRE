import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { NoAdministratorNotice } from '@/surfaces/no-administrator-notice';

const LABELS = {
  title: 'This deployment has no administrator yet',
  body: 'Run the command below on the host to create one.',
} as const;

const COMMAND = 'ninjasre setup admin --name admin';

describe('the no-administrator notice', () => {
  it('does not exist in the document when there is no command to show', () => {
    const { container } = render(<NoAdministratorNotice command="" labels={LABELS} />);

    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('no-administrator-notice')).not.toBeInTheDocument();
  });

  it('shows the command literally, in a region that selects and copies', () => {
    render(<NoAdministratorNotice command={COMMAND} labels={LABELS} />);

    const notice = screen.getByTestId('no-administrator-notice');
    expect(notice).toHaveTextContent(LABELS.title);
    expect(notice).toHaveTextContent(LABELS.body);

    const command = screen.getByTestId('no-administrator-command');
    expect(command).toHaveTextContent(COMMAND);
    expect(command.className).toContain('select-all');
  });

  it('never rewrites or shortens the command it was given', () => {
    render(<NoAdministratorNotice command={COMMAND} labels={LABELS} />);

    expect(screen.getByTestId('no-administrator-command').textContent).toBe(COMMAND);
  });
});
