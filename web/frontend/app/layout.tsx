import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'EVRP Visual Lab',
  description: 'Trực quan hóa điều độ xe giao hàng điện thời gian thực',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="vi"><body>{children}</body></html>;
}
