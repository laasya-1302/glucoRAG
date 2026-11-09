import React from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ReferenceArea,
  CartesianGrid,
  Legend
} from 'recharts';
import { TrendingUp, Info } from 'lucide-react';

export default function ForecastChart({ historicalReadings, forecastData, units = "mg/dL" }) {
  if (!historicalReadings || historicalReadings.length === 0) {
    return (
      <div className="card chart-empty-card">
        <p>No historical data to display.</p>
      </div>
    );
  }

  // Construct chart dataset: 24 historical points + 8 predicted points
  // Point 23 connects historical and predicted lines seamlessly
  const chartData = [];

  // Historical points (-345m to 0m)
  historicalReadings.forEach((val, idx) => {
    const mins = - (23 - idx) * 15;
    const label = mins === 0 ? "Now (0m)" : `${mins}m`;
    const num = parseFloat(val);

    chartData.push({
      timeLabel: label,
      minuteOffset: mins,
      historical: isNaN(num) ? null : num,
      predictedMedian: idx === 23 ? num : null, // Connect at current point
      q10: null,
      q90: null,
      qRange: null,
      isForecast: false,
      step: idx + 1
    });
  });

  // Predicted points (+15m to +120m)
  if (forecastData && forecastData.length > 0) {
    forecastData.forEach((step) => {
      const label = `+${step.horizon_minutes}m`;
      const q10 = step.uncertainty_band.low_q10;
      const q90 = step.uncertainty_band.high_q90;

      chartData.push({
        timeLabel: label,
        minuteOffset: step.horizon_minutes,
        historical: null,
        predictedMedian: step.glucose_median,
        q10: q10,
        q90: q90,
        // For Recharts Area representing the band from q10 to q90
        bandBase: q10,
        bandWidth: q90 - q10,
        riskClass: step.predicted_risk_class,
        hypoProb: (step.risk_probabilities.hypo * 100).toFixed(1),
        hyperProb: (step.risk_probabilities.hyper * 100).toFixed(1),
        isForecast: true,
        step: step.step
      });
    });
  }

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    const data = payload[0]?.payload;
    if (!data) return null;

    return (
      <div className="chart-tooltip">
        <div className="tooltip-header">
          <strong>Time: {data.timeLabel}</strong>
          {data.isForecast && <span className="tooltip-badge">GPFormer Forecast</span>}
        </div>

        {data.historical !== null && (
          <div className="tooltip-row">
            <span className="tooltip-dot history-dot"></span>
            <span>Historical Glucose:</span>
            <strong>{data.historical} {units}</strong>
          </div>
        )}

        {data.predictedMedian !== null && (
          <div className="tooltip-row">
            <span className="tooltip-dot forecast-dot"></span>
            <span>Forecast Median (q50):</span>
            <strong className="text-teal">{data.predictedMedian} {units}</strong>
          </div>
        )}

        {data.isForecast && (
          <>
            <div className="tooltip-row text-muted">
              <span>10% – 90% Uncertainty:</span>
              <strong>[{data.q10} – {data.q90}] {units}</strong>
            </div>
            <div className="tooltip-row">
              <span>Risk Assessment:</span>
              <span className={`risk-pill ${data.riskClass?.toLowerCase()}`}>
                {data.riskClass} (Hypo: {data.hypoProb}%, Hyper: {data.hyperProb}%)
              </span>
            </div>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="card chart-card">
      <div className="card-header">
        <div>
          <h2 className="card-title flex-align">
            <TrendingUp size={20} className="text-teal" />
            <span>Multi-Horizon Glucose Trajectory (6h History + 2h Forecast)</span>
          </h2>
          <p className="card-description">
            Continuous glucose readings with 10th–90th percentile uncertainty interval and 70–180 mg/dL target zone.
          </p>
        </div>
      </div>

      <div className="chart-container" style={{ width: '100%', height: 380 }}>
        <ResponsiveContainer>
          <ComposedChart
            data={chartData}
            margin={{ top: 20, right: 30, left: 10, bottom: 25 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />

            {/* Target Normal Range: 70 to 180 mg/dL */}
            <ReferenceArea
              y1={70}
              y2={180}
              fill="#10B981"
              fillOpacity={0.06}
              label={{ value: 'Target Range (70-180 mg/dL)', position: 'insideTopRight', fill: '#059669', fontSize: 11 }}
            />

            {/* Reference Threshold Lines */}
            <ReferenceLine
              y={70}
              stroke="#EF4444"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{ value: 'Hypo Threshold (70 mg/dL)', position: 'insideBottomLeft', fill: '#DC2626', fontSize: 11 }}
            />
            <ReferenceLine
              y={180}
              stroke="#F59E0B"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{ value: 'Hyper Threshold (180 mg/dL)', position: 'insideTopLeft', fill: '#D97706', fontSize: 11 }}
            />

            {/* Current Time Divider */}
            <ReferenceLine
              x="Now (0m)"
              stroke="#64748B"
              strokeDasharray="3 3"
              label={{ value: 'Forecast Horizon →', position: 'top', fill: '#475569', fontSize: 11 }}
            />

            <XAxis
              dataKey="timeLabel"
              tick={{ fontSize: 11, fill: '#64748B' }}
              interval="preserveStartEnd"
              angle={-25}
              textAnchor="end"
              height={50}
            />
            <YAxis
              domain={[40, 'auto']}
              tick={{ fontSize: 11, fill: '#64748B' }}
              label={{ value: `Glucose (${units})`, angle: -90, position: 'insideLeft', style: { fill: '#475569', fontSize: 12 } }}
            />

            <Tooltip content={<CustomTooltip />} />
            <Legend
              verticalAlign="top"
              height={36}
              wrapperStyle={{ fontSize: '12px', paddingBottom: '10px' }}
            />

            {/* Uncertainty Interval Area (10th to 90th percentile) */}
            <Area
              name="10th–90th Percentile Interval"
              type="monotone"
              dataKey="bandWidth"
              baseValue="dataMin"
              fill="#0D9488"
              fillOpacity={0.18}
              stroke="none"
              legendType="rect"
            />

            {/* Historical Glucose Line */}
            <Line
              name="Historical Readings (Past 6 Hours)"
              type="monotone"
              dataKey="historical"
              stroke="#0284C7"
              strokeWidth={2.5}
              dot={{ r: 3, fill: '#0284C7' }}
              activeDot={{ r: 6 }}
              connectNulls={false}
            />

            {/* Forecast Median Line */}
            <Line
              name="Forecast Median (Next 2 Hours)"
              type="monotone"
              dataKey="predictedMedian"
              stroke="#0D9488"
              strokeWidth={3}
              strokeDasharray="5 3"
              dot={{ r: 4, fill: '#0D9488', strokeWidth: 2, stroke: '#FFFFFF' }}
              activeDot={{ r: 7 }}
              connectNulls={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="chart-footer-note">
        <Info size={14} className="text-muted" />
        <span>
          Shaded teal area displays the model's 10th–90th percentile uncertainty interval. The dashed line traces the 50th percentile (median) forecast.
        </span>
      </div>
    </div>
  );
}
