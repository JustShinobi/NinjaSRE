import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { Breadcrumb } from '@/components/navigation';
import { PageHeader } from '@/components/layout';
import { message, type Locale } from '@/i18n/messages';
import { areaFor, trailFor, type Area } from './routes';
import { deployment, documentTitle } from './deployment';
import { requestLocale } from './request';

/**
 * The top of a page, and the metadata that names it.
 *
 * Both are here rather than in each route file for the same reason the guard is
 * above the router: the twelve routes would otherwise hold twelve copies of the
 * same four lines, and the copy that drifts is the one on the page nobody
 * opened this month.
 *
 * The document title carries the deployment as well as the page. An operator
 * with three deployments open has three tabs, and a tab that says only
 * "Approvals" is a tab they act in by mistake.
 */

/** The `<title>` for one area, ready to be returned from `generateMetadata`. */
export async function areaMetadata(id: string): Promise<Metadata> {
  const area = areaFor(id);
  const locale = await requestLocale();
  return {
    title: documentTitle(message(locale, area.title), deployment().name),
    description: message(locale, area.context),
  };
}

export interface AreaHeaderProps {
  readonly area: Area;
  readonly locale: Locale;
  /** Anything nested under the area, for a detail route that has a parent. */
  readonly nested?: readonly { readonly label: string; readonly href?: string }[];
  readonly actions?: ReactNode;
}

/** Title, subtitle, breadcrumb where the route is nested, and the page's actions. */
export function AreaHeader({
  area,
  locale,
  nested = [],
  actions,
}: AreaHeaderProps): ReactNode {
  const trail = trailFor(area, nested);
  const Icon = area.icon;
  return (
    <div data-testid="page-header" data-area={area.id}>
      {trail.length > 1 ? (
        <Breadcrumb
          label={message(locale, 'breadcrumb.label')}
          trail={trail.map((crumb) => ({
            label: crumb.translate ? message(locale, crumb.label) : crumb.label,
            ...(crumb.href === undefined ? {} : { href: crumb.href }),
          }))}
        />
      ) : null}
      <PageHeader
        title={message(locale, area.title)}
        context={message(locale, area.context)}
        icon={<Icon size="head" />}
        {...(actions === undefined ? {} : { actions })}
      />
    </div>
  );
}

/**
 * The body of an area that has no data screen yet.
 *
 * Feature 035 builds the frame; the screens inside it are the next feature. This
 * says so on the page rather than rendering an empty rectangle, because an empty
 * rectangle is indistinguishable from a page that failed to load.
 */
export async function AreaPage({ id }: { readonly id: string }): Promise<ReactNode> {
  const area = areaFor(id);
  const locale = await requestLocale();
  return (
    <>
      <AreaHeader area={area} locale={locale} />
      <p data-testid="area-pending" className="text-small text-muted">
        {message(locale, 'page.pending')}
      </p>
    </>
  );
}
