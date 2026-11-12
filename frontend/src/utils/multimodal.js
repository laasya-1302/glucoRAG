/**
 * multimodal.js
 * Pure utility functions for validation, payload construction,
 * and forecast comparison for insulin and carbohydrate data.
 */

export function getLocalDateTimeString() {
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  return now.toISOString().slice(0, 16);
}

/**
 * Validates a single bolus event.
 * Rules:
 * - 0 to 40 U per event
 * - Warning if > 17 U
 * - Event time must not be after latest glucose reading
 */
export function validateBolus(ev, latestTimestamp) {
  if (!ev || !ev.time || ev.units === '' || ev.units === undefined) {
    return { error: null, warning: null };
  }

  const evTime = new Date(ev.time);
  const maxTime = latestTimestamp ? new Date(latestTimestamp) : null;

  if (maxTime && evTime > maxTime) {
    return { error: 'Event time must not be after the latest glucose reading', warning: null };
  }

  const units = parseFloat(ev.units);
  if (isNaN(units)) {
    return { error: 'Units must be a valid number', warning: null };
  }
  if (units < 0) {
    return { error: 'Units cannot be negative', warning: null };
  }
  if (units > 40) {
    return { error: 'Units must not exceed 40 U', warning: null };
  }
  if (units > 17) {
    return { error: null, warning: '⚠ High dose (>17 U)' };
  }

  return { error: null, warning: null };
}

/**
 * Validates a basal rate event.
 * Rules:
 * - 0 to 5 U/h
 * - Event time must not be after latest glucose reading
 */
export function validateBasal(basalRate, latestTimestamp) {
  if (!basalRate) return { error: null, warning: null };

  const { time, rate } = basalRate;
  if (!time || rate === '' || rate === undefined) {
    return { error: null, warning: null };
  }

  const evTime = new Date(time);
  const maxTime = latestTimestamp ? new Date(latestTimestamp) : null;

  if (maxTime && evTime > maxTime) {
    return { error: 'Event time must not be after the latest glucose reading', warning: null };
  }

  const r = parseFloat(rate);
  if (isNaN(r)) {
    return { error: 'Basal rate must be a valid number', warning: null };
  }
  if (r < 0) {
    return { error: 'Basal rate cannot be negative', warning: null };
  }
  if (r > 5) {
    return { error: 'Basal rate must not exceed 5 U/h', warning: null };
  }

  return { error: null, warning: null };
}

/**
 * Validates a single carb event.
 * Rules:
 * - 0 to 370 g per event
 * - Warning if > 120 g
 * - Event time must not be after latest glucose reading
 */
export function validateCarb(ev, latestTimestamp) {
  if (!ev || !ev.time || ev.grams === '' || ev.grams === undefined) {
    return { error: null, warning: null };
  }

  const evTime = new Date(ev.time);
  const maxTime = latestTimestamp ? new Date(latestTimestamp) : null;

  if (maxTime && evTime > maxTime) {
    return { error: 'Event time must not be after the latest glucose reading', warning: null };
  }

  const grams = parseFloat(ev.grams);
  if (isNaN(grams)) {
    return { error: 'Carbs must be a valid number', warning: null };
  }
  if (grams < 0) {
    return { error: 'Carbs cannot be negative', warning: null };
  }
  if (grams > 370) {
    return { error: 'Carbs must not exceed 370 g', warning: null };
  }
  if (grams > 120) {
    return { error: null, warning: '⚠ Large meal (>120 g)' };
  }

  return { error: null, warning: null };
}

/**
 * Returns minute string YYYY-MM-DDTHH:MM for duplicate detection.
 */
export function minuteKey(timeStr) {
  if (!timeStr) return null;
  return timeStr.slice(0, 16);
}

/**
 * Finds duplicate minutes among a list of events.
 * Returns a Set of event IDs that share a minute with at least one other event.
 */
export function findDuplicateMinuteIds(events) {
  if (!Array.isArray(events)) return new Set();
  const minuteToIds = {};
  for (const ev of events) {
    const key = minuteKey(ev.time);
    if (!key) continue;
    if (!minuteToIds[key]) minuteToIds[key] = [];
    minuteToIds[key].push(ev.id);
  }
  const duplicateIds = new Set();
  for (const ids of Object.values(minuteToIds)) {
    if (ids.length > 1) {
      ids.forEach(id => duplicateIds.add(id));
    }
  }
  return duplicateIds;
}

