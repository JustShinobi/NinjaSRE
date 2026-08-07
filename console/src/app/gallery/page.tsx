'use client';

import type { ReactNode } from 'react';

import { ContentWidth, PageHeader, Section } from '@/components/layout';
import { GALLERY } from '@/gallery/registry';
import { ColourSection, ScaleSection } from '@/gallery/sections';
import { LayersIcon } from '@/design/icons';

/**
 * The gallery: every primitive, every variant, every state, on one route.
 *
 * It is the contract rather than a showcase. The visual regression suite
 * screenshots this instead of the product screens, because a product screen
 * shows a primitive in the one state that screen happened to be in — and the
 * states nobody screenshotted are exactly the ones that break. The
 * accessibility audit walks this for the same reason.
 *
 * It is deliberately not reachable from the product. There is no navigation
 * entry, nothing links to it, and it says at the top what it is. A design
 * gallery an operator can wander into during an incident is a page that wastes
 * somebody's three in the morning.
 */
export default function GalleryPage(): ReactNode {
  return (
    <main data-testid="gallery" className="py-6">
      <ContentWidth>
        <PageHeader
          icon={<LayersIcon size="head" />}
          title="Design system"
          context="Every primitive, every variant, every state. Not part of the console — this route exists so the suite has something to screenshot and audit."
        />

        <Section
          title="Colour"
          description="Roles, never hues, with every pair measured."
        >
          <ColourSection theme="light" />
        </Section>

        <Section
          title="Scales"
          description="Type, spacing, radius, border, duration and icon."
        >
          <ScaleSection />
        </Section>

        {GALLERY.map((primitive) => (
          <Section
            key={primitive.name}
            title={primitive.name}
            description={primitive.summary}
          >
            <ul className="flex flex-wrap items-start gap-4">
              {primitive.entries.map((entry) => (
                <li
                  key={entry.id}
                  data-entry={entry.id}
                  className="flex flex-col gap-2 min-w-0 max-w-full"
                >
                  <span className="text-micro uppercase text-muted">{entry.label}</span>
                  {entry.node}
                </li>
              ))}
            </ul>
          </Section>
        ))}
      </ContentWidth>
    </main>
  );
}
