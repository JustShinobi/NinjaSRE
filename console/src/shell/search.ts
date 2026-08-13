/**
 * Finding the thing that is broken by typing its name.
 *
 * The palette's placeholder promised "Search resources, runs, incidents" and
 * searched none of them: it held the navigation, the recent runs, and one
 * action, so typing the name of a resource sitting on the Resources screen
 * answered "Nothing matches that". In an operations tool that is the shortest
 * path there is, and it went to a dead end.
 *
 * **The matching lives here, not in the courier.** The deployment's estate
 * endpoint filters by kind, health, source and label — there is no text
 * parameter to pass a name to — so something has to read a page and pick. Doing
 * it in one tested function rather than inline in a route handler is what makes
 * "does typing `signoz` find the signoz box" a question with an answer that
 * does not require a running deployment.
 *
 * **A page is a page, and the palette says so.** Reading the first N of
 * something and calling the result "no match" is the lie ``Pages.truncated``
 * exists to prevent elsewhere, so a search that only looked at part of the
 * estate reports that it did.
 */

/** One thing found, ready for the palette to render as a command. */
export interface Found {
  readonly id: string;
  readonly group: 'resources' | 'incidents' | 'runs';
  readonly label: string;
  readonly hint: string;
  readonly href: string;
}

/** What one search produced, and whether it saw everything it looked in. */
export interface SearchResults {
  readonly found: readonly Found[];
  /**
   * Whether some source held more than the search read.
   *
   * Reported rather than hidden: "nothing matches" and "nothing matches in the
   * first two hundred" are different answers, and only one of them means the
   * thing is not there.
   */
  readonly partial: boolean;
}

/** Nothing found, nothing truncated. The answer for an empty query. */
export const NOTHING: SearchResults = { found: [], partial: false };

/** How many of each kind one search reads before it stops. */
export const SEARCH_PAGE = 200;

/** How many of each kind the palette shows, so one kind cannot fill the list. */
export const SEARCH_SHOWN = 5;

/**
 * Whether `haystack` contains `needle`, case-folded.
 *
 * Substring rather than fuzzy, for the reason `matching` gives in
 * `commands.ts`: a fuzzy match ranks, and a ranking that reorders while
 * somebody is typing moves the entry out from under the Enter key they were
 * already pressing.
 */
export function contains(haystack: string, needle: string): boolean {
  return haystack.toLowerCase().includes(needle);
}

/** The fields of one record, as one string to match against. */
function haystackOf(fields: readonly (string | undefined)[]): string {
  return fields.filter((field) => field !== undefined && field !== '').join(' ');
}

/** The display name used by the estate API, with the old fixture field tolerated. */
function resourceName(record: unknown): string {
  return textOf(record, 'display_name') || textOf(record, 'name');
}

/** One record's string field, or `''` for anything that is not one. */
export function textOf(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

/**
 * The resources whose name, identifier or kind contains `needle`.
 *
 * Kind is in the haystack because "container" is a thing an operator types when
 * they want to see the containers, and a search that only matched names would
 * make that a search for a resource somebody happened to call container.
 */
export function resourcesMatching(
  records: readonly unknown[],
  needle: string,
): readonly Found[] {
  return records
    .filter((record) =>
      contains(
        haystackOf([
          resourceName(record),
          textOf(record, 'native_id'),
          textOf(record, 'kind'),
        ]),
        needle,
      ),
    )
    .slice(0, SEARCH_SHOWN)
    .map((record) => ({
      id: `resource:${textOf(record, 'resource_id')}`,
      group: 'resources' as const,
      label: resourceName(record) || textOf(record, 'resource_id'),
      hint: haystackOf([textOf(record, 'kind'), textOf(record, 'health')]),
      href: `/resources?selected=${encodeURIComponent(textOf(record, 'resource_id'))}`,
    }));
}

/** The incidents whose title or correlation key contains `needle`. */
export function incidentsMatching(
  records: readonly unknown[],
  needle: string,
): readonly Found[] {
  return records
    .filter((record) =>
      contains(
        haystackOf([
          textOf(record, 'title'),
          textOf(record, 'summary'),
          textOf(record, 'correlation_key'),
        ]),
        needle,
      ),
    )
    .slice(0, SEARCH_SHOWN)
    .map((record) => ({
      id: `incident:${textOf(record, 'incident_id')}`,
      group: 'incidents' as const,
      label: textOf(record, 'title') || textOf(record, 'incident_id'),
      hint: haystackOf([textOf(record, 'severity'), textOf(record, 'state')]),
      href: `/incidents/${encodeURIComponent(textOf(record, 'incident_id'))}`,
    }));
}

/**
 * The runs whose identifier or subject contains `needle`.
 *
 * The palette already offers the most recent runs by identifier; this is the
 * older ones, and the ones somebody remembers by what they were about rather
 * than by their identifier.
 */
export function runsMatching(
  records: readonly unknown[],
  needle: string,
): readonly Found[] {
  return records
    .filter((record) =>
      contains(
        haystackOf([
          textOf(record, 'run_id'),
          textOf(record, 'summary'),
          textOf(record, 'trigger'),
        ]),
        needle,
      ),
    )
    .slice(0, SEARCH_SHOWN)
    .map((record) => ({
      id: `found-run:${textOf(record, 'run_id')}`,
      group: 'runs' as const,
      label: textOf(record, 'run_id'),
      hint: textOf(record, 'summary') || textOf(record, 'status'),
      href: `/runs/${encodeURIComponent(textOf(record, 'run_id'))}`,
    }));
}

/**
 * The shortest query worth sending.
 *
 * One character matches most of an estate, which is a request that costs the
 * deployment three reads to return everything the operator already sees. Two is
 * where a query starts to be about something.
 */
export const SEARCH_MINIMUM = 2;

/** Whether `query` is worth asking the deployment about. */
export function worthSearching(query: string): boolean {
  return query.trim().length >= SEARCH_MINIMUM;
}
