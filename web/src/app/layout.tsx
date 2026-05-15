import type { Metadata } from "next";
import {
  Poppins,
  Space_Grotesk,
  JetBrains_Mono,
  Anton,
  Bangers,
} from "next/font/google";
import "./globals.css";

// Match the marketing site exactly — Poppins for body, Space Grotesk
// for display, JetBrains Mono for accents. Same brand family.
const poppins = Poppins({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

// Display fonts the caption-style picker needs. Backend bundles the
// same .ttf files in /api/assets/fonts so ASS burn uses the matching
// family — this keeps the preview pixel-close to the rendered output.
const anton = Anton({
  variable: "--font-anton",
  subsets: ["latin"],
  weight: ["400"],
  display: "swap",
});
const bangers = Bangers({
  variable: "--font-bangers",
  subsets: ["latin"],
  weight: ["400"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Saurabh Tools",
  description: "Self-serve creator tools by Saurabh Bhayana & Team.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${poppins.variable} ${spaceGrotesk.variable} ${jetbrains.variable} ${anton.variable} ${bangers.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
