'use client';

import type { ReactNode } from 'react';

import {
  Avatar,
  Badge,
  Breadcrumb,
  Button,
  Card,
  Checkbox,
  CodeBlock,
  Combobox,
  ConfirmDestructive,
  ContentWidth,
  DataList,
  DateRange,
  DiffView,
  Drawer,
  EmptyState,
  ErrorState,
  IconButton,
  Input,
  Link,
  Modal,
  PageHeader,
  Pagination,
  ProgressBar,
  Radio,
  Section,
  Select,
  Skeleton,
  Spinner,
  SplitLayout,
  StatTile,
  StatusDot,
  Switch,
  Table,
  Tabs,
  Textarea,
  Timeline,
  Toast,
  Tooltip,
} from '@/components';
import { BUTTON_VARIANTS, CONTROL_STATES } from '@/components/action';
import { SURFACE_STATES } from '@/components/surface';
import { ATTENTION_STATUSES, RESOURCE_STATUSES, RUN_STATUSES } from '@/design/status';
import { DatabaseIcon, ServerIcon, TrashIcon } from '@/design/icons';

/**
 * Every primitive, in every declared variant and every declared state.
 *
 * The gallery is the contract. The visual regression suite screenshots this
 * rather than the product screens, the accessibility audit walks this rather
 * than a page somebody remembered to check, and the coverage test compares this
 * against the barrel — so a primitive that is not here is not covered, and the
 * suite says so by name rather than going quietly green.
 *
 * Nothing here does anything. Every handler is a function that returns; this is
 * a specimen board, and a specimen that mutated state would make the screenshot
 * depend on the order the entries were rendered in.
 */

/** Specimen labels, which a real screen takes from the message catalogue. */
const PAGINATION_LABELS = {
  landmark: 'Pagination',
  previous: 'Previous',
  next: 'Next',
  position: 'Page 4 of 7',
};

const nothing = (): void => {
  /* A specimen does not act. */
};

/** One rendered specimen, with the words that say which one it is. */
export interface GalleryEntry {
  readonly id: string;
  readonly label: string;
  readonly node: ReactNode;
}

/** Every specimen of one primitive. */
export interface GalleryPrimitive {
  readonly name: string;
  readonly summary: string;
  readonly entries: readonly GalleryEntry[];
}

const TABLE_COLUMNS = [
  { key: 'volume', header: 'Volume', identifier: true },
  { key: 'node', header: 'Node' },
  { key: 'used', header: 'Used', numeric: true },
];

const TABLE_ROWS = [
  { id: '1', volume: 'local-lvm', node: 'pve02', used: '94.96%' },
  { id: '2', volume: 'local-zfs', node: 'pve01', used: '41.20%' },
];

