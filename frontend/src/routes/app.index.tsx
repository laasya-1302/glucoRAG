import { createFileRoute, Link } from "@tanstack/react-router";
import {
  Activity,
  ArrowUpRight,
  Check,
  CircleHelp,
  Droplet,
  HelpCircle,
  Info,
  Plus,
  Shield,
  Sparkles,
  Syringe,
  Target,
  TrendingDown,
  TrendingUp,
  Utensils,
  Zap,
} from "lucide-react";
import { useState } from "react";
import { useSafety } from "@/components/glyra/SafetyModal";
import { GlucoseChart, MiniLine } from "@/components/glyra/charts";
import { Card, IconTile, Modal, PrimaryButton, SecondaryButton } from "@/components/glyra/ui";
import { useUser } from "@/components/glyra/user-context";
import {
  CURRENT_GLUCOSE,
  dayTrend,
  forecast,
  recentActivity,
  type Activity as ActivityItem,
} from "@/data/mock";
import { checkInLabel, firstName, greeting } from "@/lib/session";

export const Route = createFileRoute("/app/")({
  head: () => ({
    meta: [
      { title: "Overview — Glyra AI" },
      { name: "description", content: "Today's glucose signal, trends and gentle insights." },
      { property: "og:title", content: "Overview — Glyra AI" },
      { property: "og:description", content: "Your calm daily glucose check-in." },
    ],
  }),
  component: Overview,
});

