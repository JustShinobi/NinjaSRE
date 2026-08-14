'use client';

import type { ReactNode } from 'react';
import { useState, useSyncExternalStore } from 'react';

import { Button } from '@/components/action';
import { Input, Select, Switch } from '@/components/form';
import { Badge } from '@/components/status';
import { cx } from '@/design/cx';

/**
 * Editing configuration at a node, previewed against the deployment first.
 *
 * There is no merge in this component and there is nowhere in the console one
 * could be: the pending change is posted, and what comes back is rendered. That
 * is the requirement stated exactly — the preview MUST be the server's answer,
 * never a client-side merge — and it is worth restating why. A merge written
 * here would agree with the server for as long as nobody changes inheritance,
 * and the first time somebody does, an operator previews one result and saves
 * another.
 *
 * **Preview before save is structural rather than advised.** The save control
 * does not exist until a preview of the *current* change has come back, and any
 * further edit removes it again. It has to be a client guarantee: no API can
 * know whether a person read the diff, and a save that demanded a preview token
 * would only prove the browser had asked. What can be built is a document with
 * nothing in it to press.
 *
 * **Every control comes from the catalogue.** Type, range and closed set are
 * the deployment's answer to "what is this field", so an integer is a number
 * control and a closed set is a list. A console holding its own table would
 * offer values the write path refuses, which reads as the platform being
 * arbitrary.
 *
 * **Clearing an override is its own operation.** It is not "set it to the
 * parent's value": one keeps following the parent and the other freezes today's
 * answer into this node, and they diverge the moment somebody edits the parent.
 * So a clear travels as a removal beside the patch, and the diff says what the
 * field reverts to and from where.
 */

/** Where the two halves of a write go. Both are couriers in the console's process. */
const PREVIEW_ENDPOINT = '/api/preview';
const SAVE_ENDPOINT = '/api/config';

/** The types this surface offers a control for. Everything else is read-only here. */
const EDITABLE_TYPES: readonly string[] = ['string', 'integer', 'number', 'boolean'];

/**
 * One field inside an entry of an ordered list of objects.
 *
 * Half of `EditableField` is about a *node* — where the value came from,
 * whether this node overrides it, which ancestor locked it. None of that is
 * true one level down: a list replaces entirely, so an entry inherits the
 * list's answer to all of it and has none of its own.
 */
export interface ItemField {
  /** Relative to the entry, because an entry nobody has added yet has no index. */
  readonly path: string;
  readonly label: string;
  readonly type: string;
  readonly help: string;
  readonly allowedValues: readonly string[] | null;
  readonly minimum: number | null;
  readonly maximum: number | null;
  /** What a newly added entry starts this field at. */
  readonly default: unknown;
}

export interface EditableField {
  readonly path: string;
  readonly label: string;
  /** As the deployment's schema declares it: string, integer, number, boolean, array, object. */
  readonly type: string;
  /**
   * One to three lines, written for whoever is filling this form in.
   *
   * Deliberately not the schema's own `description`, which this form used to
   * render and which is written for whoever reviews the schema: it cited
   * requirement identifiers and source paths, ran to eight lines a section, and
   * arrived with reStructuredText markup nothing here renders. The long text
   * still exists for the code; the deployment now declares a short one beside
   * it and this is that one.
   */
  readonly help: string;
  readonly section: string;
  readonly sectionHelp: string;
  readonly value: unknown;
  /**
   * What this field resolves to when no node in the chain overrides it.
   *
   * Distinct from `value`, which the deployment reports as `null` for a field
   * nothing sets — the merge does not fabricate a value there, and neither
   * does this console. The default is what an unset field is actually
   * running with, and it comes from the same schema the write path validates
   * against.
   */
  readonly default: unknown;
  /** The node supplying the effective value, or empty when nothing sets it. */
  readonly provenance: string;
  /** Whether *this* node overrides it, which is when a clear is an operation at all. */
  readonly setHere: boolean;
  readonly lockedBy: string;
  readonly approvalGated: boolean;
  readonly allowedValues: readonly string[] | null;
  readonly minimum: number | null;
  readonly maximum: number | null;
  /**
   * An address the deployment already found for this field, and why.
   *
   * Offered rather than applied. A derived address is evidence, not a decision:
   * filling it in silently would make the form claim somebody had chosen it,
   * and a wrong guess would then be indistinguishable from a wrong choice.
   */
  readonly suggestedValue: string;
  readonly suggestedBecause: string;
  /**
   * For an array of objects: what one entry is made of.
   *
   * Empty everywhere else, including an array of strings — there is nothing
   * inside a string to draw, and a row of controls for one would be a shape
   * this console invented.
   */
  readonly itemFields: readonly ItemField[];
}

