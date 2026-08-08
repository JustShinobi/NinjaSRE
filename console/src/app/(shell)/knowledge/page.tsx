import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AreaPage, areaMetadata } from '@/shell/area';

/** One area of the product. What it is, and what it is for, come from the manifest. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('knowledge');
}

export default async function Page(): Promise<ReactNode> {
  return AreaPage({ id: 'knowledge' });
}