function Overview() {
  const { name } = useUser();
  const { open } = useSafety();
  const [current, setCurrent] = useState(CURRENT_GLUCOSE);
  const [activity, setActivity] = useState<ActivityItem[]>(recentActivity);
  const [adding, setAdding] = useState(false);
  const [reading, setReading] = useState("");

  function addReading() {
    const n = Number(reading);
    if (!Number.isFinite(n) || n <= 0) return;
    setCurrent(n);
    setActivity((prev) => [
      {
        id: String(Date.now()),
        kind: "reading",
        title: "Glucose check",
        subtitle: `${n} mg/dL · ${n >= 70 && n <= 180 ? "In range" : "Outside target range"}`,
        time: new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
      },
      ...prev,
    ]);
    setReading("");
    setAdding(false);
  }

  const markerPct = Math.min(96, Math.max(4, ((current - 40) / 180) * 100));

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow">{checkInLabel()}</p>
          <h1 className="mt-2 flex items-center gap-2 text-3xl font-extrabold sm:text-4xl">
            {greeting()}, {firstName(name)}
            <Sparkles className="size-5 text-teal" />
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Here's the signal from your glucose today.
          </p>
        </div>
        <SecondaryButton onClick={() => setAdding(true)}>
          <Plus className="size-4" /> Add a reading
        </SecondaryButton>
      </div>

      <Card className="flex flex-wrap items-center gap-4 border-teal/25 bg-teal/[0.06]">
        <IconTile>
          <Shield className="size-5" />
        </IconTile>
        <div className="min-w-[240px] flex-1">
          <p className="font-display font-bold text-foreground">Looking steady right now</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Your current reading is in range. If you feel symptoms that concern you, trust how you
            feel and contact your care team.
          </p>
        </div>
        <button onClick={open} className="inline-flex items-center gap-2 text-sm font-semibold text-teal">
          <Info className="size-4" /> Safety guidance
        </button>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card>
          <div className="flex items-center justify-between">
            <p className="eyebrow flex items-center gap-2">
              <span className="size-1.5 rounded-full bg-teal" /> Current glucose
            </p>
            <HelpCircle className="size-4 text-subtle" />
          </div>
          <div className="mt-5 flex items-end gap-2">
            <span className="font-display text-5xl font-extrabold text-foreground">{current}</span>
            <span className="pb-2 text-sm text-subtle">mg/dL</span>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-teal/30 bg-teal/10 px-2.5 py-1 text-xs font-semibold text-teal">
              <Check className="size-3" /> In range
            </span>
            <span className="text-xs text-subtle">+6 since last check</span>
          </div>
          <div className="mt-6">
            <div className="relative h-2 rounded-full bg-gradient-to-r from-glucose to-teal">
              <span
                className="absolute top-1/2 size-3 -translate-y-1/2 rounded-full bg-foreground shadow"
                style={{ left: `${markerPct}%` }}
              />
            </div>
            <div className="mt-2 flex justify-between text-[10px] uppercase tracking-widest text-subtle">
              <span>Low 70</span>
              <span>Target range</span>
              <span>High 180</span>
            </div>
          </div>
          <p className="mt-6 flex items-center gap-2 text-xs text-subtle">
            <Activity className="size-3.5" /> Updated Now · Continuous reading
          </p>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <p className="eyebrow">24-hour trend</p>
            <span className="inline-flex items-center gap-2 text-xs text-subtle">
              <span className="size-1.5 rounded-full bg-glucose" /> Glucose
            </span>
          </div>
          <h2 className="mt-3 text-lg font-bold">Your day, at a glance</h2>
          <GlucoseChart data={dayTrend} height={200} />
          <div className="mt-3 flex items-center justify-between text-xs">
            <span className="inline-flex items-center gap-2 text-subtle">
              <span className="size-1.5 rounded-full bg-amber" /> Target range
            </span>
            <Link to="/app/trends" className="font-semibold text-teal">
              Understand this view →
            </Link>
          </div>
        </Card>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="eyebrow">Signals to notice</p>
            <CircleHelp className="size-4 text-subtle" />
          </div>
          <h2 className="text-lg font-bold">Looking ahead</h2>
          {[
            {
              icon: Target,
              title: "Time in range",
              value: "84%",
              meta: "+7.2%",
              metaTeal: true,
              text: "A steady share of your day sits inside your target band.",
            },
            {
              icon: TrendingDown,
              title: "Low glucose risk",
              value: "Low",
              meta: "Next 24h",
              text: "No meaningful low-glucose pattern detected in your recent data.",
            },
            {
              icon: TrendingUp,
              title: "A1C projection",
              value: "6.8%",
              meta: "14-day view",
              text: "Your estimated average is within the goal you set with your care team.",
            },
          ].map((s) => (
            <Card key={s.title} className="p-5">
              <div className="flex items-start gap-3">
                <IconTile>
                  <s.icon className="size-4" />
                </IconTile>
                <div className="flex-1">
                  <p className="text-xs font-semibold text-subtle">{s.title}</p>
                  <p className="mt-1 font-display text-xl font-extrabold text-foreground">
                    {s.value}{" "}
                    <span className={`text-xs font-semibold ${s.metaTeal ? "text-teal" : "text-subtle"}`}>
                      {s.meta}
                    </span>
                  </p>
                  <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{s.text}</p>
                </div>
                <ArrowUpRight className="size-4 text-subtle" />
              </div>
            </Card>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <div className="flex items-center justify-between">
            <p className="eyebrow">Recent activity</p>
            <span className="text-xs font-semibold text-teal">View all →</span>
          </div>
          <h2 className="mt-3 text-lg font-bold">What you've logged</h2>
          <ul className="mt-5 space-y-3">
            {activity.map((a) => (
              <li key={a.id} className="flex items-center gap-3 rounded-xl border border-border bg-surface/60 p-3">
                <IconTile tone={a.kind === "meal" ? "amber" : a.kind === "dose" ? "blue" : "teal"}>
                  {a.kind === "meal" ? (
                    <Utensils className="size-4" />
                  ) : a.kind === "dose" ? (
                    <Syringe className="size-4" />
                  ) : (
                    <Droplet className="size-4" />
                  )}
                </IconTile>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-foreground">{a.title}</p>
                  <p className="text-xs text-subtle">{a.subtitle}</p>
                </div>
                <span className="text-xs text-subtle">{a.time}</span>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <p className="eyebrow">Glyra forecast</p>
            <span className="flex items-center gap-2">
              <span className="rounded-full border border-teal/30 bg-teal/10 px-2.5 py-1 text-[11px] font-semibold text-teal">
                89% confidence
              </span>
              <HelpCircle className="size-4 text-subtle" />
            </span>
          </div>
          <h2 className="mt-3 text-lg font-bold">Next 3 hours</h2>
          <div className="mt-4 flex items-start gap-3 rounded-xl border border-teal/20 bg-teal/[0.07] p-4">
            <Zap className="mt-0.5 size-4 shrink-0 text-teal" />
            <div>
              <p className="text-sm font-semibold text-foreground">Likely to stay in range</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Small rise, then a gentle return toward baseline.
              </p>
            </div>
          </div>
          <MiniLine data={forecast} />
          <Link to="/app/trends" className="text-sm font-semibold text-teal">
            Explore your prediction →
          </Link>
        </Card>
      </div>

      {adding && (
        <Modal title="Add a reading" onClose={() => setAdding(false)}>
          <p className="mt-2 text-sm text-muted-foreground">
            Enter the value you just measured, in mg/dL.
          </p>
          <input
            autoFocus
            type="number"
            value={reading}
            onChange={(e) => setReading(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addReading()}
            placeholder="118"
            className="mt-4 w-full rounded-lg border border-input bg-surface px-4 py-3 text-sm text-foreground placeholder:text-subtle focus:border-teal/50 focus:outline-none"
          />
          <div className="mt-5 flex gap-3">
            <PrimaryButton onClick={addReading}>Save reading</PrimaryButton>
            <SecondaryButton onClick={() => setAdding(false)}>Cancel</SecondaryButton>
          </div>
        </Modal>
      )}
    </div>
  );
}
