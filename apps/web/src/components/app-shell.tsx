"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { clearSession, type Session } from "@/lib/auth";
import { useSession } from "@/lib/user";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export const NAV = [
  { href: "/", label: "Overview" },
  { href: "/resume", label: "Resume" },
  { href: "/jobs", label: "Job analysis" },
  { href: "/roadmap", label: "Roadmap" },
  { href: "/applications", label: "Applications" },
  { href: "/github", label: "GitHub evidence" },
  { href: "/assessments", label: "Assessments" },
  { href: "/mentor", label: "Mentor" },
] as const;

function ModeBadge() {
  const [state, setState] = useState<"loading" | "demo" | "live" | "down">("loading");
  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((h) => !cancelled && setState(h.demo_mode ? "demo" : "live"))
      .catch(() => !cancelled && setState("down"));
    return () => {
      cancelled = true;
    };
  }, []);
  if (state === "loading") return <Badge>Checking API...</Badge>;
  if (state === "down") return <Badge tone="danger">API unreachable</Badge>;
  if (state === "demo") return <Badge tone="warning">Demo mode: fixture data, no external services</Badge>;
  return <Badge tone="success">Live mode</Badge>;
}

function UserBar({ session }: { session: Session }) {
  const router = useRouter();
  return (
    <div className="flex items-center gap-3 text-xs">
      <span className="text-muted-foreground" title={session.user.email}>
        Signed in as <span className="font-medium text-foreground">{session.user.display_name || session.user.email}</span>
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={() => {
          clearSession();
          router.replace("/login");
        }}
      >
        Sign out
      </Button>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, ready] = useSession();
  const onLogin = pathname === "/login";

  // No session -> sign in. An expired/invalid token clears the session (see request()), which lands here too.
  useEffect(() => {
    if (ready && !session && !onLogin) router.replace("/login");
  }, [ready, session, onLogin, router]);

  // Confirm the stored token once per session; a 401 expires it and the effect above redirects.
  const token = session?.token;
  useEffect(() => {
    if (!token) return;
    api.me().catch(() => undefined);
  }, [token]);

  if (onLogin) return <main className="mx-auto max-w-md p-4 md:p-6">{children}</main>;
  if (!ready || !session) return <div className="p-6 text-sm text-muted-foreground">Checking your session...</div>;
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-border bg-card md:min-h-screen md:w-56 md:border-b-0 md:border-r">
        <div className="px-4 py-4 text-base font-semibold">PathForge AI</div>
        <nav aria-label="Main" className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn("whitespace-nowrap rounded-md px-3 py-2 text-sm hover:bg-muted", active && "bg-muted font-medium")}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-4 py-3">
          <ModeBadge />
          <UserBar session={session} />
        </header>
        <main className="mx-auto max-w-6xl p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
