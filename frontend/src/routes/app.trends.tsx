import { createFileRoute } from "@tanstack/react-router";
import { Activity, Brain, ChevronDown, HelpCircle } from "lucide-react";
import { useState } from "react";
import { useSafety } from "@/components/glyra/SafetyModal";
import { GlucoseChart } from "@/components/glyra/charts";
import { Card } from "@/components/glyra/ui";
import { forecast, ranges, type RangeKey } from "@/data/mock";

export const Route = createFileRoute("/app/trends")({
  head: () => ({
    meta: [
      { title: "Trends & predictions — Glyra AI" },
      {
        name: "description",
        content: "Patterns over time and a gentle look at the next few hours.",
      },
      { property: "og:title", content: "Trends & predictions — Glyra AI" },
      { property: "og:description", content: "See the bigger picture in your glucose data." },
    ],
  }),
  component: Trends,
});

function Trends() {
  const { open } = useSafety();
  const [rangeKey, setRangeKey] = useState<RangeKey>("24h");
  const [menu, setMenu] = useState(false);
  const range = ranges[rangeKey];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">Patterns over time</p>
          <h1 className="mt-2 text-3xl font-extrabold sm:text-4xl">Trends &amp; predictions</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Use the bigger picture to prepare better questions for your care team.
          </p>
        </div>
        <div className="relative">
          <button
            onClick={() => setMenu((m) => !m)}
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2.5 text-sm font-semibold text-foreground"
          >
            <Activity className="size-4 text-teal" /> {range.label}
            <ChevronDown className="size-4 text-subtle" />
          </button>
          {menu && (
            <div className="glass-card absolute right-0 z-20 mt-2 w-48 overflow-hidden p-1">
              {(Object.keys(ranges) as RangeKey[]).map((k) => (
                <button
                  key={k}
                  onClick={() => {
                    setRangeKey(k);
                    setMenu(false);
                  }}
                  className="block w-full rounded-lg px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  {ranges[k].label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          { label: "Average glucose", value: `${range.average} mg/dL`, meta: "↓ 4.8%" },
          { label: "Time in range", value: `${range.tir}%`, meta: "↑ 7.2%" },
          { label: "Variability", value: `${range.variability} mg/dL`, meta: "Stable" },
        ].map((s) => (
          <Card key={s.label} className="p-5">
            <p className="eyebrow">{s.label}</p>
            <p className="mt-3 font-display text-2xl font-extrabold text-foreground">
              {s.value} <span className="text-xs font-semibold text-teal">{s.meta}</span>
            </p>
          </Card>
        ))}
      </div>

      <Card>
        <div className="flex items-center justify-between">
          <p className="eyebrow flex items-center gap-2">
            {range.label} trend <HelpCircle className="size-3.5" />
          </p>
          <span className="inline-flex items-center gap-2 text-xs text-subtle">
            <span className="size-1.5 rounded-full bg-glucose" /> Glucose
          </span>
        </div>
        <h2 className="mt-3 text-lg font-bold">Your day, at a glance</h2>
        <GlucoseChart data={range.data} height={280} />
        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="inline-flex items-center gap-2 text-subtle">
            <span className="size-1.5 rounded-full bg-amber" /> Target range
          </span>
          <button onClick={open} className="font-semibold text-teal">
            Understand this view →
          </button>
        </div>
      </Card>

      <Card>
        <div className="flex items-center justify-between">
          <p className="eyebrow flex items-center gap-2">
            Predicted glucose <HelpCircle className="size-3.5" />
          </p>
          <span className="inline-flex items-center gap-2 text-xs text-subtle">
            <span className="size-1.5 rounded-full bg-teal" /> Prediction
          </span>
        </div>
        <h2 className="mt-3 text-lg font-bold">The next few hours</h2>
        <GlucoseChart data={forecast} color="teal" height={260} />
        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="inline-flex items-center gap-2 text-subtle">
            <span className="size-1.5 rounded-full bg-amber" /> Target range
          </span>
          <button onClick={open} className="font-semibold text-teal">
            Understand this view →
          </button>
        </div>
      </Card>

      <Card className="flex flex-wrap items-center gap-4 border-glucose/25 bg-glucose/[0.07]">
        <Brain className="size-5 shrink-0 text-glucose" />
        <p className="min-w-[260px] flex-1 text-sm leading-relaxed text-muted-foreground">
          <span className="font-semibold text-foreground">How to read this:</span> the shaded
          forecast area represents a range of possible readings, not a promise. Your lived
          experience always matters more than a projection.
        </p>
        <button onClick={open} className="text-sm font-semibold text-teal">
          Safety guidance →
        </button>
      </Card>
    </div>
  );
}
