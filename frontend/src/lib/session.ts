export const NAME_KEY = "glyra_user";
export const ANSWERS_KEY = "glyra_answers";

export type Answers = {
  careType?: string;
  rhythm?: string;
  tools?: string;
};

export function getName(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(NAME_KEY);
}

export function setName(name: string) {
  window.sessionStorage.setItem(NAME_KEY, name);
}

export function getAnswers(): Answers {
  if (typeof window === "undefined") return {};
  try {
    return JSON.parse(window.sessionStorage.getItem(ANSWERS_KEY) ?? "{}") as Answers;
  } catch {
    return {};
  }
}

export function setAnswers(answers: Answers) {
  window.sessionStorage.setItem(ANSWERS_KEY, JSON.stringify(answers));
}

export function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "AM";
  if (parts.length === 1) return (parts[0] ?? "").slice(0, 2).toUpperCase();
  return ((parts[0]?.[0] ?? "") + (parts[parts.length - 1]?.[0] ?? "")).toUpperCase();
}

export function firstName(name: string) {
  return name.trim().split(/\s+/)[0] || "there";
}

export function greeting(date = new Date()) {
  const h = date.getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export function checkInLabel(date = new Date()) {
  const day = date
    .toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })
    .toUpperCase();
  const h = date.getHours();
  const part = h < 12 ? "MORNING" : h < 17 ? "AFTERNOON" : "EVENING";
  return `${day} · ${part} CHECK-IN`;
}
