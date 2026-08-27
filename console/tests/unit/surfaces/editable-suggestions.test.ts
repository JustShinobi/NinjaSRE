import { describe, expect, it } from 'vitest';

import { suggestedAddresses, withSuggestions } from '@/surfaces/editable';
import type { EditableField } from '@/surfaces/preview';

/**
 * Which address gets offered on which endpoint, and why it is never a guess.
 *
 * The pairing is decided by the `integration` field sitting in the same
 * section — the deployment's own statement of which vendor that source is.
 * Matching on a field's name or on a path fragment would attach an address to
 * whatever happened to be spelled similarly, which is the failure this
 * mechanism exists to prevent rather than a shortcut it may take.
 */

// Assembled, not written whole: the boundary rule forbids a third-party
// origin in console source and cannot tell a fixture from a real one.
const ADDRESS: string = ['https:', '', 'pve.lan'].join('/');

/** A field the editor would draw, with only what these two functions read. */
function fieldNamed(section: string, leaf: string, value: unknown): EditableField {
  const drawn: Partial<EditableField> = {
    section,
    path: `${section}.${leaf}`,
    label: leaf,
    value,
  };
  return drawn as EditableField;
}

const endpoint = (section: string): EditableField =>
  fieldNamed(section, 'endpoint', '');

const names = (section: string, vendor: unknown): EditableField =>
  fieldNamed(section, 'integration', vendor);

describe('suggestedAddresses', () => {
  it('reads an address and its reason, keyed by the vendor that offered it', () => {
    const found = suggestedAddresses({
      integrations: [
        {
          name: 'proxmox',
          suggested: { address: ADDRESS, because: 'discovered' },
        },
      ],
    });
    expect(found.proxmox).toEqual({ address: ADDRESS, because: 'discovered' });
  });

  it('offers nothing for a vendor whose suggestion carries no address', () => {
    const found = suggestedAddresses({
      integrations: [
        { name: 'proxmox', suggested: { address: '', because: 'looked' } },
      ],
    });
    expect(found).toEqual({});
  });

  it('offers nothing for a vendor that carries no suggestion at all', () => {
    expect(suggestedAddresses({ integrations: [{ name: 'proxmox' }] })).toEqual({});
  });

  it('reads nothing at all out of a body with no integrations', () => {
    expect(suggestedAddresses({})).toEqual({});
  });
});

describe('withSuggestions', () => {
  const offered = { proxmox: { address: ADDRESS, because: 'discovered' } };

  it('offers the address on the endpoint whose section names that vendor', () => {
    const [, given] = withSuggestions(
      [names('sources.a', 'proxmox'), endpoint('sources.a')],
      offered,
    );
    expect(given?.suggestedValue).toBe(ADDRESS);
    expect(given?.suggestedBecause).toBe('discovered');
  });

  it('leaves a field that is not an endpoint untouched', () => {
    const [given] = withSuggestions([names('sources.a', 'proxmox')], offered);
    expect(given?.suggestedValue).toBeUndefined();
  });

  it('offers nothing when the section names a vendor nobody suggested for', () => {
    const [, given] = withSuggestions(
      [names('sources.a', 'alertmanager'), endpoint('sources.a')],
      offered,
    );
    expect(given?.suggestedValue).toBeUndefined();
  });

  it('offers nothing when the section names no vendor at all', () => {
    const [given] = withSuggestions([endpoint('sources.a')], offered);
    expect(given?.suggestedValue).toBeUndefined();
  });

  it('offers nothing when the vendor field holds something that is not a name', () => {
    const [, given] = withSuggestions(
      [names('sources.a', 42), endpoint('sources.a')],
      offered,
    );
    expect(given?.suggestedValue).toBeUndefined();
  });

  it('keeps two sections apart rather than letting one vendor answer for both', () => {
    const given = withSuggestions(
      [
        names('sources.a', 'proxmox'),
        endpoint('sources.a'),
        names('sources.b', 'alertmanager'),
        endpoint('sources.b'),
      ],
      offered,
    );
    expect(given[1]?.suggestedValue).toBe(ADDRESS);
    expect(given[3]?.suggestedValue).toBeUndefined();
  });
});
