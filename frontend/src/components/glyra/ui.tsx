import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("glass-card animate-rise p-6", className)}>{children}</div>;
}

export function Eyebrow({ className, children }: { className?: string; children: ReactNode }) {
  return <p className={cn("eyebrow", className)}>{children}</p>;
}

export function IconTile({ children, tone = "teal" }: { children: ReactNode; tone?: "teal" | "blue" | "amber" }) {
  const tones = {
    teal: "border-teal/30 bg-teal/10 text-teal",
    blue: "border-glucose/30 bg-glucose/10 text-glucose",
    amber: "border-amber/30 bg-amber/10 text-amber",
  } as const;
  return (
    <span
      className={cn(
        "flex size-10 shrink-0 items-center justify-center rounded-xl border",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function PrimaryButton({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg bg-teal px-5 py-3 text-sm font-semibold text-primary-foreground shadow-glow transition-all hover:brightness-110 active:scale-[0.99]",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground transition-colors hover:border-teal/40",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="presentation"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
        className="glass-card animate-rise w-full max-w-md p-7"
      >
        <h2 className="text-xl font-bold">{title}</h2>
        {children}
      </div>
    </div>
  );
}
