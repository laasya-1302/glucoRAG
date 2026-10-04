import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { ArrowRight, Shield, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Logo } from "@/components/glyra/Logo";
import { setName } from "@/lib/session";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in — Glyra AI" },
      {
        name: "description",
        content: "Enter your name to continue to your private Glyra AI workspace.",
      },
      { property: "og:title", content: "Sign in — Glyra AI" },
      { property: "og:description", content: "Your private, name-only health space." },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const [value, setValue] = useState("");
  const navigate = useNavigate();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const typed = String(new FormData(e.currentTarget as HTMLFormElement).get("name") ?? value);
    setName(typed.trim() || "Alex Morgan");
    navigate({ to: "/app" });
  }

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="px-6 py-6">
        <Logo />
      </header>
      <main className="teal-glow flex flex-1 items-center justify-center px-6 pb-16">
        <form onSubmit={submit} className="glass-card animate-rise w-full max-w-[580px] p-8 sm:p-10">
          <span className="flex size-11 items-center justify-center rounded-xl border border-teal/30 bg-teal/10">
            <ShieldCheck className="size-5 text-teal" />
          </span>
          <p className="eyebrow mt-6 text-teal">Your private health space</p>
          <h1 className="mt-2 text-3xl font-extrabold">Welcome back.</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Enter your name to continue to your Glyra AI workspace.
          </p>

          <label htmlFor="name" className="mt-8 flex items-center gap-2 text-sm font-bold text-foreground">
            Your name <span className="font-normal text-subtle">optional</span>
          </label>
          <input
            id="name"
            name="name"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Alex Morgan"
            className="mt-2 w-full rounded-lg border border-input bg-surface px-4 py-3 text-sm text-foreground placeholder:text-subtle focus:border-teal/50 focus:outline-none"
          />

          <button
            type="submit"
            className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-teal px-5 py-3 text-sm font-semibold text-primary-foreground shadow-glow transition-all hover:brightness-110"
          >
            Continue to Glyra <ArrowRight className="size-4" />
          </button>

          <div className="my-7 flex items-center gap-4">
            <span className="h-px flex-1 bg-border" />
            <span className="eyebrow">Private by design</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <p className="flex items-start gap-2 text-xs leading-relaxed text-subtle">
            <Shield className="mt-0.5 size-3.5 shrink-0" />
            This demo keeps access in your current browser tab. No account or password is created.
          </p>
        </form>
      </main>
      <footer className="px-6 pb-8 text-center text-xs text-subtle">
        <span className="mr-2 inline-block size-1.5 rounded-full bg-teal align-middle" />
        Glyra AI is informational and does not replace professional medical advice.
      </footer>
    </div>
  );
}
