import { Link } from "@tanstack/react-router";
import { Activity } from "lucide-react";

export function Logo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-3" aria-label="Glyra AI home">
      <span className="flex size-9 items-center justify-center rounded-xl border border-teal/40 bg-teal/10">
        <Activity className="size-[18px] text-teal" strokeWidth={2.4} />
      </span>
      <span className="font-display text-lg font-extrabold tracking-tight text-foreground">
        glyra<span className="text-teal">AI</span>
      </span>
    </Link>
  );
}