export interface EditorLabels {
  readonly setting: string;
  readonly value: string;
  readonly submit: string;
  readonly save: string;
  readonly saving: string;
  readonly saved: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly before: string;
  readonly after: string;
  readonly locked: string;
  readonly lockedDetail: string;
  readonly gated: string;
  readonly gatedDetail: string;
  readonly provenance: string;
  /** Prefixes an override's node, unambiguously — never "the default". */
  readonly setAt: string;
  /** Prefixes the value a field runs with when nothing overrides it. */
  readonly usingDefault: string;
  readonly toc: string;
  readonly search: string;
  readonly searchEmpty: string;
  /** What a field with no declared section is grouped under. */
  readonly generalSection: string;
  readonly empty: string;
  readonly previewFirst: string;
  readonly clear: string;
  readonly cleared: string;
  readonly redundant: string;
  readonly reverts: string;
  readonly notEditable: string;
  readonly inherited: string;
  readonly useSuggested: string;
  readonly addEntry: string;
  readonly removeEntry: string;
  readonly moveUp: string;
  readonly moveDown: string;
  /** Prefixes an entry's position, which is what an ordered list *means*. */
  readonly entryPosition: string;
  readonly emptyList: string;
}

export interface ConfigEditorProps {
  readonly nodeId: string;
  /** Every field this node can be edited by, as the deployment describes them. */
  readonly fields: readonly EditableField[];
  readonly labels: EditorLabels;
}

interface Change {
  readonly path: string;
  readonly before: string;
  readonly after: string;
}

interface Inherited {
  readonly path: string;
  readonly value: string;
  readonly from: string;
}

interface Previewed {
  readonly changes: readonly Change[];
  readonly locked: readonly string[];
  readonly gated: readonly string[];
  readonly requiresApproval: boolean;
  readonly redundant: readonly Inherited[];
  readonly reverts: readonly Inherited[];
}

