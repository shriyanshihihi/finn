"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./ui";

const TABS = [
  { href: "/", label: "Today", icon: "today" },
  { href: "/holdings", label: "Holdings", icon: "holdings" },
  { href: "/research", label: "Research", icon: "research" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

export function TabBar() {
  const path = usePathname();
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-bg/90 backdrop-blur-md">
      <div className="mx-auto grid max-w-[480px] grid-cols-4 pb-[env(safe-area-inset-bottom)]">
        {TABS.map((t) => {
          const on = t.href === "/" ? path === "/" : path.startsWith(t.href) || (t.href === "/research" && path.startsWith("/c/"));
          return (
            <Link key={t.href} href={t.href} className={`flex h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium ${on ? "text-ink" : "text-ink-3"}`}>
              <Icon name={t.icon} className="size-[22px]" />
              {t.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
