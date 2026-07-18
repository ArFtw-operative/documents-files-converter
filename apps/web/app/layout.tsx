import type { Metadata } from "next";
import "./styles.css";
import "./rich.css";

export const metadata: Metadata = {title: "ConvertVault", description: "Private file conversion and document library"};
export default function Layout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="en"><body>{children}</body></html>;
}
