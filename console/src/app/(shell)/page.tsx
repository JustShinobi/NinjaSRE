import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AreaPage, areaMetadata } from '@/shell/area';

/** The overview: the first screen there is, and where a deep link lands by default. */
export function generateMetadata(): Promise<Metadata> {
  return areaMetadata('dashboard');
}

export default async function Page(): Promise<ReactNode> {
  return AreaPage({ id: 'dashboard' });
}
