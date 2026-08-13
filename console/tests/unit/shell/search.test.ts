import { describe, expect, it } from 'vitest';

import { runCommands, searchCommands } from '@/shell/commands';
import {
  SEARCH_SHOWN,
  contains,
  incidentsMatching,
  resourcesMatching,
  runsMatching,
  worthSearching,
} from '@/shell/search';

/**
 * Typing the name of the thing that is broken.
 *
 * The palette promised "Search resources, runs, incidents" and searched none of
 * them — typing the name of a resource sitting on the Resources screen answered
 * "Nothing matches that". In an operations tool that is the shortest path there
 * is, and it led to a dead end.
 *
 * The matching is here rather than in the courier so that "does typing `signoz`
 * find the signoz box" is a question with an answer that does not need a
 * running deployment.
 */

const RESOURCES = [
  {
    resource_id: 'r1',
    display_name: 'signoz-collector',
    kind: 'container',
    health: 'healthy',
  },
  {
    resource_id: 'r2',
    display_name: 'checkout-api',
    kind: 'container',
    health: 'degraded',
  },
  {
    resource_id: 'r3',
    display_name: 'pve-node-01',
    native_id: 'proxmox/101',
    kind: 'node',
  },
];

describe('finding a resource by what it is called', () => {
  it('finds the one an operator would have typed the name of', () => {
    const found = resourcesMatching(RESOURCES, 'signoz');

    expect(found.map((entry) => entry.label)).toEqual(['signoz-collector']);
    expect(found[0]?.href).toBe('/resources?selected=r1');
  });

  it('matches the kind too, because that is a thing people type', () => {
    // "container" is what somebody types when they want the containers, not a
    // search for a resource that happens to be called container.
    expect(resourcesMatching(RESOURCES, 'container')).toHaveLength(2);
  });

  it('matches the identifier the vendor knows it by', () => {
    expect(resourcesMatching(RESOURCES, 'proxmox/101')).toHaveLength(1);
  });

  it('ignores case, because nobody types the case of a hostname', () => {
    expect(resourcesMatching(RESOURCES, 'signoz')).toHaveLength(1);
    expect(contains('SigNoz-Collector', 'signoz')).toBe(true);
  });

  it('falls back to the identifier when a resource has no name', () => {
    const found = resourcesMatching([{ resource_id: 'r9', kind: 'volume' }], 'volume');

    expect(found[0]?.label).toBe('r9');
  });

  it('shows a bounded number, so one kind cannot fill the palette', () => {
    const many = Array.from({ length: 40 }, (_, at) => ({
      resource_id: `r${String(at)}`,
      display_name: `worker-${String(at)}`,
      kind: 'container',
    }));

    expect(resourcesMatching(many, 'worker')).toHaveLength(SEARCH_SHOWN);
  });
});

describe('finding an incident and a run', () => {
  it('finds an incident by its title', () => {
    const found = incidentsMatching(
      [{ incident_id: 'inc-1', title: 'checkout is out of memory', severity: 'high' }],
      'memory',
    );

    expect(found[0]?.href).toBe('/incidents/inc-1');
    expect(found[0]?.hint).toContain('high');
  });

  it('finds a run by what it was about, not only by its identifier', () => {
    // The palette already offers the most recent runs by identifier. This is
    // the older ones, and the ones somebody remembers by subject.
    const found = runsMatching(
      [
        {
          run_id: 'run-77',
          summary: 'the node was out of memory',
          status: 'succeeded',
        },
      ],
      'node was out',
    );

    expect(found[0]?.label).toBe('run-77');
    expect(found[0]?.href).toBe('/runs/run-77');
  });

  it('gives each group its own identifier space', () => {
    // A run found by search and the same run offered as "recent" must not
    // collide: React keys them, and two entries with one key is one entry.
    const found = runsMatching([{ run_id: 'run-77' }], 'run-77');

    expect(found[0]?.id).not.toBe('run:run-77');
  });
});

