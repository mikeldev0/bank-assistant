import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Bank Assistant · Centro de control",
  description: "Revisión humana de acciones bancarias simuladas.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
