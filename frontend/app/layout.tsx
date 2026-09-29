import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Pulse — Autonomous Research",
  description: "Ask a question. Get a fully cited research report.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body>
        <header className="topbar">
          <div className="container topbar-inner">
            <a href="/" className="wordmark" aria-label="Pulse home">
              <span className="wordmark-dot" aria-hidden="true" />
              Pulse
            </a>
            <nav className="topnav" aria-label="Main">
              <a href="/">Research</a>
              <a href="/#recent">Recent</a>
            </nav>
          </div>
        </header>
        {children}
        <div className="container">
          <footer className="page-footer">
            <span>Autonomous research with verifiable citations</span>
            <span>Planning → Searching → Reading → Writing</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