export const GALLERY: readonly GalleryPrimitive[] = [
  {
    name: 'Button',
    summary:
      'Every variant and every state. The destructive one is distinct in words as well as colour.',
    entries: [
      ...BUTTON_VARIANTS.map((variant) => ({
        id: `button-${variant}`,
        label: variant,
        node: <Button variant={variant}>Reclaim 41 GiB</Button>,
      })),
      ...CONTROL_STATES.map((state) => ({
        id: `button-state-${state}`,
        label: state,
        node: (
          <Button variant="primary" state={state}>
            Approve
          </Button>
        ),
      })),
    ],
  },
  {
    name: 'IconButton',
    summary:
      'A control whose only content is a shape, and which therefore has to be named.',
    entries: CONTROL_STATES.map((state) => ({
      id: `icon-button-${state}`,
      label: state,
      node: (
        <IconButton label="Delete this backup" icon={<TrashIcon />} state={state} />
      ),
    })),
  },
  {
    name: 'Link',
    summary: 'Inside the deployment, and outside it.',
    entries: [
      {
        id: 'link-internal',
        label: 'internal',
        node: <Link href="/runs">Investigations</Link>,
      },
      {
        id: 'link-external',
        label: 'external',
        node: (
          <Link href="/docs" external>
            Documentation
          </Link>
        ),
      },
    ],
  },
  {
    name: 'Badge',
    summary:
      'Every status, each with its shape as well as its colour, and one nobody declared.',
    entries: [
      ...RUN_STATUSES,
      ...RESOURCE_STATUSES,
      ...ATTENTION_STATUSES,
      'quiesced',
    ].map((status) => ({
      id: `badge-${status}`,
      label: status,
      node: <Badge status={status} />,
    })),
  },
  {
    name: 'StatusDot',
    summary: 'The smallest status there is. Seven shapes, five roles.',
    entries: RESOURCE_STATUSES.map((status) => ({
      id: `dot-${status}`,
      label: status,
      node: <StatusDot status={status} standalone />,
    })),
  },
  {
    name: 'Card',
    summary: 'A titled panel, in each of the four things it can be showing.',
    entries: SURFACE_STATES.map((state) => ({
      id: `card-${state}`,
      label: state,
      node: (
        <Card
          title="Estate"
          state={state}
          emptyMessage="No resources are watched yet."
          errorMessage="The estate service refused the connection."
        >
          <p className="text-small">92 resources across 2 nodes.</p>
        </Card>
      ),
    })),
  },
  {
    name: 'StatTile',
    summary: 'One figure with its context line, which is mandatory.',
    entries: [
      {
        id: 'stat-ready',
        label: 'ready',
        node: (
          <StatTile
            label="Resources watched"
            value="92"
            context="2 nodes · 82 CT · 2 VM"
            icon={<ServerIcon />}
          />
        ),
      },
      {
        id: 'stat-trend',
        label: 'with a comparison',
        node: (
          <StatTile
            label="Healthy"
            value="85"
            context="↓ 4 since yesterday"
            trend="down"
          />
        ),
      },
      {
        id: 'stat-loading',
        label: 'loading',
        node: (
          <StatTile
            label="Mean time to detect"
            value="3m 48s"
            context="↑ 22% faster"
            state="loading"
          />
        ),
      },
    ],
  },
  {
    name: 'Input',
    summary: 'Labelled, described, and announced when it is wrong.',
    entries: [
      {
        id: 'input-default',
        label: 'default',
        node: <Input label="Node name" name="node" />,
      },
      {
        id: 'input-described',
        label: 'described',
        node: (
          <Input
            label="Node name"
            name="node2"
            description="As the cluster reports it."
          />
        ),
      },
      {
        id: 'input-error',
        label: 'error',
        node: (
          <Input label="Threshold" name="threshold" error="Must be a percentage." />
        ),
      },
      {
        id: 'input-disabled',
        label: 'disabled',
        node: <Input label="Cluster" name="cluster" disabled />,
      },
    ],
  },
  {
    name: 'Select',
    summary: 'A choice from a closed list.',
    entries: [
      {
        id: 'select-default',
        label: 'default',
        node: (
          <Select
            label="Severity"
            name="severity"
            options={[
              { value: 'critical', label: 'Critical' },
              { value: 'warning', label: 'Warning' },
            ]}
          />
        ),
      },
      {
        id: 'select-error',
        label: 'error',
        node: (
          <Select
            label="Severity"
            name="severity2"
            options={[{ value: 'critical', label: 'Critical' }]}
            error="Choose a severity."
          />
        ),
      },
    ],
  },
  {
    name: 'Textarea',
    summary: 'Several lines — a rejection reason, a note on an approval.',
    entries: [
      {
        id: 'textarea-default',
        label: 'default',
        node: <Textarea label="Reason" name="reason" />,
      },
      {
        id: 'textarea-error',
        label: 'error',
        node: (
          <Textarea label="Reason" name="reason2" error="A rejection needs a reason." />
        ),
      },
    ],
  },
  {
    name: 'Checkbox',
    summary: 'One independent yes or no.',
    entries: [
      {
        id: 'checkbox-default',
        label: 'default',
        node: <Checkbox label="Include recovery points" name="include" />,
      },
      {
        id: 'checkbox-disabled',
        label: 'disabled',
        node: <Checkbox label="Include recovery points" name="include2" disabled />,
      },
    ],
  },
  {
    name: 'Radio',
    summary: 'One choice out of several that share a name.',
    entries: [
      {
        id: 'radio-default',
        label: 'default',
        node: <Radio label="Partial reclaim" name="mode" value="partial" />,
      },
      {
        id: 'radio-disabled',
        label: 'disabled',
        node: <Radio label="Full reclaim" name="mode2" value="full" disabled />,
      },
    ],
  },
  {
    name: 'Switch',
    summary: 'A setting that takes effect when it is flipped, announced as a switch.',
    entries: [
      {
        id: 'switch-off',
        label: 'off',
        node: <Switch label="Pause autonomy" name="paused" />,
      },
      {
        id: 'switch-on',
        label: 'on',
        node: <Switch label="Pause autonomy" name="paused2" checked />,
      },
    ],
  },
  {
    name: 'Combobox',
    summary: 'A text field over a list, with the roles the pattern requires.',
    entries: [
      {
        id: 'combobox-default',
        label: 'default',
        node: (
          <Combobox
            label="Node"
            name="node"
            options={[
              { value: 'pve01', label: 'pve01' },
              { value: 'pve02', label: 'pve02' },
            ]}
          />
        ),
      },
    ],
  },
  {
    name: 'DateRange',
    summary: 'Two dates, because "from" and "to" are two questions.',
    entries: [
      {
        id: 'daterange-default',
        label: 'default',
        node: <DateRange label="Window" name="window" />,
      },
      {
        id: 'daterange-inverted',
        label: 'ends before it starts',
        node: (
          <DateRange label="Window" name="window2" from="2026-02-02" to="2026-02-01" />
        ),
      },
    ],
  },
  {
    name: 'Spinner',
    summary: 'Waiting, and what for.',
    entries: [
      {
        id: 'spinner',
        label: 'default',
        node: <Spinner label="Sweeping the estate" />,
      },
    ],
  },
  {
    name: 'Skeleton',
    summary: 'A reserved box, the exact size of what will land in it.',
    entries: [
      { id: 'skeleton-title', label: 'title', node: <Skeleton width="title" /> },
      { id: 'skeleton-line', label: 'line', node: <Skeleton width="line" /> },
      { id: 'skeleton-figure', label: 'figure', node: <Skeleton width="figure" /> },
    ],
  },
  {
    name: 'ProgressBar',
    summary: 'A bar and its number, changing role at each threshold.',
    entries: [
      {
        id: 'meter-0',
        label: 'zero',
        node: <ProgressBar label="local-zfs" value={0} />,
      },
      {
        id: 'meter-low',
        label: 'under the first threshold',
        node: <ProgressBar label="local-zfs" value={41.2} />,
      },
      {
        id: 'meter-warning',
        label: 'warning',
        node: <ProgressBar label="local-lvm" value={82} />,
      },
      {
        id: 'meter-danger',
        label: 'danger',
        node: <ProgressBar label="local-lvm" value={94.96} />,
      },
    ],
  },
  {
    name: 'Toast',
    summary: 'An outcome, announced — and never the only record of it.',
    entries: [
      {
        id: 'toast-success',
        label: 'success',
        node: (
          <Toast
            role="success"
            message="Reclaimed 41 GiB on local-lvm."
            recordedAt={{ href: '/audit', label: 'the audit trail' }}
            onDismiss={nothing}
          />
        ),
      },
      {
        id: 'toast-danger',
        label: 'danger',
        node: <Toast role="danger" message="The reclaim failed." onDismiss={nothing} />,
      },
    ],
  },
  {
    name: 'Tooltip',
    summary: 'A description on the control, on hover and on focus.',
    entries: [
      {
        id: 'tooltip',
        label: 'default',
        node: (
          <Tooltip text="The last successful sweep">
            <Button>Last swept 41s ago</Button>
          </Tooltip>
        ),
      },
    ],
  },
  {
    name: 'Table',
    summary: 'Rows, columns, a labelled cell for the stacked form, and an empty state.',
    entries: [
      {
        id: 'table-rows',
        label: 'populated',
        node: <Table caption="Storage" columns={TABLE_COLUMNS} rows={TABLE_ROWS} />,
      },
      {
        id: 'table-long-token',
        label: 'a very long single-token cell',
        node: (
          <Table
            caption="Storage"
            columns={TABLE_COLUMNS}
            rows={[{ id: '1', volume: 'a'.repeat(90), node: 'pve01', used: '1.00%' }]}
          />
        ),
      },
      {
        id: 'table-empty',
        label: 'empty',
        node: (
          <Table
            caption="Storage"
            columns={TABLE_COLUMNS}
            rows={[]}
            empty="No storage is watched."
          />
        ),
      },
    ],
  },
  {
    name: 'DataList',
    summary: 'Name and value pairs, with identifiers in monospace.',
    entries: [
      {
        id: 'datalist-default',
        label: 'default',
        node: (
          <DataList
            items={[
              { term: 'Target', value: 'local-lvm', identifier: true },
              { term: 'Rollback', value: 'Snapshot retained for 7 days' },
            ]}
          />
        ),
      },
      {
        id: 'datalist-empty',
        label: 'empty',
        node: <DataList items={[]} empty="Nothing was recorded for this run." />,
      },
    ],
  },
  {
    name: 'Timeline',
    summary: 'What happened, in order, with side effects said out loud.',
    entries: [
      {
        id: 'timeline-default',
        label: 'default',
        node: (
          <Timeline
            events={[
              {
                id: '1',
                kind: 'running',
                actor: 'detector',
                at: '09:01',
                summary: 'local-lvm passed 94%.',
              },
              {
                id: '2',
                kind: 'succeeded',
                actor: 'runner',
                at: '09:03',
                summary: 'Removed 41 GiB of expired volumes.',
                sideEffect: true,
              },
            ]}
          />
        ),
      },
      {
        id: 'timeline-empty',
        label: 'empty',
        node: <Timeline events={[]} empty="Nothing has happened in this run yet." />,
      },
    ],
  },
  {
    name: 'CodeBlock',
    summary: 'A payload, bounded rather than truncated.',
    entries: [
      {
        id: 'codeblock-short',
        label: 'short',
        node: <CodeBlock label="Response" content={'{\n  "quorum": 2\n}'} />,
      },
      {
        id: 'codeblock-bounded',
        label: 'bounded',
        node: (
          <CodeBlock
            label="Response"
            content={Array.from(
              { length: 400 },
              (_, index) => `line ${String(index)}`,
            ).join('\n')}
          />
        ),
      },
    ],
  },
  {
    name: 'DiffView',
    summary:
      'Two documents, with the change carried by sign and position as well as colour.',
    entries: [
      {
        id: 'diff-changed',
        label: 'changed',
        node: (
          <DiffView
            label="Proposed configuration"
            before={'retention: 7\nquorum: 2'}
            after={'retention: 14\nquorum: 2'}
          />
        ),
      },
      {
        id: 'diff-same',
        label: 'no difference',
        node: (
          <DiffView
            label="Proposed configuration"
            before="quorum: 2"
            after="quorum: 2"
          />
        ),
      },
    ],
  },
  {
    name: 'Tabs',
    summary: 'Roving focus, arrow keys, and a wrap at each end.',
    entries: [
      {
        id: 'tabs-default',
        label: 'default',
        node: (
          <Tabs
            label="Investigation"
            selected="transcript"
            onSelect={nothing}
            tabs={[
              { id: 'transcript', label: 'Transcript' },
              { id: 'evidence', label: 'Evidence' },
            ]}
          >
            <p className="text-small">The transcript.</p>
          </Tabs>
        ),
      },
    ],
  },
  {
    name: 'Breadcrumb',
    summary: 'Where this page sits, with the current page not linked to itself.',
    entries: [
      {
        id: 'breadcrumb-default',
        label: 'default',
        node: (
          <Breadcrumb
            trail={[
              { href: '/', label: 'Operate' },
              { href: '/incidents', label: 'Incidents' },
              { label: 'Quorum margin is zero' },
            ]}
            label="Breadcrumb"
          />
        ),
      },
    ],
  },
  {
    name: 'Pagination',
    summary: 'The edge it is already at is disabled rather than hidden.',
    entries: [
      {
        id: 'pagination-first',
        label: 'first page',
        node: (
          <Pagination page={1} pages={7} onPage={nothing} labels={PAGINATION_LABELS} />
        ),
      },
      {
        id: 'pagination-middle',
        label: 'middle',
        node: (
          <Pagination page={4} pages={7} onPage={nothing} labels={PAGINATION_LABELS} />
        ),
      },
      {
        id: 'pagination-last',
        label: 'last page',
        node: (
          <Pagination page={7} pages={7} onPage={nothing} labels={PAGINATION_LABELS} />
        ),
      },
    ],
  },
  {
    name: 'Avatar',
    summary: 'Initials, with the name available to anybody who cannot see them.',
    entries: [
      {
        id: 'avatar-person',
        label: 'a person',
        node: <Avatar name="Priya Raman" unknownLabel="Unknown person" />,
      },
      {
        id: 'avatar-service',
        label: 'a service',
        node: <Avatar name="runner" unknownLabel="Unknown person" />,
      },
    ],
  },
  {
    name: 'Modal',
    summary:
      'A confirmation, and nothing else. Focus goes in, stays in, and comes back.',
    entries: [
      {
        id: 'modal-open',
        label: 'open',
        node: (
          <Modal open title="Confirm the reclaim" onClose={nothing} closeLabel="Close">
            <p className="text-small">41 GiB will be removed from local-lvm.</p>
          </Modal>
        ),
      },
    ],
  },
  {
    name: 'Drawer',
    summary: 'Detail beside the thing it is about, so the context stays visible.',
    entries: [
      {
        id: 'drawer-open',
        label: 'open',
        node: (
          <Drawer open title="Evidence" onClose={nothing} closeLabel="Close">
            <p className="text-small">The last sweep of local-lvm.</p>
          </Drawer>
        ),
      },
    ],
  },
  {
    name: 'ConfirmDestructive',
    summary: 'The confirmation a destructive action requires, naming the target.',
    entries: [
      {
        id: 'confirm-destructive',
        label: 'open',
        node: (
          <ConfirmDestructive
            open
            target="local-lvm on pve02"
            action="Reclaim 41 GiB"
            consequence="One of the items is a recovery point."
            labels={{ close: 'Close', cancel: 'Cancel' }}
            onConfirm={nothing}
            onCancel={nothing}
          />
        ),
      },
    ],
  },
  {
    name: 'EmptyState',
    summary:
      'Icon, heading, a sentence saying what would be here, and an action. All four required.',
    entries: [
      {
        id: 'empty-state',
        label: 'default',
        node: (
          <EmptyState
            icon={<DatabaseIcon size="empty" />}
            heading="No resources yet"
            body="Connect an infrastructure source and the estate populates itself within a minute. Nothing here is entered by hand."
            action={{ label: 'Connect a source', onSelect: nothing }}
          />
        ),
      },
    ],
  },
  {
    name: 'ErrorState',
    summary:
      'Scoped to its panel: names the dependency, says the page is unaffected, retries this panel.',
    entries: [
      {
        id: 'error-state',
        label: 'default',
        node: (
          <ErrorState
            heading="Could not reach this source"
            dependency="metrics.internal.invalid"
            detail="refused the connection. The rest of this page is unaffected."
            retryLabel="Retry this panel"
            onRetry={nothing}
          />
        ),
      },
    ],
  },
  {
    name: 'PageHeader',
    summary: 'The one first-level heading on a page, with its context beneath.',
    entries: [
      {
        id: 'page-header',
        label: 'default',
        node: (
          <PageHeader
            icon={<ServerIcon size="head" />}
            title="Cluster HAL9000"
            context="2 nodes · 84 guests · last swept 41s ago"
            actions={<Button variant="primary">Sweep now</Button>}
          />
        ),
      },
    ],
  },
  {
    name: 'Section',
    summary:
      'A named division of a page, which is a landmark rather than a heading and a gap.',
    entries: [
      {
        id: 'section',
        label: 'default',
        node: (
          <Section title="Attention" description="Ordered by severity, then by age.">
            <p className="text-small">Three things need a person.</p>
          </Section>
        ),
      },
    ],
  },
  {
    name: 'SplitLayout',
    summary:
      'A primary surface with a context rail that wraps below rather than shrinking.',
    entries: [
      {
        id: 'split-layout',
        label: 'default',
        node: (
          <SplitLayout
            primary={<Card title="The investigation">The transcript.</Card>}
            secondary={<Card title="Context">The estate around it.</Card>}
          />
        ),
      },
    ],
  },
  {
    name: 'ContentWidth',
    summary: 'The measure cap, so a sentence does not run the width of a wide monitor.',
    entries: [
      {
        id: 'content-width',
        label: 'default',
        node: (
          <ContentWidth>
            <p className="text-small">Everything on a page sits inside this.</p>
          </ContentWidth>
        ),
      },
    ],
  },
];

/** Every primitive the gallery shows, by name. */
export function galleryPrimitiveNames(): readonly string[] {
  return GALLERY.map((primitive) => primitive.name);
}
