import { createFileRoute, Link } from "@tanstack/react-router";
import { BellRing, ChevronLeft, ChevronRight, Lock, Moon, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Card, IconTile, Modal, PrimaryButton, SecondaryButton } from "@/components/glyra/ui";
import { useUser } from "@/components/glyra/user-context";
import { getAnswers, initials, type Answers } from "@/lib/session";

export const Route = createFileRoute("/app/profile")({
  head: () => ({
    meta: [
      { title: "Profile & settings — Glyra AI" },
      { name: "description", content: "Keep your context close, and your choices yours." },
      { property: "og:title", content: "Profile & settings — Glyra AI" },
      { property: "og:description", content: "Your Glyra space, your preferences." },
    ],
  }),
  component: Profile,
});

function Toggle({ on, onChange, label }: { on: boolean; onChange: () => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onChange}
      className={`h-6 w-11 shrink-0 rounded-full p-0.5 transition-colors ${on ? "bg-teal" : "bg-accent"}`}
    >
      <span
        className={`block size-5 rounded-full bg-foreground transition-transform ${on ? "translate-x-5" : ""}`}
      />
    </button>
  );
}

function Profile() {
  const { name, setUserName } = useUser();
  const [answers, setAnswersState] = useState<Answers>({});
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name);
  const [reminders, setReminders] = useState(false);
  const [summary, setSummary] = useState(true);

  useEffect(() => setAnswersState(getAnswers()), []);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <p className="eyebrow">Your Glyra space</p>
        <h1 className="mt-2 text-3xl font-extrabold sm:text-4xl">Profile &amp; settings</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Keep your context close, and your choices yours.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <Card>
          <div className="flex flex-col items-center text-center">
            <span className="flex size-20 items-center justify-center rounded-full bg-glucose/25 font-display text-xl font-extrabold text-teal">
              {initials(name)}
            </span>
            <p className="mt-4 font-display text-lg font-bold text-foreground">{name}</p>
            <p className="text-sm text-subtle">{answers.careType ?? "Type 1 diabetes"}</p>
          </div>
          <div className="my-6 h-px bg-border" />
          <dl className="space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-subtle">Target range</dt>
              <dd className="font-semibold text-foreground">70–180 mg/dL</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-subtle">Reading rhythm</dt>
              <dd className="font-semibold text-foreground">{answers.rhythm ?? "Continuous"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-subtle">Tools</dt>
              <dd className="font-semibold text-foreground">{answers.tools ?? "Insulin"}</dd>
            </div>
          </dl>
          <SecondaryButton
            className="mt-6 w-full"
            onClick={() => {
              setDraft(name);
              setEditing(true);
            }}
          >
            Edit profile
          </SecondaryButton>
        </Card>

        <div className="space-y-6">
          <Card>
            <p className="eyebrow">Preferences</p>
            <div className="mt-5 space-y-4">
              <div className="flex items-center gap-4">
                <IconTile>
                  <BellRing className="size-4" />
                </IconTile>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-foreground">Gentle reminders</p>
                  <p className="text-xs text-subtle">A quiet nudge when it may help</p>
                </div>
                <Toggle
                  on={reminders}
                  onChange={() => setReminders((v) => !v)}
                  label="Gentle reminders"
                />
              </div>
              <div className="flex items-center gap-4">
                <IconTile>
                  <Moon className="size-4" />
                </IconTile>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-foreground">Evening summary</p>
                  <p className="text-xs text-subtle">A daily reflection at 8:30 PM</p>
                </div>
                <Toggle on={summary} onChange={() => setSummary((v) => !v)} label="Evening summary" />
              </div>
            </div>
          </Card>

          <Card>
            <p className="eyebrow">Your information</p>
            <div className="mt-5 space-y-3">
              {[
                {
                  icon: Lock,
                  title: "Privacy & data",
                  text: "Your health space stays on this device",
                },
                {
                  icon: Sparkles,
                  title: "How Glyra works",
                  text: "Understand the signals behind your insights",
                },
              ].map((r) => (
                <button
                  key={r.title}
                  className="flex w-full items-center gap-4 rounded-xl border border-border bg-surface/60 p-4 text-left transition-colors hover:border-teal/40"
                >
                  <IconTile>
                    <r.icon className="size-4" />
                  </IconTile>
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-foreground">{r.title}</p>
                    <p className="text-xs text-subtle">{r.text}</p>
                  </div>
                  <ChevronRight className="size-4 text-subtle" />
                </button>
              ))}
            </div>
          </Card>
        </div>
      </div>

      <Link to="/app" className="inline-flex items-center gap-1 text-sm font-semibold text-teal">
        <ChevronLeft className="size-4" /> Back to overview
      </Link>

      {editing && (
        <Modal title="Edit profile" onClose={() => setEditing(false)}>
          <p className="mt-2 text-sm text-muted-foreground">Update the name shown in your space.</p>
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="mt-4 w-full rounded-lg border border-input bg-surface px-4 py-3 text-sm text-foreground focus:border-teal/50 focus:outline-none"
          />
          <div className="mt-5 flex gap-3">
            <PrimaryButton
              onClick={() => {
                setUserName(draft.trim() || name);
                setEditing(false);
              }}
            >
              Save
            </PrimaryButton>
            <SecondaryButton onClick={() => setEditing(false)}>Cancel</SecondaryButton>
          </div>
        </Modal>
      )}
    </div>
  );
}
