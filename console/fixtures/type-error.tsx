// A component handed a number where its own props say string. The type checker
// has to name this file and this line, or it is not doing the job the gate
// bought it for.
import type { ReactNode } from 'react';

interface Props {
  readonly label: string;
}

function Chip({ label }: Props): ReactNode {
  return <span>{label}</span>;
}

export function Broken(): ReactNode {
  return <Chip label={42} />;
}
