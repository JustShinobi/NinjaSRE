'use client';

import type { ReactNode } from 'react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

import { Button } from '@/components/action';
import { ProgressBar } from '@/components/feedback';
import { message, type Locale } from '@/i18n/messages';
import { CONFIG_ENDPOINT } from './model';

/**
 * Five screens over the top of the product, and a `Skip` that is never further
 * away than the `Next`.
 *
 * Over the top rather than instead of: the dashboard is behind this, rendered
 * and readable, so the tutorial teaches *while* the product is on screen rather
 * than in place of it. That is the whole difference between an overlay and the
 * onboarding wall this feature was originally specified as.
 *
 * **Dismissal is a fact about the deployment, not about the browser.** It is
 * written through the ordinary configuration path, because a `localStorage`
 * flag would show the whole thing again on the second machine, to the same
 * person, on the same deployment. It is also only ever *shown* while the setup
 * checklist has something outstanding, so a dismissal that failed to save can
 * never trap a configured deployment behind an overlay — the two rules
 * together mean the worst case is seeing it twice.
 *
 * There is no animation. The panel appears; a reader who has
 * `prefers-reduced-motion` set and a reader who has not see the same thing,
 * which is a stronger claim than honouring the preference and the reason
 * nothing here declares a duration at all.
 */

/** Where the dismissal is recorded, at the viewer's own node. */
export const TUTORIAL_SETTING = 'surfaces.console.tutorial_dismissed';

/** Where the final slide's invitation actually goes. */
const SETUP_PATH = '/first-run';

/** The five slides, by the number their catalogue keys carry. */
export const SLIDES: readonly number[] = [1, 2, 3, 4, 5];

/**
 * Whether `values` — a node's effective configuration — records the dismissal.
 *
 * The effective document is nested the way the schema is, so the dotted
 * setting is walked one segment at a time. Read as one flat key it would
 * answer false forever, which is exactly the overlay that never stops coming
 * back.
 */
export function tutorialDismissed(values: unknown): boolean {
  let cursor: unknown = values;
  for (const segment of TUTORIAL_SETTING.split('.')) {
    cursor = Reflect.get(Object(cursor), segment);
  }
  return cursor === true;
}

/**
 * The dismissal as the nested document the deployment validates.
 *
 * Built from the same dotted setting the read walks, so the two halves of the
 * persistence cannot name different fields. A flat dotted key would be a field
 * the closed schema has never heard of, and the write would be refused.
 */
function dismissalPatch(): Record<string, unknown> {
  let patch: unknown = true;
  for (const segment of [...TUTORIAL_SETTING.split('.')].reverse()) {
    patch = { [segment]: patch };
  }
  return patch as Record<string, unknown>;
}

export interface TutorialProps {
  readonly locale: Locale;
  /** The node the dismissal is written at. Empty when the viewer resolves to none. */
  readonly nodeId: string;
}

/** The dismissable tutorial, over a dashboard that is rendered behind it. */
export function Tutorial({ locale, nodeId }: TutorialProps): ReactNode {
  const router = useRouter();
  const [slide, setSlide] = useState(0);
  const [closed, setClosed] = useState(false);

  function close(): void {
    // Closed here and now. The write below is what stops it coming back
    // tomorrow, and a person who dismissed something must not have to wait for
    // a round trip to find out whether they did.
    setClosed(true);
    if (nodeId === '') return;
    void fetch(CONFIG_ENDPOINT, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ nodeId, patch: dismissalPatch() }),
    }).catch(() => undefined);
  }

  if (closed) return null;

  const last = slide === SLIDES.length - 1;
  const number = String(SLIDES[slide] ?? 1);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={message(locale, 'tutorial.title')}
      data-testid="tutorial"
      data-slide={number}
      className="fixed inset-0 z-20 flex items-center justify-center bg-sunken/80 p-5"
    >
      <div className="flex w-prose max-w-full flex-col gap-4 rounded-3 edge border-border bg-raised p-5 shadow-2">
        <div className="flex items-center gap-3">
          <p className="text-meta text-muted" data-testid="tutorial-progress">
            {message(locale, 'tutorial.progress', {
              step: String(slide + 1),
              total: String(SLIDES.length),
            })}
          </p>
          {/* Visible from the first slide and the same size as the control
              beside it. A skip somebody has to hunt for is a skip that was not
              offered. */}
          <span className="ml-auto">
            <Button data-testid="tutorial-skip" onClick={close}>
              {message(locale, 'tutorial.skip')}
            </Button>
          </span>
        </div>

        <ProgressBar
          label={message(locale, 'tutorial.progress', {
            step: String(slide + 1),
            total: String(SLIDES.length),
          })}
          value={((slide + 1) / SLIDES.length) * 100}
        />

        <h2 className="text-strong">
          {message(
            locale,
            `tutorial.slide.${number}.title` as 'tutorial.slide.1.title',
          )}
        </h2>
        <p className="text-small text-muted">
          {message(locale, `tutorial.slide.${number}.body` as 'tutorial.slide.1.body')}
        </p>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            data-testid="tutorial-back"
            state={slide === 0 ? 'disabled' : 'default'}
            onClick={() => {
              setSlide((was) => Math.max(0, was - 1));
            }}
          >
            {message(locale, 'tutorial.back')}
          </Button>
          <Button
            variant="primary"
            data-testid="tutorial-next"
            onClick={() => {
              if (last) {
                // The final slide promises a beginning, so pressing it is two
                // things: the dismissal every other exit records, and the
                // navigation the wording offers.
                close();
                router.push(SETUP_PATH);
              } else setSlide((was) => Math.min(SLIDES.length - 1, was + 1));
            }}
          >
            {message(locale, last ? 'tutorial.done' : 'tutorial.next')}
          </Button>
        </div>
      </div>
    </div>
  );
}
