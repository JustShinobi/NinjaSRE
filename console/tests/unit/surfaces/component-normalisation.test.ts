import { describe, expect, it } from 'vitest';

import { normaliseComponents } from '@/surfaces/screens/component-normalisation';

describe('normaliseComponents', () => {
  it('collapses container:<id> and guest:<id> for the same id into one guest entry', () => {
    const groups = normaliseComponents(['container:lxc/122', 'guest:lxc/122']);
    const guestGroup = groups.find((group) => group.type === 'guest');
    expect(guestGroup?.options).toHaveLength(1);
    expect(guestGroup?.options[0]?.display).toBe('lxc/122');
  });

  it('never invents the canonical value: it is always one of the raw strings actually seen', () => {
    // Only "container:lxc/122" was ever observed -- the server-side exact
    // match must be queryable with that string, never a synthesised
    // "guest:lxc/122" that names something no episode carries.
    const groups = normaliseComponents(['container:lxc/122']);
    const option = groups.find((group) => group.type === 'guest')?.options[0];
    expect(option?.canonical).toBe('container:lxc/122');
    expect(option?.raw).toEqual(['container:lxc/122']);
  });

  it('carries both raw spellings on a merged option, so a caller can query and merge both', () => {
    const groups = normaliseComponents(['container:lxc/122', 'guest:lxc/122']);
    const option = groups.find((group) => group.type === 'guest')?.options[0];
    expect(new Set(option?.raw)).toEqual(
      new Set(['container:lxc/122', 'guest:lxc/122']),
    );
    // The chosen canonical is still one of the two, never a third string.
    expect(option?.raw).toContain(option?.canonical);
  });

  it('leaves an unpaired prefixed identifier alone, under its own type', () => {
    const groups = normaliseComponents(['guest:lxc/130']);
    const guestGroup = groups.find((group) => group.type === 'guest');
    expect(guestGroup?.options).toHaveLength(1);
  });

  it('classifies a literal "cluster" as its own type', () => {
    const groups = normaliseComponents(['cluster']);
    expect(groups.find((group) => group.type === 'cluster')?.options).toHaveLength(1);
  });

  it('classifies node01/node02-shaped names as nodes', () => {
    const groups = normaliseComponents(['node01', 'node02']);
    expect(groups.find((group) => group.type === 'node')?.options).toHaveLength(2);
  });

  it('falls back to service for anything else', () => {
    const groups = normaliseComponents(['redis-exporter', 'metrics-agent.service']);
    expect(groups.find((group) => group.type === 'service')?.options).toHaveLength(2);
  });

  it('never lists the same canonical identifier twice across the whole set', () => {
    const groups = normaliseComponents([
      'container:lxc/122',
      'guest:lxc/122',
      'node01',
      'cluster',
    ]);
    const all = groups.flatMap((group) =>
      group.options.map((option) => option.canonical),
    );
    expect(new Set(all).size).toBe(all.length);
  });

  it('carries a count per type group', () => {
    const groups = normaliseComponents(['node01', 'node02', 'cluster']);
    const nodeGroup = groups.find((group) => group.type === 'node');
    expect(nodeGroup?.options).toHaveLength(2);
  });
});