/** What a change is: the values that were keyed, and the overrides being dropped. */
interface Pending {
  readonly edits: Readonly<Record<string, string>>;
  readonly cleared: readonly string[];
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

/** Read the deployment's answer without holding an opinion about it. */
function previewedFrom(body: unknown): Previewed {
  const changes: unknown = Reflect.get(Object(body), 'changes');
  const locked: unknown = Reflect.get(Object(body), 'locked');
  const gated: unknown = Reflect.get(Object(body), 'approval_gated');
  return {
    changes: (Array.isArray(changes) ? changes : []).map((change) => ({
      path: stringify(Reflect.get(Object(change), 'path')),
      before: stringify(Reflect.get(Object(change), 'before')),
      after: stringify(Reflect.get(Object(change), 'after')),
    })),
    locked: typeof locked === 'object' && locked !== null ? Object.keys(locked) : [],
    gated: Array.isArray(gated) ? gated.map(String) : [],
    requiresApproval: Reflect.get(Object(body), 'requires_approval') === true,
    redundant: inheritedFrom(body, 'redundant'),
    reverts: inheritedFrom(body, 'reverts'),
  };
}

function inheritedFrom(body: unknown, key: string): readonly Inherited[] {
  const found: unknown = Reflect.get(Object(body), key);
  return (Array.isArray(found) ? found : []).map((entry) => ({
    path: stringify(Reflect.get(Object(entry), 'path')),
    value: stringify(Reflect.get(Object(entry), 'value')),
    from: stringify(Reflect.get(Object(entry), 'inherited_from')),
  }));
}

/** Whether this field is an ordered list of objects rather than a plain leaf. */
function isObjectList(field: EditableField): boolean {
  return field.type === 'array' && field.itemFields.length > 0;
}

/** The entries a list field currently holds, from the pending edit or the value. */
function entriesOf(field: EditableField, keyed: string | undefined): readonly Entry[] {
  const source: unknown = keyed === undefined ? field.value : safeParse(keyed);
  if (!Array.isArray(source)) return [];
  const found: unknown[] = source;
  return found.map((each) =>
    typeof each === 'object' && each !== null ? { ...(each as Entry) } : {},
  );
}

function safeParse(keyed: string): unknown {
  try {
    return JSON.parse(keyed);
  } catch {
    return [];
  }
}

/**
 * Return the value a typed control produced, as the deployment's schema wants it.
 *
 * A list of objects rides in the pending map as JSON, because that map is keyed
 * by path and holds strings. It is parsed back here rather than kept as a
 * second kind of pending state: one shape of pending change means one
 * invalidates-the-preview comparison, and two would eventually disagree.
 */
function typed(field: EditableField, keyed: string): unknown {
  if (isObjectList(field)) return safeParse(keyed);
  if (field.type === 'boolean') return keyed === 'true';
  if (field.type === 'integer') return Number.parseInt(keyed, 10);
  if (field.type === 'number') return Number.parseFloat(keyed);
  return keyed;
}

/** One entry of an ordered list, as the editor holds it while it is being edited. */
type Entry = Record<string, unknown>;

/** Every field belonging to one section, in the order the catalogue declared them. */
interface Section {
  readonly section: string;
  readonly summary: string;
  readonly fields: readonly EditableField[];
}

/**
 * Group `fields` by `section`, first-seen order.
 *
 * The catalogue already tags every field with the section it belongs to; this
 * editor used to ignore that and draw one flat column, which is how a dozen
 * unrelated settings ended up looking like a single undifferentiated form.
 * Grouping does not change what is editable — every field is still on the
 * page — it changes whether the page can be scanned.
 */
function sectioned(fields: readonly EditableField[]): readonly Section[] {
  const order: string[] = [];
  const bySection = new Map<string, EditableField[]>();
  for (const field of fields) {
    if (!bySection.has(field.section)) {
      order.push(field.section);
      bySection.set(field.section, []);
    }
    bySection.get(field.section)?.push(field);
  }
  return order.map((section) => ({
    section,
    summary: bySection.get(section)?.[0]?.sectionHelp ?? '',
    fields: bySection.get(section) ?? [],
  }));
}

/** Whether `field` matches a search typed against its label or its path. */
function matchesQuery(field: EditableField, query: string): boolean {
  if (query === '') return true;
  return (
    field.label.toLowerCase().includes(query) ||
    field.path.toLowerCase().includes(query)
  );
}

/** An id an anchor can jump to, stable for one section across renders. */
function sectionId(section: string): string {
  return section === ''
    ? 'config-section-general'
    : `config-section-${section.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`;
}

/** Where a section's open state is remembered, across visits and across nodes. */
const OPEN_SECTIONS_KEY = 'ninjasre.configuration.openSections';

/**
 * Published when the remembered layout changes.
 *
 * Storage events do not fire in the tab that wrote the value, so a form that
 * only listened to those would not re-render in the very window somebody just
 * opened a section in. The same reason `DENSITY_CHANGED_EVENT` exists.
 */
const OPEN_SECTIONS_CHANGED_EVENT = 'ninjasre:config-sections-changed';

/** Nothing open — what the server renders, and what a browser with no memory has. */
const NOTHING_OPEN: Readonly<Record<string, boolean>> = {};

/**
 * The sections the operator has previously opened, read from this browser.
 *
 * Never the deployment. A collapsed-by-default form is friendlier the first
 * time and only stays friendly if it does not forget what somebody already
 * decided they cared about — and that decision belongs to the browser they
 * are sitting at, not to configuration this console would then have to write
 * back and diff against.
 *
 * The snapshot is cached because `useSyncExternalStore` compares by identity:
 * parsing the JSON afresh on every render would hand React a new object each
 * time and spin.
 */
let openSectionsSnapshot: Readonly<Record<string, boolean>> = NOTHING_OPEN;
let openSectionsRaw: string | null = null;

function readOpenSections(): Readonly<Record<string, boolean>> {
  let raw: string | null;
  try {
    raw = window.localStorage.getItem(OPEN_SECTIONS_KEY);
  } catch {
    return NOTHING_OPEN;
  }
  if (raw === openSectionsRaw) return openSectionsSnapshot;
  openSectionsRaw = raw;
  try {
    const parsed: unknown = raw === null ? null : JSON.parse(raw);
    openSectionsSnapshot =
      typeof parsed === 'object' && parsed !== null
        ? (parsed as Record<string, boolean>)
        : NOTHING_OPEN;
  } catch {
    openSectionsSnapshot = NOTHING_OPEN;
  }
  return openSectionsSnapshot;
}

/**
 * What the server renders: every section closed.
 *
 * Not the remembered layout, which the server cannot know. Reading storage into
 * state during the first client render instead would produce markup that
 * disagrees with the HTML the server sent — a hydration mismatch, and a visible
 * correction on every load for the returning operator this memory exists for.
 * `browser.ts` argues the same case for the theme and the density; a form is no
 * different from a stylesheet in this respect.
 */
function openSectionsServerSnapshot(): Readonly<Record<string, boolean>> {
  return NOTHING_OPEN;
}

function subscribeToOpenSections(onChange: () => void): () => void {
  window.addEventListener(OPEN_SECTIONS_CHANGED_EVENT, onChange);
  return () => {
    window.removeEventListener(OPEN_SECTIONS_CHANGED_EVENT, onChange);
  };
}

function saveOpenSections(state: Readonly<Record<string, boolean>>): void {
  try {
    window.localStorage.setItem(OPEN_SECTIONS_KEY, JSON.stringify(state));
  } catch {
    // Private browsing or a full quota. Losing the remembered layout is not
    // losing configuration, so there is nothing here worth surfacing — but the
    // section still opens for the life of this page, because the event below
    // is what the form actually re-renders from.
    openSectionsRaw = null;
    openSectionsSnapshot = state;
  }
  window.dispatchEvent(new Event(OPEN_SECTIONS_CHANGED_EVENT));
}

/**
 * What one item field of an entry holds, read as the title for that entry.
 *
 * Only ever the entry's own `name` field, and only when it is a non-empty
 * string. Falling back to anything derived — the first field, the path — would
 * put a guess where "proxmox" belongs, and the guess is exactly what made
 * every entry read as "Evaluated 1" in the first place.
 */
function entryTitle(entry: Entry, items: readonly ItemField[]): string {
  const named = items.find((item) => item.path === 'name');
  if (named === undefined) return '';
  const value = entry[named.path];
  return typeof value === 'string' ? value : '';
}

/** Return the entry a newly added row starts as, from the catalogue's defaults. */
function blankEntry(items: readonly ItemField[]): Entry {
  const fresh: Entry = {};
  for (const item of items) {
    fresh[item.path] = item.default ?? (item.type === 'boolean' ? false : '');
  }
  return fresh;
}

/** Return one item's current value as a control's string. */
function itemValue(entry: Entry, item: ItemField): string {
  return stringify(entry[item.path]);
}

/** Return the value an item control produced, in the type the schema declares. */
function itemTyped(item: ItemField, keyed: string): unknown {
  if (item.type === 'boolean') return keyed === 'true';
  if (item.type === 'integer') return Number.parseInt(keyed, 10);
  if (item.type === 'number') return Number.parseFloat(keyed);
  return keyed;
}

/** Return `patch` with `value` set at the dotted `path`, nesting as it goes. */
function placed(
  patch: Record<string, unknown>,
  path: string,
  value: unknown,
): Record<string, unknown> {
  const segments = path.split('.');
  let cursor = patch;
  for (const segment of segments.slice(0, -1)) {
    const existing: unknown = cursor[segment];
    const next: Record<string, unknown> =
      typeof existing === 'object' && existing !== null
        ? (existing as Record<string, unknown>)
        : {};
    cursor[segment] = next;
    cursor = next;
  }
  cursor[segments[segments.length - 1] ?? path] = value;
  return patch;
}

/**
 * Return the request body a change makes, built from a sorted path list.
 *
 * Sorted so the body is a stable function of the change rather than of the
 * order somebody happened to type in — which is what lets it double as the
 * identity of the thing that was previewed.
 */
function bodyOf(
  nodeId: string,
  fields: readonly EditableField[],
  pending: Pending,
): Record<string, unknown> {
  const byPath = new Map(fields.map((field) => [field.path, field]));
  const patch: Record<string, unknown> = {};
  for (const path of Object.keys(pending.edits).sort()) {
    const field = byPath.get(path);
    const keyed = pending.edits[path];
    if (field === undefined || keyed === undefined || keyed === '') continue;
    placed(patch, path, typed(field, keyed));
  }
  return { nodeId, patch, remove: [...pending.cleared].sort() };
}

/** Whether anything is pending at all. An empty change is not previewable. */
function isEmpty(body: Record<string, unknown>): boolean {
  const patch = body.patch as Record<string, unknown>;
  const remove = body.remove as string[];
  return Object.keys(patch).length === 0 && remove.length === 0;
}

/** Change one or more settings, see what the deployment says, then save that. */
export function ConfigEditor({ nodeId, fields, labels }: ConfigEditorProps): ReactNode {
  const [pending, setPending] = useState<Pending>({ edits: {}, cleared: [] });
  const [answer, setAnswer] = useState<Previewed | null>(null);
  // The change the answer above was produced for. Compared against the current
  // one on every render, so an edit invalidates the preview without anything
  // having to remember to clear it.
  const [previewedBody, setPreviewedBody] = useState('');
  const [asking, setAsking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState('');
  // Every section starts closed and stays that way until the operator opens
  // one — reaching a field the operator already knows the name of should not
  // cost a scroll past a hundred others. The remembered layout is an external
  // store with a server snapshot rather than component state, so the first
  // paint matches the HTML the server sent and React, not an effect, is what
  // brings the browser's own answer in.
  const openSections = useSyncExternalStore(
    subscribeToOpenSections,
    readOpenSections,
    openSectionsServerSnapshot,
  );
  const [query, setQuery] = useState('');

  function toggleSection(section: string, open: boolean): void {
    saveOpenSections({ ...openSections, [section]: open });
  }

  const body = bodyOf(nodeId, fields, pending);
  const serialised = JSON.stringify(body);
  const empty = isEmpty(body);
  const current = answer !== null && serialised === previewedBody;
  const trimmedQuery = query.trim().toLowerCase();
  const searching = trimmedQuery !== '';
  const everySection = sectioned(fields);
  const visibleSections = searching
    ? everySection
        .map((entry) => ({
          ...entry,
          fields: entry.fields.filter((field) => matchesQuery(field, trimmedQuery)),
        }))
        .filter((entry) => entry.fields.length > 0)
    : everySection;

  function edit(path: string, keyed: string): void {
    setSaved(false);
    setFailure('');
    setPending((was) => ({ ...was, edits: { ...was.edits, [path]: keyed } }));
  }

  function toggleClear(path: string): void {
    setSaved(false);
    setFailure('');
    setPending((was) => ({
      ...was,
      cleared: was.cleared.includes(path)
        ? was.cleared.filter((each) => each !== path)
        : [...was.cleared, path],
    }));
  }

  function ask(): void {
    setAsking(true);
    setFailure('');
    void fetch(PREVIEW_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: serialised,
    })
      .then(async (response) => {
        const answered: unknown = await response.json();
        setAnswer(previewedFrom(answered));
        setPreviewedBody(serialised);
      })
      .catch(() => {
        setFailure(labels.unreachable);
      })
      .finally(() => {
        setAsking(false);
      });
  }

  async function save(): Promise<void> {
    setSaving(true);
    setFailure('');
    let response: Response;
    try {
      response = await fetch(SAVE_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: previewedBody,
      });
    } catch {
      // The deployment, not this process. Saying "refused" would send somebody
      // to look at the wrong machine and find nothing wrong with it.
      setSaving(false);
      setFailure(labels.unreachable);
      return;
    }
    const written: unknown = await response.json().catch(() => ({}));
    setSaving(false);
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(written), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return;
    }
    setSaved(true);
    setAnswer(null);
    setPreviewedBody('');
    setPending({ edits: {}, cleared: [] });
  }

  return (
    <div data-testid="config-editor" className="flex flex-col gap-3">
      {/* Fixed above the sections, so reaching a field by name or by section
          never costs a scroll past the ones before it. */}
      <div className="sticky top-0 z-10 flex flex-col gap-2 bg-surface py-2 edge border-border border-t-0 border-x-0">
        <Input
          label={labels.search}
          name="config-field-search"
          type="search"
          value={query}
          onValueChange={setQuery}
        />
        <nav
          aria-label={labels.toc}
          data-testid="section-toc"
          className="flex flex-wrap gap-3"
        >
          {everySection.map(({ section, fields: sectionFields }) => (
            <a
              key={section === '' ? ' ' : section}
              href={`#${sectionId(section)}`}
              data-testid="section-link"
              data-section={section}
              className="text-meta text-strong underline"
              onClick={() => {
                toggleSection(section, true);
              }}
            >
              {section === '' ? labels.generalSection : section} ({sectionFields.length}
              )
            </a>
          ))}
        </nav>
      </div>

      <div className="flex flex-col gap-3">
        {visibleSections.length === 0 ? (
          <p data-testid="search-empty" className="text-meta text-muted">
            {labels.searchEmpty}
          </p>
        ) : (
          visibleSections.map(({ section, summary, fields: sectionFields }) => (
            <details
              key={section === '' ? ' ' : section}
              id={sectionId(section)}
              data-testid="config-section"
              data-section={section}
              open={searching || (openSections[section] ?? false)}
              onToggle={(event) => {
                if (searching) return;
                toggleSection(section, (event.target as HTMLDetailsElement).open);
              }}
              className="edge border-border rounded-2 px-3 py-2"
            >
              <summary className="cursor-pointer select-none">
                <span className="font-mono text-meta text-strong">
                  {section === '' ? labels.generalSection : section}
                </span>
                {summary === '' ? null : (
                  <span className="ml-2 text-meta text-muted">{summary}</span>
                )}
              </summary>
              <div className="flex flex-col gap-3 pt-3">
                {sectionFields.map((field) => (
                  <FieldRow
                    key={field.path}
                    field={field}
                    keyed={pending.edits[field.path]}
                    cleared={pending.cleared.includes(field.path)}
                    labels={labels}
                    onEdit={edit}
                    onToggleClear={toggleClear}
                  />
                ))}
              </div>
            </details>
          ))
        )}
      </div>

      {/* Sticky the moment there is something pending, so previewing and
          saving never cost a scroll back to wherever the button row started
          out. Ordinary flow otherwise — nothing here needs to follow the
          viewport when there is nothing to act on. */}
      <div
        className={cx(
          'flex flex-wrap items-center gap-3 px-3 py-2',
          empty ? '' : 'sticky bottom-0 z-10 bg-surface rounded-2 edge border-border',
        )}
      >
        <Button
          variant="primary"
          data-testid="ask-preview"
          state={asking ? 'loading' : empty ? 'disabled' : 'default'}
          onClick={ask}
        >
          {labels.submit}
        </Button>

        {/* Absent rather than disabled. A save that exists and refuses is a save
            somebody presses twice and then reports as broken. */}
        {current ? (
          <Button
            data-testid="save-config"
            state={saving ? 'loading' : 'default'}
            onClick={() => {
              void save();
            }}
          >
            {saving ? labels.saving : labels.save}
          </Button>
        ) : empty ? null : (
          <span data-testid="preview-first" className="text-meta text-muted">
            {labels.previewFirst}
          </span>
        )}

        {saved ? (
          <span data-testid="save-result" className="text-meta text-success">
            {labels.saved}
          </span>
        ) : null}
        {failure === '' ? null : (
          <span data-testid="save-failure" className="text-meta text-danger">
            {failure}
          </span>
        )}
      </div>

      {answer === null || !current ? null : <Diff answer={answer} labels={labels} />}
    </div>
  );
}

