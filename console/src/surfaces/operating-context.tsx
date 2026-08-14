'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';

import { Button, Link } from '@/components/action';
import { Input, Textarea } from '@/components/form';
import { Badge } from '@/components/status';

/**
 * Writing down what this environment is, and reading the prompt it becomes.
 *
 * **The preview is the prompt.** Everywhere else in this console a preview is a
 * diff of values; here the effect of saving *is* text, and what comes back is
 * the exact string the next investigation's system prompt will carry —
 * assembled by the deployment, from the same function the runtime uses. The save
 * control does not exist until a preview of the current text has come back, and
 * any further edit removes it again. That has to be a client guarantee: no API
 * can know whether a person read what they are about to send to a model.
 *
 * **Nothing here is assembled.** The console does not join the shipped prompt to
 * the sections, does not merge an ancestor's section with this node's, and does
 * not count tokens. All three are the deployment's answers, rendered. A console
 * that counted its own tokens would show a budget the write path disagrees with,
 * which reads as the platform being arbitrary about length.
 *
 * **Facts, not instructions, and the interface says so.** The distinction is
 * the whole difference between text that improves reasoning and text that
 * quietly becomes a procedure nobody reviewed. It is stated in the copy and the
 * two right homes for an instruction are linked, because "do not write that
 * here" without "write it there" is advice nobody can follow.
 *
 * **A section carrying only whitespace is how an inherited one is silenced.**
 * That is different from clearing the override, which puts the ancestor's text
 * back — so both are offered and the copy names which is which.
 */

/** Where every write goes. The console's own process, forwarding once. */
export const CONTEXT_ENDPOINT = '/api/operating-context';

export interface ContextSection {
  readonly name: string;
  readonly body: string;
  /** The node supplying this section, or empty where nothing does yet. */
  readonly provenance: string;
}

export interface OperatingContextLabels {
  readonly section: string;
  readonly body: string;
  readonly provenance: string;
  readonly budget: string;
  readonly budgetUsed: string;
  /** What happens past the budget — refused, not shortened. Said before anyone is near it. */
  readonly budgetConsequence: string;
  readonly overBudget: string;
  readonly addSection: string;
  /** Why "Add a section" is disabled, while nothing has been typed to name it yet. */
  readonly addSectionDisabledReason: string;
  readonly sectionName: string;
  readonly remove: string;
  readonly factNotInstruction: string;
  readonly runbooks: string;
  readonly policy: string;
  readonly previewTitle: string;
  readonly previewLead: string;
  readonly submit: string;
  /** Why "Show me the prompt" is disabled, while there is nothing new to show. */
  readonly previewDisabledReason: string;
  readonly previewing: string;
  readonly previewFirst: string;
  readonly save: string;
  readonly saving: string;
  readonly saved: string;
  readonly failed: string;
  readonly unreachable: string;
  readonly roles: string;
  readonly templateUse: string;
  /** What the starting document actually is, for the button that offers it. */
  readonly templateLead: string;
}

export interface OperatingContextEditorProps {
  readonly nodeId: string;
  /** What resolves at this node today, ancestors included. */
  readonly sections: readonly ContextSection[];
  /** The starting document the deployment derived, offered where nothing is written. */
  readonly template: readonly ContextSection[];
  readonly tokensUsed: number;
  readonly tokenBudget: number;
  /** The roles this text is sent to, as the deployment names them. */
  readonly roles: readonly string[];
  readonly labels: OperatingContextLabels;
  /** Whether this viewer may write. A reader gets the text and no controls. */
  readonly writable: boolean;
}

interface Previewed {
  readonly prompt: string;
  readonly tokensUsed: number;
  readonly overBudget: boolean;
  readonly accepted: boolean;
  readonly errors: readonly { readonly path: string; readonly message: string }[];
}

function text(record: unknown, name: string): string {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'string' ? found : '';
}

function number(record: unknown, name: string): number {
  const found: unknown = Reflect.get(Object(record), name);
  return typeof found === 'number' && Number.isFinite(found) ? found : 0;
}

function previewedFrom(body: unknown): Previewed {
  const errors: unknown = Reflect.get(Object(body), 'errors');
  return {
    prompt: text(body, 'prompt'),
    tokensUsed: number(body, 'tokens_used'),
    overBudget: Reflect.get(Object(body), 'over_budget') === true,
    accepted: Reflect.get(Object(body), 'accepted') !== false,
    errors: (Array.isArray(errors) ? errors : []).map((entry) => ({
      path: text(entry, 'path'),
      message: text(entry, 'message'),
    })),
  };
}

