import { text } from '../read';

/**
 * How many degraded findings no detector is currently watching.
 *
 * No endpoint answers this directly — confirmed by reading the observation
 * and detector services this build has (`evidence/caracterizacao.md`, this
 * feature's own Phase 0). `/v1/incidents/observations` names what every
 * *enabled* detector concludes right now, which is the covered set; a
 * degraded or unhealthy resource absent from it is exactly a finding nothing
 * is watching — the number the footer card names, and the definition a
 * future Painel should reuse rather than re-derive (decision 3 of the v7
 * wave: one source per fact).
 */

const PROBLEM_HEALTH = new Set(['degraded', 'unhealthy']);

/** The count of degraded/unhealthy resources with no current observation. */
export function degradedFindingsWithoutDetector(
  resources: readonly unknown[],
  observations: readonly unknown[],
): number {
  const covered = new Set(observations.map((entry) => text(entry, 'resource_id')));
  return resources.filter(
    (resource) =>
      PROBLEM_HEALTH.has(text(resource, 'health')) &&
      !covered.has(text(resource, 'resource_id')),
  ).length;
}
