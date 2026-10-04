import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight, CircleCheck, Shield } from "lucide-react";
import { useState } from "react";
import { Card } from "@/components/glyra/ui";
import { getAnswers, setAnswers, type Answers } from "@/lib/session";

export const Route = createFileRoute("/app/assessment")({
  head: () => ({
    meta: [
      { title: "Guided assessment — Glyra AI" },
      {
        name: "description",
        content: "A few quiet questions to shape your Glyra dashboard around your routine.",
      },
      { property: "og:title", content: "Guided assessment — Glyra AI" },
      { property: "og:description", content: "Build your starting point in three short steps." },
    ],
  }),
  component: Assessment,
});

const steps = [
  {
    key: "careType" as const,
    name: "Care context",
    question: "What kind of diabetes care are you navigating?",
    subtext: "This helps Glyra frame your insights in the right context.",
    options: ["Type 1 diabetes", "Type 2 diabetes", "I'm not sure yet"],
  },
  {
    key: "rhythm" as const,
    name: "Daily rhythm",
    question: "How often do you see your glucose readings?",
    subtext: "There's no wrong answer — we're just getting oriented.",
    options: ["Occasionally", "Daily", "Continuous"],
  },
  {
    key: "tools" as const,
    name: "Your tools",
    question: "What tools are part of your routine?",
    subtext: "Choose the one that feels most like your day.",
    options: ["Insulin", "Oral medication", "Lifestyle changes", "A combination"],
  },
];

function Assessment() {
  const [index, setIndex] = useState(0);
  const [answers, setLocal] = useState<Answers>({});
  const done = index >= steps.length;

  function choose(value: string) {
    const next = { ...getAnswers(), ...answers, [steps[index]!.key]: value };
    setLocal(next);
    setAnswers(next);
    setIndex((i) => i + 1);
  }

  if (done) {
    return (
      <div className="mx-auto max-w-xl">
        <Card className="teal-glow text-center">
          <CircleCheck className="mx-auto size-12 text-teal" />
          <p className="eyebrow mt-5 text-teal">Your Glyra starting point</p>
          <h1 className="mt-2 text-3xl font-extrabold">A thoughtful place to begin.</h1>
          <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
            Based on what you shared, Glyra will focus on helping you notice patterns without adding
            noise to your day.
          </p>
          <p className="mt-8 font-display text-6xl font-extrabold text-teal">82</p>
          <p className="mt-1 text-xs text-subtle">readiness score</p>
          <div className="mt-8 flex items-start gap-3 rounded-xl border border-border bg-surface/70 p-4 text-left">
            <Shield className="mt-0.5 size-4 shrink-0 text-teal" />
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">Next best step</span> — Review your
              weekly trend with your care team at your next visit.
            </p>
          </div>
          <Link
            to="/app"
            className="mt-7 inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-3 text-sm font-semibold text-primary-foreground shadow-glow hover:brightness-110"
          >
            Go to my overview →
          </Link>
        </Card>
      </div>
    );
  }

  const step = steps[index]!;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">A few quiet questions</p>
          <h1 className="mt-2 text-3xl font-extrabold sm:text-4xl">Build your starting point</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            A short reflection helps Glyra make the dashboard feel more like yours.
          </p>
        </div>
        <p className="font-display text-sm font-bold text-subtle">
          0{index + 1} <span className="text-border">/</span> 03
        </p>
      </div>

      <div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-card">
          <div
            className="h-full rounded-full bg-teal transition-all duration-500"
            style={{ width: `${((index + 1) / steps.length) * 100}%` }}
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-6">
          {steps.map((s, i) => (
            <span
              key={s.key}
              className={`flex items-center gap-2 text-xs font-semibold ${
                i <= index ? "text-teal" : "text-subtle"
              }`}
            >
              <span
                className={`flex size-6 items-center justify-center rounded-full border text-[11px] ${
                  i <= index ? "border-teal/40 bg-teal/10" : "border-border"
                }`}
              >
                {i + 1}
              </span>
              {s.name}
            </span>
          ))}
        </div>
      </div>

      <Card key={step.key}>
        <p className="font-display text-4xl font-extrabold text-teal">0{index + 1}</p>
        <h2 className="mt-3 text-xl font-bold">{step.question}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{step.subtext}</p>
        <div className="mt-6 space-y-3">
          {step.options.map((o) => (
            <button
              key={o}
              onClick={() => choose(o)}
              className="flex w-full items-center justify-between rounded-xl border border-border bg-surface/60 px-4 py-4 text-left text-sm font-semibold text-foreground transition-colors hover:border-teal/50"
            >
              {o}
              <ChevronRight className="size-4 text-subtle" />
            </button>
          ))}
        </div>
        <p className="mt-6 flex items-center gap-2 text-xs text-subtle">
          <Shield className="size-3.5" /> Your answers stay on this device.
        </p>
      </Card>
    </div>
  );
}