/**
 * Constructs the three-state payloads for the API:
 *   1. NOT AVAILABLE: null
 *   2. AVAILABLE, no events in window: []
 *   3. AVAILABLE with events: [{ timestamp, units/rate/carbs }]
 *
 * Filters events:
 *   - Only bolus and carb events from the last 7 hours relative to latestTimestamp.
 *   - Basal rate valid up to 24 hours prior to latestTimestamp.
 *   - Events after latestTimestamp are excluded.
 */
export function buildEventPayloads({
  insulinEnabled = false,
  carbsEnabled = false,
  bolusEvents = [],
  basalRate = null,
  carbEvents = [],
  latestTimestamp = null,
  forceNull = false,
}) {
  if (forceNull) {
    return { bolusEvents: null, basalEvents: null, carbEvents: null };
  }

  const cutoff = latestTimestamp ? new Date(latestTimestamp) : null;
  const sevenHoursAgo = cutoff ? new Date(cutoff.getTime() - 7 * 60 * 60 * 1000) : null;
  const twentyFourHoursAgo = cutoff ? new Date(cutoff.getTime() - 24 * 60 * 60 * 1000) : null;

  // 1. Bolus payload
  let payloadBolusEvents = null;
  if (insulinEnabled) {
    payloadBolusEvents = (bolusEvents || [])
      .filter(ev => ev && ev.time && ev.units !== '' && ev.units !== undefined)
      .filter(ev => {
        const t = new Date(ev.time);
        if (cutoff && t > cutoff) return false;
        if (sevenHoursAgo && t < sevenHoursAgo) return false;
        return true;
      })
      .map(ev => ({
        timestamp: new Date(ev.time).toISOString(),
        units: parseFloat(ev.units),
        type: 'bolus'
      }));
  }

  // 2. Basal payload
  let payloadBasalEvents = null;
  if (insulinEnabled) {
    if (basalRate && basalRate.rate !== '' && basalRate.rate !== undefined && basalRate.time) {
      const bTime = new Date(basalRate.time);
      const isNotFuture = !cutoff || bTime <= cutoff;
      const isWithin24h = !twentyFourHoursAgo || bTime >= twentyFourHoursAgo;
      if (isNotFuture && isWithin24h) {
        payloadBasalEvents = [{
          timestamp: bTime.toISOString(),
          rate: parseFloat(basalRate.rate),
          type: 'basal'
        }];
      } else {
        payloadBasalEvents = [];
      }
    } else {
      payloadBasalEvents = [];
    }
  }

  // 3. Carb payload
  let payloadCarbEvents = null;
  if (carbsEnabled) {
    payloadCarbEvents = (carbEvents || [])
      .filter(ev => ev && ev.time && ev.grams !== '' && ev.grams !== undefined)
      .filter(ev => {
        const t = new Date(ev.time);
        if (cutoff && t > cutoff) return false;
        if (sevenHoursAgo && t < sevenHoursAgo) return false;
        return true;
      })
      .map(ev => ({
        timestamp: new Date(ev.time).toISOString(),
        carbs: parseFloat(ev.grams)
      }));
  }

  return {
    bolusEvents: payloadBolusEvents,
    basalEvents: payloadBasalEvents,
    carbEvents: payloadCarbEvents
  };
}

/**
 * Computes median differences per horizon between multimodal forecast and cgm-only forecast.
 * Returns array of { step, horizon_minutes, diff_mg_dl, multimodal_median, cgmonly_median }
 */
export function computeHorizonDifferences(multimodalForecast, cgmOnlyForecast) {
  if (!Array.isArray(multimodalForecast) || !Array.isArray(cgmOnlyForecast)) return [];
  const cgmMap = new Map();
  for (const step of cgmOnlyForecast) {
    cgmMap.set(step.step, step.glucose_median);
  }

  return multimodalForecast.map(mStep => {
    const cgmMed = cgmMap.get(mStep.step);
    const diff = cgmMed !== undefined ? Math.round((mStep.glucose_median - cgmMed) * 10) / 10 : 0.0;
    return {
      step: mStep.step,
      horizon_minutes: mStep.horizon_minutes,
      diff_mg_dl: diff,
      multimodal_median: mStep.glucose_median,
      cgmonly_median: cgmMed
    };
  });
}
