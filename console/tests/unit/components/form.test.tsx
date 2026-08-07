import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  Checkbox,
  Combobox,
  DateRange,
  Input,
  Radio,
  Select,
  Switch,
  Textarea,
} from '@/components/form';

/**
 * The form controls, held to the two things that decide whether a form works
 * for everybody: every control is named, and every control is reachable.
 *
 * "Named" means a real label, not a placeholder — a placeholder disappears the
 * moment somebody types, which is the moment they most need to know what the
 * field was. "Reachable" means the keyboard alone, tested by pressing keys
 * rather than by asserting that a handler exists.
 */

describe('every control is labelled and described', () => {
  it('labels a text input and ties its help text to it', () => {
    render(
      <Input label="Node name" name="node" description="As the cluster reports it." />,
    );
    const field = screen.getByLabelText('Node name');

    expect(field).toHaveAccessibleDescription('As the cluster reports it.');
    expect(field).toHaveAttribute('name', 'node');
  });

  it('announces an error on the control rather than only colouring it', () => {
    render(<Input label="Threshold" name="threshold" error="Must be a percentage." />);
    const field = screen.getByLabelText('Threshold');

    expect(field).toHaveAttribute('aria-invalid', 'true');
    expect(field).toHaveAccessibleDescription(/Must be a percentage/);
    expect(screen.getByRole('alert')).toHaveTextContent('Must be a percentage.');
  });

  it('labels a select, a textarea, a checkbox, a radio and a switch', () => {
    render(
      <>
        <Select
          label="Severity"
          name="severity"
          options={[{ value: 'high', label: 'High' }]}
        />
        <Textarea label="Reason" name="reason" />
        <Checkbox label="Include recovery points" name="include" />
        <Radio label="Partial reclaim" name="mode" value="partial" />
        <Switch label="Pause autonomy" name="paused" />
      </>,
    );

    for (const name of [
      'Severity',
      'Reason',
      'Include recovery points',
      'Partial reclaim',
      'Pause autonomy',
    ]) {
      expect(screen.getByLabelText(name), name).toBeInTheDocument();
    }
  });

  it('gives a switch the role and the state a switch has', () => {
    render(<Switch label="Pause autonomy" name="paused" checked />);
    expect(screen.getByRole('switch', { name: 'Pause autonomy' })).toBeChecked();
  });
});

describe('every control is operable from the keyboard', () => {
  it('reaches a text input, a checkbox and a switch in reading order', async () => {
    render(
      <>
        <Input label="First" name="first" />
        <Checkbox label="Second" name="second" />
        <Switch label="Third" name="third" />
      </>,
    );

    await userEvent.tab();
    expect(screen.getByLabelText('First')).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByLabelText('Second')).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByLabelText('Third')).toHaveFocus();
  });

  it('toggles a switch with the space bar', async () => {
    const changed = vi.fn();
    render(<Switch label="Pause autonomy" name="paused" onCheckedChange={changed} />);

    await userEvent.tab();
    await userEvent.keyboard(' ');
    expect(changed).toHaveBeenCalledWith(true);
  });
});

describe('Combobox', () => {
  it('exposes the roles the pattern requires', () => {
    render(
      <Combobox
        label="Node"
        name="node"
        options={[
          { value: 'pve01', label: 'pve01' },
          { value: 'pve02', label: 'pve02' },
        ]}
      />,
    );
    const field = screen.getByRole('combobox', { name: 'Node' });

    expect(field).toHaveAttribute('aria-expanded', 'false');
    expect(field).toHaveAttribute('aria-autocomplete', 'list');
  });

  it('opens on the down arrow and offers its options', async () => {
    render(
      <Combobox
        label="Node"
        name="node"
        options={[
          { value: 'pve01', label: 'pve01' },
          { value: 'pve02', label: 'pve02' },
        ]}
      />,
    );

    await userEvent.tab();
    await userEvent.keyboard('{ArrowDown}');

    expect(screen.getByRole('combobox')).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByRole('option')).toHaveLength(2);
  });

  it('narrows to what was typed, and says so when nothing matches', async () => {
    render(
      <Combobox
        label="Node"
        name="node"
        options={[
          { value: 'pve01', label: 'pve01' },
          { value: 'pve02', label: 'pve02' },
        ]}
      />,
    );

    await userEvent.tab();
    await userEvent.keyboard('pve01');
    expect(screen.getAllByRole('option')).toHaveLength(1);

    await userEvent.keyboard('zzz');
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByText(/no match/i)).toBeInTheDocument();
  });
});

