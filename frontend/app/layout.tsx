import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Bank Assistant · Control Center",
  description: "Human review of simulated banking actions.",
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
