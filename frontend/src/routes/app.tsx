import { createFileRoute, Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  BarChart3,
  Bell,
  Brain,
  ChevronDown,
  LayoutGrid,
  Menu,
  Settings,
  Shield,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { UserContext } from "@/components/glyra/user-context";
import { Logo } from "@/components/glyra/Logo";
import { SafetyProvider, useSafety } from "@/components/glyra/SafetyModal";
import { getName, initials } from "@/lib/session";


export const Route = createFileRoute("/app")({
  ssr: false,
  component: AppLayout,
});

const nav: { to: "/app" | "/app/trends" | "/app/assessment" | "/app/profile"; label: string; icon: typeof LayoutGrid; exact?: boolean; dot?: boolean }[] = [
  { to: "/app", label: "Overview", icon: LayoutGrid, exact: true },
  { to: "/app/trends", label: "Trends & predictions", icon: BarChart3, dot: true },
  { to: "/app/assessment", label: "Guided assessment", icon: Brain },
  { to: "/app/profile", label: "Profile & settings", icon: Settings },
];

const pageNames: Record<string, string> = {
  "/app": "Overview",
  "/app/trends": "Trends & predictions",
  "/app/assessment": "Guided assessment",
  "/app/profile": "Profile & settings",
};

function AppLayout() {
  const navigate = useNavigate();
  const [name, setUserName] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    const stored = getName();
    if (!stored) navigate({ to: "/login" });
    else setUserName(stored);
  }, [navigate]);

  useEffect(() => setDrawer(false), [pathname]);

  if (!name) return <div className="min-h-screen bg-background" />;

  return (
    <UserContext.Provider
      value={{
        name,
        setUserName: (n) => {
          setUserName(n);
          window.sessionStorage.setItem("glyra_user", n);
        },
      }}
    >
      <SafetyProvider>
        <div className="flex min-h-screen bg-background">
          {drawer && (
            <div
              className="fixed inset-0 z-30 bg-background/70 backdrop-blur-sm lg:hidden"
              onClick={() => setDrawer(false)}
              role="presentation"
            />
          )}
          <aside
            className={`fixed inset-y-0 left-0 z-40 flex w-[300px] flex-col border-r border-border bg-surface p-6 transition-transform lg:static lg:w-[320px] lg:translate-x-0 ${
              drawer ? "translate-x-0" : "-translate-x-full"
            }`}
          >
            <div className="flex items-center justify-between">
              <Logo to="/app" />
              <button
                className="lg:hidden"
                aria-label="Close menu"
                onClick={() => setDrawer(false)}
              >
                <X className="size-5 text-subtle" />
              </button>
            </div>
            <p className="eyebrow mt-10">Your space</p>
            <nav className="mt-4 flex flex-col gap-1.5">
              {nav.map((item) => {
                const active = item.exact ? pathname === item.to : pathname.startsWith(item.to);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={`flex items-center gap-3 rounded-xl border px-4 py-3 text-sm font-semibold transition-colors ${
                      active
                        ? "border-teal/40 bg-teal/10 text-teal"
                        : "border-transparent text-muted-foreground hover:bg-accent hover:text-foreground"
                    }`}
                  >
                    <item.icon className="size-4" />
                    <span className="flex-1">{item.label}</span>
                    {item.dot && <span className="size-1.5 rounded-full bg-teal" />}
                  </Link>
                );
              })}
            </nav>
            <div className="mt-auto space-y-3 border-t border-border pt-6 text-sm text-subtle">
              <p className="flex items-center gap-3">
                <Shield className="size-4" /> Your data stays private
              </p>
              <Link to="/app/profile" className="flex items-center gap-3 hover:text-foreground">
                <Settings className="size-4" /> Settings
              </Link>
            </div>
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <TopBar name={name} onMenu={() => setDrawer(true)} pathname={pathname} />
            <main className="flex-1 px-5 py-8 sm:px-8">
              <Outlet />
            </main>
            <FooterBar />
          </div>
        </div>
      </SafetyProvider>
    </UserContext.Provider>
  );
}

function TopBar({
  name,
  onMenu,
  pathname,
}: {
  name: string;
  onMenu: () => void;
  pathname: string;
}) {
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-4 border-b border-border bg-background/85 px-5 py-4 backdrop-blur sm:px-8">
      <div className="flex items-center gap-3">
        <button className="lg:hidden" aria-label="Open menu" onClick={onMenu}>
          <Menu className="size-5 text-muted-foreground" />
        </button>
        <p className="text-sm text-subtle">
          My health space{" "}
          <span className="mx-1 text-border">›</span>
          <span className="font-semibold text-foreground">{pageNames[pathname] ?? "Overview"}</span>
        </p>
      </div>
      <div className="flex items-center gap-4">
        <button className="relative" aria-label="Notifications">
          <Bell className="size-5 text-muted-foreground" />
          <span className="absolute -right-0.5 -top-0.5 size-2 rounded-full bg-teal" />
        </button>
        <div className="flex items-center gap-2">
          <span className="flex size-9 items-center justify-center rounded-full bg-glucose/25 text-xs font-bold text-teal">
            {initials(name)}
          </span>
          <span className="hidden text-sm font-semibold text-foreground sm:block">{name}</span>
          <ChevronDown className="size-4 text-subtle" />
        </div>
      </div>
    </header>
  );
}

function FooterBar() {
  const { open } = useSafety();
  return (
    <footer className="sticky bottom-0 z-20 flex flex-wrap items-center justify-between gap-3 border-t border-border bg-surface/95 px-5 py-3 text-xs text-subtle backdrop-blur sm:px-8">
      <p className="flex items-center gap-2">
        <Shield className="size-3.5 shrink-0" />
        Glyra AI provides informational insights only. It does not replace professional medical
        advice or emergency care.
      </p>
      <button onClick={open} className="font-semibold text-teal">
        Learn more →
      </button>
    </footer>
  );
}
