import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/header";
import { Footer } from "@/components/footer";

export const metadata: Metadata = {
  title: { default: "Równa ściana — małe naprawy, dobre decyzje", template: "%s | Równa ściana" },
  description: "Praktyczne poradniki o przygotowaniu ścian i poprawianiu błędów malowania. Ilustracje, konkretne kroki i źródła producentów.",
  robots: { index: false, follow: false },
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pl">
      <body id="top"><Header />{children}<Footer /></body>
    </html>
  );
}
