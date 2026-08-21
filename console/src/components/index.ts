/**
 * Every primitive the design system ships.
 *
 * This barrel is not a convenience. It is what the gallery coverage test reads:
 * a primitive exported here and absent from the gallery fails the suite by
 * name, so a component cannot be added without also being shown, documented and
 * screenshotted. Without a single list of "what exists", that test would have
 * nothing to compare the gallery against and coverage would be a claim.
 */

export { Button, IconButton, Link } from './action';
export { Badge, StatusChip, StatusDot } from './status';
export { Card, StatTile } from './surface';
export {
  Checkbox,
  Combobox,
  DateRange,
  Input,
  Radio,
  Select,
  Switch,
  Textarea,
} from './form';
export { ProgressBar, Skeleton, Spinner, Toast, Tooltip } from './feedback';
export { CodeBlock, DataList, DiffView, Table, Timeline } from './data';
export { Avatar, Breadcrumb, Pagination, TabLinks, Tabs } from './navigation';
export { ConfirmDestructive, Drawer, Modal } from './overlay';
export { EmptyState, ErrorState } from './state';
export { ContentWidth, PageHeader, Section, SplitLayout } from './layout';