describe('DateRange', () => {
  it('labels both ends, because "from" and "to" are two questions', () => {
    render(<DateRange label="Window" name="window" />);

    expect(screen.getByLabelText(/from/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/to/i)).toBeInTheDocument();
  });

  it('reports a range that ends before it starts rather than accepting it', () => {
    render(
      <DateRange label="Window" name="window" from="2026-02-02" to="2026-02-01" />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/ends before it starts/i);
  });
});

describe('every control reports what a person did to it', () => {
  it('reports typing, choosing, and writing', async () => {
    const typed = vi.fn();
    const chosen = vi.fn();
    const written = vi.fn();
    render(
      <>
        <Input label="Node name" name="node" onValueChange={typed} />
        <Select
          label="Severity"
          name="severity"
          options={[
            { value: 'high', label: 'High' },
            { value: 'low', label: 'Low' },
          ]}
          onValueChange={chosen}
        />
        <Textarea label="Reason" name="reason" onValueChange={written} />
      </>,
    );

    await userEvent.type(screen.getByLabelText('Node name'), 'pve01');
    expect(typed).toHaveBeenLastCalledWith('pve01');

    await userEvent.selectOptions(screen.getByLabelText('Severity'), 'low');
    expect(chosen).toHaveBeenLastCalledWith('low');

    await userEvent.type(screen.getByLabelText('Reason'), 'no');
    expect(written).toHaveBeenLastCalledWith('no');
  });

  it('reports ticking and selecting', async () => {
    const ticked = vi.fn();
    const selected = vi.fn();
    render(
      <>
        <Checkbox
          label="Include recovery points"
          name="include"
          onCheckedChange={ticked}
        />
        <Radio
          label="Partial reclaim"
          name="mode"
          value="partial"
          onSelect={selected}
        />
      </>,
    );

    await userEvent.click(screen.getByLabelText('Include recovery points'));
    expect(ticked).toHaveBeenCalledWith(true);

    await userEvent.click(screen.getByLabelText('Partial reclaim'));
    expect(selected).toHaveBeenCalledWith('partial');
  });

  it('reports a range as both ends change', async () => {
    const ranged = vi.fn();
    render(<DateRange label="Window" name="window" onRangeChange={ranged} />);

    await userEvent.type(screen.getByLabelText(/from/i), '2026-02-01');
    expect(ranged).toHaveBeenCalled();
  });

  it('narrows a combobox and reports what was typed', async () => {
    const typed = vi.fn();
    render(
      <Combobox
        label="Node"
        name="node"
        options={[{ value: 'pve01', label: 'pve01' }]}
        onValueChange={typed}
      />,
    );

    await userEvent.type(screen.getByRole('combobox'), 'pve');
    expect(typed).toHaveBeenLastCalledWith('pve');

    await userEvent.keyboard('{Escape}');
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-expanded', 'false');
  });

  it('describes a field that has both a description and an error', () => {
    render(
      <Input
        label="Threshold"
        name="threshold"
        description="A percentage of the pool."
        error="Must be between 0 and 100."
      />,
    );
    expect(screen.getByLabelText('Threshold')).toHaveAccessibleDescription(
      /A percentage of the pool.*Must be between 0 and 100/,
    );
  });
});