interface FieldRowProps {
  readonly field: EditableField;
  readonly keyed: string | undefined;
  readonly cleared: boolean;
  readonly labels: EditorLabels;
  readonly onEdit: (path: string, value: string) => void;
  readonly onToggleClear: (path: string) => void;
}

/** One field: its control, where its value came from, and what constrains it. */
function FieldRow({
  field,
  keyed,
  cleared,
  labels,
  onEdit,
  onToggleClear,
}: FieldRowProps): ReactNode {
  // The deployment reports `null` for a field nothing overrides — it does not
  // fabricate a value, and neither does this console — but `null` is not what
  // is actually running. Once there is a schema default worth showing, the
  // control opens on it rather than on a blank the operator has to already
  // know to distrust.
  const defaultKnown = field.provenance === '' && stringify(field.default) !== '';
  const current =
    keyed ??
    (defaultKnown && !isObjectList(field)
      ? stringify(field.default)
      : stringify(field.value));
  return (
    <div
      data-testid="config-field"
      data-path={field.path}
      className="flex flex-col gap-1"
    >
      {field.lockedBy !== '' ? (
        <span data-testid="field-locked" className="flex items-center gap-2">
          <Badge status="locked" />
          <span className="text-meta text-muted">
            {field.label} — {labels.lockedDetail} {field.lockedBy}
          </span>
        </span>
      ) : isObjectList(field) ? (
        <ObjectList
          field={field}
          entries={entriesOf(field, keyed)}
          disabled={cleared}
          labels={labels}
          onEdit={onEdit}
        />
      ) : EDITABLE_TYPES.includes(field.type) ? (
        <Control field={field} value={current} disabled={cleared} onEdit={onEdit} />
      ) : (
        <span data-testid="field-not-editable" className="flex items-center gap-2">
          <span className="text-meta font-mono">{field.path}</span>
          <span className="text-meta text-muted">{labels.notEditable}</span>
        </span>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <span
          data-testid="field-provenance"
          data-path={field.path}
          className="text-meta text-muted"
        >
          {field.provenance !== ''
            ? // An override, recorded at a node — never called "the default",
              // even where the node itself happens to be named that. The two
              // phrases below never share a word for exactly that reason.
              `${labels.setAt} ${field.provenance}`
            : defaultKnown
              ? `${labels.usingDefault} ${stringify(field.default)}`
              : `${labels.provenance} ${labels.inherited}`}
        </span>
        {field.approvalGated ? (
          <span data-testid="field-gated" className="text-meta text-muted">
            {labels.gatedDetail}
          </span>
        ) : null}
        {/* Only where there is an override to remove. Offering it on an
            inherited field would be offering an operation with no subject. */}
        {field.setHere && field.lockedBy === '' ? (
          <button
            type="button"
            data-testid="clear-override"
            data-path={field.path}
            aria-pressed={cleared}
            className="text-meta text-strong underline"
            onClick={() => {
              onToggleClear(field.path);
            }}
          >
            {cleared ? labels.cleared : labels.clear}
          </button>
        ) : null}
        {/* Only where the field is empty. An address somebody typed is a
            decision, and offering to replace it with a derived one puts a guess
            above a choice. */}
        {field.suggestedValue !== '' && current === '' && field.lockedBy === '' ? (
          <>
            <button
              type="button"
              data-testid="use-suggested"
              data-path={field.path}
              className="text-meta text-strong underline"
              onClick={() => {
                onEdit(field.path, field.suggestedValue);
              }}
            >
              {labels.useSuggested} {field.suggestedValue}
            </button>
            <span data-testid="suggested-because" className="text-meta text-muted">
              {field.suggestedBecause}
            </span>
          </>
        ) : null}
      </div>
    </div>
  );
}

interface ControlProps {
  readonly field: EditableField;
  readonly value: string;
  readonly disabled: boolean;
  readonly onEdit: (path: string, value: string) => void;
}

/** The control the catalogue asks for, and never one this console chose. */
function Control({ field, value, disabled, onEdit }: ControlProps): ReactNode {
  if (field.allowedValues !== null && field.allowedValues.length > 0) {
    return (
      <Select
        label={field.label}
        name={field.path}
        description={field.help}
        disabled={disabled}
        value={value}
        options={field.allowedValues.map((each) => ({ value: each, label: each }))}
        onValueChange={(next) => {
          onEdit(field.path, next);
        }}
      />
    );
  }

  if (field.type === 'boolean') {
    return (
      <Switch
        label={field.label}
        name={field.path}
        description={field.help}
        disabled={disabled}
        checked={value === 'true'}
        onCheckedChange={(next) => {
          onEdit(field.path, next ? 'true' : 'false');
        }}
      />
    );
  }

  const numeric = field.type === 'integer' || field.type === 'number';
  return (
    <Input
      label={field.label}
      name={field.path}
      description={field.help}
      disabled={disabled}
      type={numeric ? 'number' : 'text'}
      min={field.minimum ?? undefined}
      max={field.maximum ?? undefined}
      value={value}
      onValueChange={(next) => {
        onEdit(field.path, next);
      }}
    />
  );
}

interface ObjectListProps {
  readonly field: EditableField;
  readonly entries: readonly Entry[];
  readonly disabled: boolean;
  readonly labels: EditorLabels;
  readonly onEdit: (path: string, value: string) => void;
}

/**
 * An ordered list of objects: rows that can be edited, added, removed and moved.
 *
 * The whole list is posted on every change, because that is what the merge
 * does with a list — it replaces it entirely. A control that sent only the
 * touched entry would silently delete every other one, which is the failure
 * this shape of editor exists to make impossible rather than merely unlikely.
 *
 * **Position is drawn, because for these fields it is the value.** Routing
 * rules are first-match-wins with an explicit last word; specialists are
 * dispatched down the list. A row that could be moved but did not say where it
 * sat would be an editor for a set, offered for something that is not one.
 *
 * Moving is two buttons rather than a drag. A drag is unusable from a keyboard
 * without building a second interaction anyway, and the second interaction is
 * this one.
 */
function ObjectList({
  field,
  entries,
  disabled,
  labels,
  onEdit,
}: ObjectListProps): ReactNode {
  function write(next: readonly Entry[]): void {
    onEdit(field.path, JSON.stringify(next));
  }

  function change(index: number, item: ItemField, keyed: string): void {
    write(
      entries.map((entry, at) =>
        at === index ? { ...entry, [item.path]: itemTyped(item, keyed) } : entry,
      ),
    );
  }

  function move(index: number, by: number): void {
    const target = index + by;
    if (target < 0 || target >= entries.length) return;
    const next = [...entries];
    const [lifted] = next.splice(index, 1);
    if (lifted !== undefined) next.splice(target, 0, lifted);
    write(next);
  }

  return (
    <fieldset
      data-testid="object-list"
      data-path={field.path}
      className="flex flex-col gap-3 border-l border-subtle pl-3"
    >
      <legend className="text-meta text-strong">{field.label}</legend>
      {field.help === '' ? null : <p className="text-meta text-muted">{field.help}</p>}

      {entries.length === 0 ? (
        <p className="text-meta text-muted">{labels.emptyList}</p>
      ) : (
        entries.map((entry, index) => {
          const title = entryTitle(entry, field.itemFields);
          return (
            <div
              // The index is the identity here, and deliberately: an entry has no
              // stable key of its own until somebody names one, and keying on a
              // field the operator is in the middle of typing would remount the
              // control under their cursor.
              key={index}
              data-testid="list-entry"
              data-index={String(index)}
              className="flex flex-col gap-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                {/* Titled by what the entry is, not by where it sits. "Evaluated
                  1" read as the only heading is how an integration entry ends
                  up named after its evaluation order instead of "proxmox". */}
                {title === '' ? null : (
                  <span data-testid="entry-title" className="text-meta text-strong">
                    {title}
                  </span>
                )}
                <span
                  data-testid="entry-position"
                  className="text-micro uppercase text-muted"
                >
                  {labels.entryPosition} {index + 1}
                </span>
                <button
                  type="button"
                  data-testid="move-entry-up"
                  disabled={disabled || index === 0}
                  className="text-meta text-strong underline"
                  onClick={() => {
                    move(index, -1);
                  }}
                >
                  {labels.moveUp}
                </button>
                <button
                  type="button"
                  data-testid="move-entry-down"
                  disabled={disabled || index === entries.length - 1}
                  className="text-meta text-strong underline"
                  onClick={() => {
                    move(index, 1);
                  }}
                >
                  {labels.moveDown}
                </button>
                <button
                  type="button"
                  data-testid="remove-entry"
                  disabled={disabled}
                  className="text-meta text-danger underline"
                  onClick={() => {
                    write(entries.filter((_, at) => at !== index));
                  }}
                >
                  {labels.removeEntry}
                </button>
              </div>

              <div className="flex flex-col gap-2">
                {field.itemFields.map((item) => (
                  <div key={item.path} data-item-path={item.path}>
                    <ItemControl
                      item={
                        // A switch read on its own says only "Enabled" — of
                        // what is not in the sentence. Every other control in
                        // the entry sits under a title that answers that, but a
                        // screen reader visits controls one at a time. An entry
                        // with no name typed yet still has a position, which is
                        // the one fact about it that is never a guess.
                        item.type === 'boolean'
                          ? {
                              ...item,
                              label: `${title !== '' ? title : `${labels.entryPosition} ${String(index + 1)}`} — ${item.label}`,
                            }
                          : item
                      }
                      name={`${field.path}.${String(index)}.${item.path}`}
                      value={itemValue(entry, item)}
                      disabled={disabled}
                      onEdit={(keyed) => {
                        change(index, item, keyed);
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          );
        })
      )}

      <div>
        <button
          type="button"
          data-testid="add-entry"
          disabled={disabled}
          className="text-meta text-strong underline"
          onClick={() => {
            write([...entries, blankEntry(field.itemFields)]);
          }}
        >
          {labels.addEntry}
        </button>
      </div>
    </fieldset>
  );
}

interface ItemControlProps {
  readonly item: ItemField;
  readonly name: string;
  readonly value: string;
  readonly disabled: boolean;
  readonly onEdit: (value: string) => void;
}

/** One control inside a list entry, from the item schema and nothing else. */
function ItemControl({
  item,
  name,
  value,
  disabled,
  onEdit,
}: ItemControlProps): ReactNode {
  if (item.allowedValues !== null && item.allowedValues.length > 0) {
    return (
      <Select
        label={item.label}
        name={name}
        description={item.help}
        disabled={disabled}
        value={value}
        options={item.allowedValues.map((each) => ({ value: each, label: each }))}
        onValueChange={onEdit}
      />
    );
  }

  if (item.type === 'boolean') {
    return (
      <Switch
        label={item.label}
        name={name}
        description={item.help}
        disabled={disabled}
        checked={value === 'true'}
        onCheckedChange={(next) => {
          onEdit(next ? 'true' : 'false');
        }}
      />
    );
  }

  const numeric = item.type === 'integer' || item.type === 'number';
  return (
    <Input
      label={item.label}
      name={name}
      description={item.help}
      disabled={disabled}
      type={numeric ? 'number' : 'text'}
      min={item.minimum ?? undefined}
      max={item.maximum ?? undefined}
      value={value}
      onValueChange={onEdit}
    />
  );
}

interface DiffProps {
  readonly answer: Previewed;
  readonly labels: EditorLabels;
}

/** What the deployment says would happen, and the two things it says about inheritance. */
function Diff({ answer, labels }: DiffProps): ReactNode {
  const redundant = new Map(answer.redundant.map((each) => [each.path, each]));
  const reverts = new Map(answer.reverts.map((each) => [each.path, each]));

  return (
    <div className="flex flex-col gap-2">
      {answer.changes.length === 0 ? (
        <p className="text-muted text-small">{labels.empty}</p>
      ) : (
        <table className="w-full text-meta" data-testid="preview-changes">
          <thead>
            <tr>
              {[labels.setting, labels.before, labels.after].map((header) => (
                <th
                  key={header}
                  scope="col"
                  className="text-left text-micro uppercase text-muted pb-1"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {answer.changes.map((change) => (
              <tr
                key={change.path}
                data-testid="preview-change"
                data-path={change.path}
              >
                <td className="py-1 font-mono break-all">
                  {change.path}
                  {/* Inside the diff rather than beside it: the row is where
                      somebody is looking when they decide the change is worth
                      making. */}
                  {redundant.has(change.path) ? (
                    <span
                      data-testid="preview-redundant"
                      data-path={change.path}
                      className="block text-micro text-warning"
                    >
                      {labels.redundant} — {redundant.get(change.path)?.from}
                    </span>
                  ) : null}
                  {reverts.has(change.path) ? (
                    <span
                      data-testid="preview-revert"
                      data-path={change.path}
                      className="block text-micro text-muted"
                    >
                      {labels.reverts} {reverts.get(change.path)?.value} —{' '}
                      {reverts.get(change.path)?.from}
                    </span>
                  ) : null}
                </td>
                <td className="py-1 text-danger break-all">{change.before}</td>
                <td className="py-1 text-success break-all">{change.after}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {answer.locked.map((path) => (
          <span key={path} data-testid="locked" className="flex items-center gap-1">
            <Badge status="locked" />
            <span className="text-meta text-muted">
              {path} — {labels.lockedDetail}
            </span>
          </span>
        ))}
        {answer.requiresApproval || answer.gated.length > 0 ? (
          <span data-testid="gated" className="flex items-center gap-1">
            <Badge status="pending" />
            <span className="text-meta text-muted">{labels.gatedDetail}</span>
          </span>
        ) : null}
      </div>
    </div>
  );
}
