import { createFileRoute, Link } from "@tanstack/react-router";
import { ArrowRight, Brain, Check, Shield, Sparkles, Target } from "lucide-react";
import { Logo } from "@/components/glyra/Logo";
import { SparkArea } from "@/components/glyra/charts";
import { heroSignal } from "@/data/mock";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Glyra AI — A clearer view of what's next" },
      {
        name: "description",
        content:
          "Glyra AI turns glucose patterns into calm, understandable signals for people living with diabetes.",
      },
      { property: "og:title", content: "Glyra AI — A clearer view of what's next" },
      {
        property: "og:description",
        content: "Calm, privacy-first glucose insights. A demo health space.",
      },
    ],
  }),
  component: Landing,
});

function Landing() {
  return (
    <div className="min-h-screen bg-background">
      <header className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Logo />
        <div className="flex items-center gap-5">
          <span className="hidden items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-muted-foreground sm:inline-flex">
            <span className="size-1.5 rounded-full bg-teal" />
            Demo environment
          </span>
          <Link to="/login" className="text-sm font-semibold text-teal hover:brightness-110">
            Explore dashboard →
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6">
        <section className="teal-glow grid items-center gap-16 py-14 lg:grid-cols-2 lg:py-24">
          <div className="animate-rise">
            <p className="eyebrow flex items-center gap-2 text-teal">
              <Sparkles className="size-3.5" /> Glucose intelligence, made clear
            </p>
            <h1 className="mt-5 text-5xl font-extrabold leading-[1.05] sm:text-6xl">
              A clearer view of
              <br />
              <span className="text-teal">what's next.</span>
            </h1>
            <p className="mt-6 max-w-md text-base leading-relaxed text-muted-foreground">
              Glyra turns your glucose patterns into calm, understandable signals — so you can feel
              more informed between appointments.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-5">
              <Link
                to="/login"
                className="inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-3 text-sm font-semibold text-primary-foreground shadow-glow transition-all hover:brightness-110"
              >
                Open your health space <ArrowRight className="size-4" />
              </Link>
              <span className="inline-flex items-center gap-2 text-sm text-subtle">
                <Shield className="size-4" /> Built with privacy in mind
              </span>
            </div>
            <div className="mt-12 flex items-center gap-4">
              <div className="flex -space-x-3">
                {["JM", "RK", "SL"].map((i) => (
                  <span
                    key={i}
                    className="flex size-10 items-center justify-center rounded-full border border-border bg-card text-xs font-bold text-muted-foreground"
                  >
                    {i}
                  </span>
                ))}
              </div>
              <div>
                <p className="font-display text-sm font-bold text-foreground">
                  Designed for real life
                </p>
                <p className="text-sm text-subtle">Type 1 &amp; Type 2 support</p>
              </div>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-md py-10">
            <div className="absolute inset-0 -z-10 m-auto size-[420px] rounded-full border border-teal/10" />
            <div
              className="glass-card p-6"
              style={{ transform: "perspective(1200px) rotateY(-10deg) rotateX(6deg)" }}
            >
              <div className="flex items-center justify-between text-xs">
                <span className="inline-flex items-center gap-2 font-semibold tracking-widest text-teal">
                  <span className="size-1.5 rounded-full bg-teal" /> LIVE SIGNAL
                </span>
                <span className="text-subtle">08:42 PM</span>
              </div>
              <div className="mt-5 flex items-end gap-2">
                <span className="font-display text-5xl font-extrabold text-foreground">118</span>
                <span className="pb-2 text-sm text-subtle">mg/dL</span>
              </div>
              <p className="mt-2 inline-flex items-center gap-2 text-sm text-teal">
                <Check className="size-4" /> In your target range
              </p>
              <div className="mt-4">
                <SparkArea data={heroSignal} />
              </div>
              <div className="mt-3 flex items-center justify-between text-xs text-subtle">
                <span>30 min outlook</span>
                <span>+6 m…</span>
              </div>
            </div>

            <div className="animate-float glass-card absolute -left-2 top-2 flex items-center gap-3 p-3 sm:-left-8">
              <Target className="size-4 text-teal" />
              <div>
                <p className="eyebrow">Time in range</p>
                <p className="font-display text-sm font-bold text-foreground">
                  84% <span className="text-teal">↗ 7.2%</span>
                </p>
              </div>
            </div>
            <div className="animate-float-slow glass-card absolute -right-2 bottom-4 flex items-center gap-3 p-3 sm:-right-8">
              <Brain className="size-4 text-teal" />
              <div>
                <p className="eyebrow">Glyra insight</p>
                <p className="font-display text-sm font-bold text-foreground">
                  Pattern looks stable
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-8 border-t border-border py-10 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="eyebrow">A more informed day</p>
            <p className="mt-3 max-w-md font-display text-xl font-bold text-foreground">
              See patterns. Ask better questions. Move forward with confidence.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-4">
            {[
              ["24h", "glucose view"],
              ["3h", "predictive horizon"],
              ["1", "calm place to start"],
            ].map(([n, l]) => (
              <div key={l}>
                <p className="font-display text-2xl font-extrabold text-teal">{n}</p>
                <p className="mt-1 text-xs text-subtle">{l}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="mx-auto max-w-6xl px-6 py-10 text-xs text-subtle">
        <span className="mr-2 inline-block size-1.5 rounded-full bg-teal align-middle" />
        Glyra AI is informational and does not replace professional medical advice.
      </footer>
    </div>
  );
}
