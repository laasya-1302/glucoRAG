export type Point = { label: string; value: number };

export const CURRENT_GLUCOSE = 118;

export const dayTrend: Point[] = [
  { label: "12 AM", value: 104 },
  { label: "2 AM", value: 98 },
  { label: "4 AM", value: 95 },
  { label: "6 AM", value: 101 },
  { label: "8 AM", value: 124 },
  { label: "10 AM", value: 132 },
  { label: "12 PM", value: 119 },
  { label: "2 PM", value: 110 },
  { label: "4 PM", value: 122 },
  { label: "6 PM", value: 130 },
  { label: "8 PM", value: 121 },
  { label: "Now", value: 118 },
];

export const weekTrend: Point[] = [
  { label: "Mon", value: 116 },
  { label: "Tue", value: 121 },
  { label: "Wed", value: 112 },
  { label: "Thu", value: 125 },
  { label: "Fri", value: 118 },
  { label: "Sat", value: 109 },
  { label: "Now", value: 115 },
];

export const fortnightTrend: Point[] = [
  { label: "Week 1", value: 122 },
  { label: "Day 4", value: 117 },
  { label: "Day 7", value: 126 },
  { label: "Day 10", value: 113 },
  { label: "Day 12", value: 119 },
  { label: "Now", value: 114 },
];

export const forecast: Point[] = [
  { label: "Now", value: 118 },
  { label: "+30m", value: 122 },
  { label: "+60m", value: 127 },
  { label: "+90m", value: 130 },
  { label: "+2h", value: 124 },
  { label: "+3h", value: 116 },
];

export const ranges = {
  "24h": { label: "Last 24 hours", data: dayTrend, average: 115, tir: 84, variability: 28 },
  "7d": { label: "Last 7 days", data: weekTrend, average: 118, tir: 81, variability: 31 },
  "14d": { label: "Last 14 days", data: fortnightTrend, average: 119, tir: 79, variability: 33 },
} as const;

export type RangeKey = keyof typeof ranges;

export type Activity = {
  id: string;
  kind: "meal" | "reading" | "dose";
  title: string;
  subtitle: string;
  time: string;
};

export const recentActivity: Activity[] = [
  {
    id: "a1",
    kind: "meal",
    title: "Dinner logged",
    subtitle: "48g carbohydrates",
    time: "6:42 PM",
  },
  {
    id: "a2",
    kind: "reading",
    title: "Glucose check",
    subtitle: "122 mg/dL · In range",
    time: "4:10 PM",
  },
  {
    id: "a3",
    kind: "dose",
    title: "Bolus recorded",
    subtitle: "2.5 units rapid-acting",
    time: "12:30 PM",
  },
];

export const heroSignal: Point[] = [
  { label: "1", value: 108 },
  { label: "2", value: 114 },
  { label: "3", value: 110 },
  { label: "4", value: 121 },
  { label: "5", value: 116 },
  { label: "6", value: 124 },
  { label: "7", value: 118 },
];
