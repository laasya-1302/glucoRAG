import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  validateBolus,
  validateBasal,
  validateCarb,
  findDuplicateMinuteIds,
  buildEventPayloads,
  computeHorizonDifferences,
} from '../utils/multimodal.js';

describe('Multimodal Inputs Validation & Payloads', () => {

  describe('Bolus validation', () => {
    const latestTimestamp = '2026-10-27T12:00:00';

    it('accepts valid normal bolus (e.g. 5 U)', () => {
      const res = validateBolus({ time: '2026-10-27T11:45:00', units: '5' }, latestTimestamp);
      assert.equal(res.error, null);
      assert.equal(res.warning, null);
    });

    it('warns on high dose above 17 U (e.g. 18 U)', () => {
      const res = validateBolus({ time: '2026-10-27T11:45:00', units: '18' }, latestTimestamp);
      assert.equal(res.error, null);
      assert.match(res.warning, /High dose/);
    });

    it('rejects doses exceeding 40 U (e.g. 45 U)', () => {
      const res = validateBolus({ time: '2026-10-27T11:45:00', units: '45' }, latestTimestamp);
      assert.match(res.error, /must not exceed 40 U/);
    });

    it('rejects negative bolus doses', () => {
      const res = validateBolus({ time: '2026-10-27T11:45:00', units: '-2' }, latestTimestamp);
      assert.match(res.error, /cannot be negative/);
    });

    it('rejects bolus event with future time relative to latest glucose reading', () => {
      const res = validateBolus({ time: '2026-10-27T12:05:00', units: '4' }, latestTimestamp);
      assert.match(res.error, /must not be after the latest glucose reading/);
    });
  });

  describe('Basal validation', () => {
    const latestTimestamp = '2026-10-27T12:00:00';

    it('accepts valid basal rate (e.g. 0.9 U/h)', () => {
      const res = validateBasal({ time: '2026-10-27T08:00:00', rate: '0.9' }, latestTimestamp);
      assert.equal(res.error, null);
    });

    it('rejects basal rate exceeding 5 U/h (e.g. 6.5 U/h)', () => {
      const res = validateBasal({ time: '2026-10-27T08:00:00', rate: '6.5' }, latestTimestamp);
      assert.match(res.error, /must not exceed 5 U\/h/);
    });

    it('rejects negative basal rate', () => {
      const res = validateBasal({ time: '2026-10-27T08:00:00', rate: '-0.5' }, latestTimestamp);
      assert.match(res.error, /cannot be negative/);
    });

    it('rejects basal record with future time relative to latest glucose reading', () => {
      const res = validateBasal({ time: '2026-10-27T12:15:00', rate: '1.0' }, latestTimestamp);
      assert.match(res.error, /must not be after the latest glucose reading/);
    });
  });

  describe('Carb validation', () => {
    const latestTimestamp = '2026-10-27T12:00:00';

    it('accepts valid carb intake (e.g. 50 g)', () => {
      const res = validateCarb({ time: '2026-10-27T11:30:00', grams: '50' }, latestTimestamp);
      assert.equal(res.error, null);
      assert.equal(res.warning, null);
    });

    it('warns on large meal above 120 g (e.g. 130 g)', () => {
      const res = validateCarb({ time: '2026-10-27T11:30:00', grams: '130' }, latestTimestamp);
      assert.equal(res.error, null);
      assert.match(res.warning, /Large meal/);
    });

    it('rejects carbs exceeding 370 g (e.g. 400 g)', () => {
      const res = validateCarb({ time: '2026-10-27T11:30:00', grams: '400' }, latestTimestamp);
      assert.match(res.error, /must not exceed 370 g/);
    });

    it('rejects negative carbs', () => {
      const res = validateCarb({ time: '2026-10-27T11:30:00', grams: '-10' }, latestTimestamp);
      assert.match(res.error, /cannot be negative/);
    });

    it('rejects carb event with future time relative to latest glucose reading', () => {
      const res = validateCarb({ time: '2026-10-27T12:01:00', grams: '45' }, latestTimestamp);
      assert.match(res.error, /must not be after the latest glucose reading/);
    });
  });

  describe('Duplicate minute detection', () => {
    it('detects events that share the same minute', () => {
      const events = [
        { id: 'ev1', time: '2026-10-27T11:15:20' },
        { id: 'ev2', time: '2026-10-27T11:15:45' },
        { id: 'ev3', time: '2026-10-27T11:30:00' }
      ];
      const dupes = findDuplicateMinuteIds(events);
      assert.equal(dupes.has('ev1'), true);
      assert.equal(dupes.has('ev2'), true);
      assert.equal(dupes.has('ev3'), false);
    });
  });

  describe('Three-State API Payload Generation', () => {
    const latestTimestamp = '2026-10-27T12:00:00';

    it('State 1: Both toggles off -> all channels null (not available)', () => {
      const payload = buildEventPayloads({
        insulinEnabled: false,
        carbsEnabled: false,
        bolusEvents: [{ id: '1', time: '2026-10-27T11:00:00', units: '5' }],
        basalRate: { time: '2026-10-27T08:00:00', rate: '1.0' },
        carbEvents: [{ id: '2', time: '2026-10-27T11:00:00', grams: '60' }],
        latestTimestamp
      });

      assert.equal(payload.bolusEvents, null);
      assert.equal(payload.basalEvents, null);
      assert.equal(payload.carbEvents, null);
    });

    it('State 2: Toggles on with no events -> channels are empty arrays [] (available, no events)', () => {
      const payload = buildEventPayloads({
        insulinEnabled: true,
        carbsEnabled: true,
        bolusEvents: [],
        basalRate: null,
        carbEvents: [],
        latestTimestamp
      });

      assert.deepEqual(payload.bolusEvents, []);
      assert.deepEqual(payload.basalEvents, []);
      assert.deepEqual(payload.carbEvents, []);
    });

    it('State 3: Toggles on with valid events within window -> populated arrays', () => {
      const payload = buildEventPayloads({
        insulinEnabled: true,
        carbsEnabled: true,
        bolusEvents: [
          { id: 'b1', time: '2026-10-27T10:00:00', units: '4.5' }
        ],
        basalRate: { time: '2026-10-27T06:00:00', rate: '0.85' },
        carbEvents: [
          { id: 'c1', time: '2026-10-27T10:00:00', grams: '45' }
        ],
        latestTimestamp
      });

      assert.equal(payload.bolusEvents.length, 1);
      assert.equal(payload.bolusEvents[0].units, 4.5);
      assert.equal(payload.bolusEvents[0].type, 'bolus');

      assert.equal(payload.basalEvents.length, 1);
      assert.equal(payload.basalEvents[0].rate, 0.85);
      assert.equal(payload.basalEvents[0].type, 'basal');

      assert.equal(payload.carbEvents.length, 1);
      assert.equal(payload.carbEvents[0].carbs, 45);
    });

    it('Filters out events older than 7 hours', () => {
      const payload = buildEventPayloads({
        insulinEnabled: true,
        carbsEnabled: true,
        bolusEvents: [
          { id: 'old', time: '2026-10-27T04:30:00', units: '5' }, // 7.5 hours ago -> filtered
          { id: 'recent', time: '2026-10-27T08:00:00', units: '3' } // 4 hours ago -> included
        ],
        basalRate: null,
        carbEvents: [
          { id: 'old_carb', time: '2026-10-27T03:00:00', grams: '50' }, // 9 hours ago -> filtered
          { id: 'recent_carb', time: '2026-10-27T10:00:00', grams: '30' } // 2 hours ago -> included
        ],
        latestTimestamp
      });

      assert.equal(payload.bolusEvents.length, 1);
      assert.equal(payload.bolusEvents[0].units, 3);

      assert.equal(payload.carbEvents.length, 1);
      assert.equal(payload.carbEvents[0].carbs, 30);
    });

    it('Basal rate valid up to 24 hours prior', () => {
      // 20 hours ago -> valid
      const payloadValid = buildEventPayloads({
        insulinEnabled: true,
        carbsEnabled: false,
        basalRate: { time: '2026-10-26T16:00:00', rate: '0.9' },
        latestTimestamp
      });
      assert.equal(payloadValid.basalEvents.length, 1);

      // 25 hours ago -> invalid / outside 24h -> returns []
      const payloadOld = buildEventPayloads({
        insulinEnabled: true,
        carbsEnabled: false,
        basalRate: { time: '2026-10-26T10:00:00', rate: '0.9' },
        latestTimestamp
      });
      assert.deepEqual(payloadOld.basalEvents, []);
    });

    it('forceNull=true always forces null across all channels (BLE streaming mode)', () => {
      const payload = buildEventPayloads({
        insulinEnabled: true,
        carbsEnabled: true,
        bolusEvents: [{ id: '1', time: '2026-10-27T11:00:00', units: '5' }],
        basalRate: { time: '2026-10-27T08:00:00', rate: '1.0' },
        carbEvents: [{ id: '2', time: '2026-10-27T11:00:00', grams: '60' }],
        latestTimestamp,
        forceNull: true
      });

      assert.equal(payload.bolusEvents, null);
      assert.equal(payload.basalEvents, null);
      assert.equal(payload.carbEvents, null);
    });
  });

  describe('Horizon differences comparison', () => {
    it('computes per-horizon differences accurately', () => {
      const multimodalForecast = [
        { step: 1, horizon_minutes: 15, glucose_median: 140.2 },
        { step: 2, horizon_minutes: 30, glucose_median: 142.5 }
      ];
      const cgmOnlyForecast = [
        { step: 1, horizon_minutes: 15, glucose_median: 139.0 },
        { step: 2, horizon_minutes: 30, glucose_median: 143.0 }
      ];

      const diffs = computeHorizonDifferences(multimodalForecast, cgmOnlyForecast);
      assert.equal(diffs.length, 2);
      assert.equal(diffs[0].diff_mg_dl, 1.2);
      assert.equal(diffs[1].diff_mg_dl, -0.5);
    });
  });
});
