import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AdvancedConfigSection } from '@/surfaces/advanced-config-section';

/**
 * The one place every technical, prefix-scoped group of a domain's own
 * configuration is rendered from — proved once here so that a dona page
 * costs the ~10 lines of feeding it data, not the ~40 lines of
 * `ConfigEditor` labels this component exists to stop copying.
 */

const NODE = 'org-northwind';

const FIELDS = [{ path: 'policies.observation.paused', label: 'Paused' }];

function rawFieldsWith(paths: readonly string[]): unknown {
  return {
    fields: paths.map((path) => ({
      path,
      label: path,
      type: 'boolean',
      help: '',
      section: 'observation',
      section_help: '',
      value: true,
      provenance: NODE,
      set_here: true,
      locked_by: '',
      approval_gated: false,
      allowed_values: null,
      minimum: null,
      maximum: null,
      default: false,
      item_fields: [],
    })),
  };
}

describe('AdvancedConfigSection', () => {
  it('is collapsed by default', () => {
    render(
      <AdvancedConfigSection
        title="Observation"
        prefix="policies.observation."
        nodeId={NODE}
        locale="en"
        writable={false}
        fields={FIELDS}
        rawFields={rawFieldsWith(['policies.observation.paused'])}
      />,
    );

    const details = screen.getByTestId('advanced-config-policies-observation');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);
  });

  it('shows the effective value and its origin for every field it names', () => {
    render(
      <AdvancedConfigSection
        title="Observation"
        prefix="policies.observation."
        nodeId={NODE}
        locale="en"
        writable={false}
        fields={FIELDS}
        rawFields={rawFieldsWith(['policies.observation.paused'])}
      />,
    );

    const row = screen.getByTestId('effective-field');
    expect(row).toHaveAttribute('data-path', 'policies.observation.paused');
    expect(row).toHaveTextContent('Paused');
    expect(row).toHaveTextContent('On');
    const origin = screen.getByTestId('effective-field-origin');
    expect(origin).toHaveTextContent(NODE);
  });

  it('offers no editor to a viewer who may not write', () => {
    render(
      <AdvancedConfigSection
        title="Observation"
        prefix="policies.observation."
        nodeId={NODE}
        locale="en"
        writable={false}
        fields={FIELDS}
        rawFields={rawFieldsWith(['policies.observation.paused'])}
      />,
    );

    expect(screen.queryByTestId('ask-preview')).toBeNull();
  });

  it('offers no editor when no node is resolved, even for a writer', () => {
    render(
      <AdvancedConfigSection
        title="Observation"
        prefix="policies.observation."
        nodeId=""
        locale="en"
        writable
        fields={FIELDS}
        rawFields={rawFieldsWith(['policies.observation.paused'])}
      />,
    );

    expect(screen.queryByTestId('ask-preview')).toBeNull();
  });

  it('scopes the editor to fields under the prefix, and no others', () => {
    render(
      <AdvancedConfigSection
        title="Observation"
        prefix="policies.observation."
        nodeId={NODE}
        locale="en"
        writable
        fields={FIELDS}
        rawFields={rawFieldsWith([
          'policies.observation.paused',
          'policies.autonomy.dry_run',
        ])}
      />,
    );

    expect(screen.getByTestId('ask-preview')).toBeInTheDocument();
    const inScope = screen.getAllByTestId('field-provenance');
    expect(inScope).toHaveLength(1);
    expect(inScope[0]).toHaveAttribute('data-path', 'policies.observation.paused');
  });
});
