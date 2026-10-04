import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Point } from "@/data/mock";

const TEAL = "#3DDBC0";
const BLUE = "#3B82F6";
const AMBER = "#F5B84B";

function DarkTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-border bg-surface px-3 py-2 text-xs shadow-card">
      <p className="text-subtle">{label}</p>
      <p className="font-display font-bold text-foreground">{payload[0].value} mg/dL</p>
    </div>
  );
}

export function GlucoseChart({
  data,
  color = "blue",
  height = 240,
  ticks = true,
}: {
  data: Point[];
  color?: "blue" | "teal";
  height?: number;
  ticks?: boolean;
}) {
  const stroke = color === "teal" ? TEAL : BLUE;
  const id = `fill-${color}`;
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 8, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.04)" />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#6B7C93", fontSize: 11 }}
            interval="preserveStartEnd"
            minTickGap={16}
          />
          <YAxis
            domain={[60, 190]}
            ticks={ticks ? [70, 130, 180] : []}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "#6B7C93", fontSize: 11 }}
            width={44}
          />
          <ReferenceLine y={70} stroke={AMBER} strokeDasharray="4 6" strokeOpacity={0.6} />
          <ReferenceLine y={180} stroke={AMBER} strokeDasharray="4 6" strokeOpacity={0.6} />
          <Tooltip content={<DarkTooltip />} cursor={{ stroke: "rgba(255,255,255,0.12)" }} />
          <Area
            type="monotone"
            dataKey="value"
            stroke={stroke}
            strokeWidth={2.5}
            fill={`url(#${id})`}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function SparkArea({ data }: { data: Point[] }) {
  return (
    <div className="h-24 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="hero-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={TEAL} stopOpacity={0.4} />
              <stop offset="100%" stopColor={TEAL} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={TEAL}
            strokeWidth={2.5}
            fill="url(#hero-fill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function MiniLine({ data }: { data: Point[] }) {
  return (
    <div className="h-20 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 4, left: 8 }}>
          <Line
            type="monotone"
            dataKey="value"
            stroke={TEAL}
            strokeWidth={2}
            dot={{ r: 3, fill: TEAL, strokeWidth: 0 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
