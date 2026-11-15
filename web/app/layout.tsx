import type { Metadata, Viewport } from "next";
import "./globals.css";
import { Providers } from "@/components/Providers";
import { TabBar } from "@/components/TabBar";

export const metadata: Metadata = {
  title: "FINN",
  description: "Only what should change your mind about a holding.",
  appleWebApp: { capable: true, title: "FINN", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0c0c0d" },
    { media: "(prefers-color-scheme: light)", color: "#f6f4ef" },
  ],
};

// pick the theme before first paint, so there is no flash
const themeScript = `try{var s=JSON.parse(localStorage.getItem('finn.settings.v1')||'{}').theme||'system';var d=s==='dark'||(s==='system'&&matchMedia('(prefers-color-scheme: dark)').matches);document.documentElement.dataset.theme=d?'dark':'light'}catch(e){}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <Providers>
          <main className="mx-auto min-h-dvh max-w-[480px] px-4 pb-[calc(88px+env(safe-area-inset-bottom))] pt-[env(safe-area-inset-top)]">
            {children}
          </main>
          <TabBar />
        </Providers>
      </body>
    </html>
  );
}