describe('what is worth asking the deployment', () => {
  it('does not send a single character', () => {
    // One character matches most of an estate: three reads to return what the
    // operator is already looking at.
    expect(worthSearching('s')).toBe(false);
    expect(worthSearching('  ')).toBe(false);
  });

  it('sends two', () => {
    expect(worthSearching('pv')).toBe(true);
  });
});

describe('what a found thing becomes in the palette', () => {
  it('carries the permission its destination demands', () => {
    // The same presence rule the navigation follows. A search must not be the
    // way somebody reaches a screen the sidebar would not have offered them.
    const commands = searchCommands([
      {
        id: 'resource:r1',
        group: 'resources',
        label: 'a',
        hint: '',
        href: '/resources?selected=r1',
      },
      {
        id: 'incident:i1',
        group: 'incidents',
        label: 'b',
        hint: 'high',
        href: '/incidents/i1',
      },
      {
        id: 'found-run:run-1',
        group: 'runs',
        label: 'c',
        hint: '',
        href: '/runs/run-1',
      },
    ]);

    expect(commands.map((command) => command.permission)).toEqual([
      'estate.read',
      'incident.read',
      'investigation.read',
    ]);
  });

  it('puts each kind in its own palette group', () => {
    const commands = searchCommands([
      {
        id: 'resource:r1',
        group: 'resources',
        label: 'a',
        hint: '',
        href: '/resources?selected=r1',
      },
      {
        id: 'incident:i1',
        group: 'incidents',
        label: 'b',
        hint: '',
        href: '/incidents/i1',
      },
      {
        id: 'found-run:run-1',
        group: 'runs',
        label: 'c',
        hint: '',
        href: '/runs/run-1',
      },
    ]);

    expect(commands.map((command) => command.group)).toEqual([
      'resources',
      'incidents',
      'found-runs',
    ]);
  });

  it('leaves the hint off entirely rather than rendering an empty one', () => {
    const [without, with_] = searchCommands([
      { id: 'a', group: 'resources', label: 'a', hint: '', href: '/a' },
      { id: 'b', group: 'resources', label: 'b', hint: 'container', href: '/b' },
    ]);

    expect(without).not.toHaveProperty('hint');
    expect(with_?.hint).toBe('container');
  });

  it('falls back to the identifier when an incident has no title', () => {
    const found = incidentsMatching(
      [{ incident_id: 'inc-9', summary: 'a volume filled' }],
      'volume',
    );

    expect(found[0]?.label).toBe('inc-9');
  });

  it('falls back to the status when a run has no summary', () => {
    const found = runsMatching([{ run_id: 'run-9', status: 'failed' }], 'run-9');

    expect(found[0]?.hint).toBe('failed');
  });

  it('does not expose an exception summary when a found run becomes a command', () => {
    const [command] = searchCommands(
      [
        {
          id: 'found-run:run-10',
          group: 'runs',
          label: 'run-10',
          hint: 'InvestigatorNotConfigured: set NINJASRE_INVESTIGATOR',
          href: '/runs/run-10',
        },
      ],
      'en',
    );

    expect(command?.hint).not.toContain('NINJASRE_INVESTIGATOR');
    expect(command?.hint).not.toContain('InvestigatorNotConfigured');
    // Not "finish choosing a model": this failure is the deployment's own
    // runtime, missing whether or not a model has been chosen, so the
    // translated hint names the runtime instead of pointing at a
    // configuration field.
    expect(command?.hint).toContain('no runtime to investigate with');
  });

  it('does not expose an exception summary from recent runs either', () => {
    const [command] = runCommands(
      [
        {
          id: 'run-11',
          status: 'failed',
          summary: 'CredentialNotConfigured: add the deployment key',
        },
      ],
      'en',
    );

    expect(command?.hint).not.toContain('deployment key');
    expect(command?.hint).toContain('Store the credential');
  });
});