/** Write the facts, read the prompt they become, then save it. */
export function OperatingContextEditor({
  nodeId,
  sections,
  template,
  tokensUsed,
  tokenBudget,
  roles,
  labels,
  writable,
}: OperatingContextEditorProps): ReactNode {
  const [bodyFor, setBodyFor] = useState<Readonly<Record<string, string>>>({});
  const [added, setAdded] = useState<readonly string[]>([]);
  const [naming, setNaming] = useState('');
  const [answer, setAnswer] = useState<Previewed | null>(null);
  const [previewedDocument, setPreviewedDocument] = useState('');
  const [busy, setBusy] = useState('');
  const [saved, setSaved] = useState(false);
  const [failure, setFailure] = useState('');

  const rows: readonly ContextSection[] = [
    ...sections,
    ...added.map((name) => ({ name, body: '', provenance: '' })),
  ];
  const document: Readonly<Record<string, string>> = Object.fromEntries(
    rows.map((row) => [row.name, bodyFor[row.name] ?? row.body]),
  );
  const serialised = JSON.stringify(document);
  const edited = rows.some((row) => (bodyFor[row.name] ?? row.body) !== row.body);
  const current = answer !== null && serialised === previewedDocument;
  // Neither a pending edit nor an existing preview to show: there is nothing
  // new for a preview to say yet, and the button explains exactly that.
  const previewBlocked = !edited && !current;

  async function ask(operation: string, payload: unknown): Promise<unknown> {
    setFailure('');
    let response: Response;
    try {
      response = await fetch(CONTEXT_ENDPOINT, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ nodeId, operation, payload }),
      });
    } catch {
      setFailure(labels.unreachable);
      return null;
    }
    const body: unknown = await response.json().catch(() => ({}));
    if (!response.ok) {
      const reason: unknown = Reflect.get(Object(body), 'reason');
      setFailure(typeof reason === 'string' && reason !== '' ? reason : labels.failed);
      return null;
    }
    return Reflect.get(Object(body), 'answer');
  }

  async function preview(): Promise<void> {
    setBusy('preview');
    const found = await ask('preview', { sections: document });
    setBusy('');
    if (found === null) return;
    setAnswer(previewedFrom(found));
    setPreviewedDocument(serialised);
  }

  async function save(): Promise<void> {
    setBusy('save');
    // The document the preview was taken *of*, not the one on screen. They are
    // the same string or the save control is not rendered, and sending the
    // second would make that guarantee a coincidence.
    const previewedSections = JSON.parse(previewedDocument) as Record<string, string>;
    const found = await ask('save', {
      patch: { agents: { operating_context: { sections: previewedSections } } },
    });
    setBusy('');
    if (found === null) return;
    setSaved(true);
    setAnswer(null);
    setPreviewedDocument('');
  }

  function edit(name: string, next: string): void {
    setSaved(false);
    setBodyFor((was) => ({ ...was, [name]: next }));
  }

  function startFromTemplate(): void {
    setSaved(false);
    setAdded(
      template
        .filter((row) => !rows.some((held) => held.name === row.name))
        .map((row) => row.name),
    );
    setBodyFor((was) => ({
      ...was,
      ...Object.fromEntries(template.map((row) => [row.name, row.body])),
    }));
  }

  // The deployment's count for the pending text once it has answered, and the
  // resolved node's until then. Never one this console worked out: a budget the
  // write path disagrees with reads as the platform being arbitrary.
  const shown = current ? answer : null;
  const spent = shown === null ? tokensUsed : shown.tokensUsed;
  const over = spent > tokenBudget;

  return (
    <div data-testid="operating-context-editor" className="flex flex-col gap-4">
      {/* Said before the first field, because it is the rule that decides what
          belongs here at all, and after the fact it is only a correction. */}
      <p data-testid="fact-not-instruction" className="text-meta text-muted">
        {labels.factNotInstruction} <Link href="/knowledge">{labels.runbooks}</Link>
        {' · '}
        <Link href="/autonomy">{labels.policy}</Link>
      </p>

      <p className="flex flex-wrap items-center gap-2 text-meta text-muted">
        <span>{labels.roles}</span>
        {roles.map((role) => (
          <Badge key={role} status={role} />
        ))}
      </p>

      <p
        data-testid="context-budget"
        className={`text-meta tabular-nums ${over ? 'text-danger' : 'text-muted'}`}
      >
        {labels.budget}{' '}
        {labels.budgetUsed
          .replace('{used}', String(spent))
          .replace('{budget}', String(tokenBudget))}
      </p>
      {/* Said before anyone is near the limit, not only once they have crossed
          it: what happens past the budget is a refusal, never a silent cut. */}
      <p data-testid="context-budget-consequence" className="text-meta text-muted">
        {labels.budgetConsequence}
      </p>
      {over ? (
        <p
          data-testid="context-over-budget"
          role="status"
          className="text-meta text-danger"
        >
          {labels.overBudget}
        </p>
      ) : null}

      {rows.map((row) => (
        <div
          key={row.name}
          data-testid="context-section"
          data-section={row.name}
          className="flex flex-col gap-1"
        >
          {/* Which level said it. Without this, a section changed at the wrong
              level looks like a console that ignored the change. Beside the
              name rather than under it, and the name is the field's own label
              rather than a heading repeated above one. */}
          <span
            data-testid="section-provenance"
            data-section={row.name}
            className="flex flex-wrap items-center gap-2"
          >
            <span className="text-meta text-muted">{labels.provenance}</span>
            <Badge status={row.provenance === '' ? 'unset' : row.provenance} />
          </span>
          {writable ? (
            <Textarea
              label={row.name}
              name={`section-${row.name}`}
              rows={4}
              value={bodyFor[row.name] ?? row.body}
              onValueChange={(next) => {
                edit(row.name, next);
              }}
            />
          ) : (
            <>
              <span className="text-meta text-muted">{row.name}</span>
              <p className="text-small whitespace-pre-wrap">{row.body}</p>
            </>
          )}
        </div>
      ))}

      {writable ? (
        <div className="flex flex-wrap items-end gap-3">
          <Input
            label={labels.sectionName}
            name="new-section"
            value={naming}
            onValueChange={setNaming}
          />
          <Button
            data-testid="add-section"
            state={naming.trim() === '' ? 'disabled' : 'default'}
            title={naming.trim() === '' ? labels.addSectionDisabledReason : undefined}
            onClick={() => {
              const name = naming.trim();
              if (name === '') return;
              setAdded((was) => (was.includes(name) ? was : [...was, name]));
              setNaming('');
              setSaved(false);
            }}
          >
            {labels.addSection}
          </Button>
          {template.length === 0 ? null : (
            // The label alone answers "start from what?"; the title carries the
            // longer answer (what it was derived from, and that nothing is
            // written until save) for whoever hovers rather than guesses.
            <Button
              data-testid="use-template"
              title={labels.templateLead}
              onClick={() => {
                startFromTemplate();
              }}
            >
              {labels.templateUse}
            </Button>
          )}
        </div>
      ) : null}

      {writable ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            data-testid="ask-context-preview"
            state={
              busy === 'preview' ? 'loading' : previewBlocked ? 'disabled' : 'default'
            }
            title={previewBlocked ? labels.previewDisabledReason : undefined}
            onClick={() => {
              void preview();
            }}
          >
            {busy === 'preview' ? labels.previewing : labels.submit}
          </Button>
        </div>
      ) : null}

      {answer === null || !current ? null : (
        <div data-testid="context-preview" className="flex flex-col gap-2">
          <p className="text-small">{labels.previewTitle}</p>
          <p className="text-meta text-muted">{labels.previewLead}</p>
          {answer.errors.length === 0 ? null : (
            <ul
              data-testid="context-errors"
              className="flex flex-col gap-1 text-meta text-danger"
            >
              {answer.errors.map((error) => (
                <li key={error.path} data-path={error.path}>
                  <span className="font-mono break-all">{error.path}</span>{' '}
                  {error.message}
                </li>
              ))}
            </ul>
          )}
          {answer.accepted ? (
            <pre
              data-testid="context-prompt"
              className="rounded-2 bg-surface-sunken p-3 text-meta whitespace-pre-wrap break-words max-h-96 overflow-y-auto"
            >
              {answer.prompt}
            </pre>
          ) : null}

          {/* Below the prompt, never beside the form: what has to have been read
              is what the model will be sent. */}
          {answer.accepted ? (
            <span className="flex items-center gap-3">
              <Button
                data-testid="save-context"
                state={busy === 'save' ? 'loading' : 'default'}
                onClick={() => {
                  void save();
                }}
              >
                {busy === 'save' ? labels.saving : labels.save}
              </Button>
            </span>
          ) : null}
        </div>
      )}

      {answer === null && edited ? (
        <span data-testid="context-preview-first" className="text-meta text-muted">
          {labels.previewFirst}
        </span>
      ) : null}

      {saved ? (
        <span data-testid="context-saved" className="text-meta text-success">
          {labels.saved}
        </span>
      ) : null}
      {failure === '' ? null : (
        <span data-testid="context-failure" className="text-meta text-danger">
          {failure}
        </span>
      )}
    </div>
  );
}
