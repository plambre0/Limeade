import type { Metadata } from "next";
import "./globals.css";
import ThemeRegistry from './ThemeRegistry';
import Header from './components/header';




export const metadata: Metadata = {
  title: "Scooter Site",
  description: "View info collected",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`antialiased overflow-hidden`}
      >
        <ThemeRegistry>
          <Header />
          {children}
        </ThemeRegistry>
      </body>
    </html>
  );
}
