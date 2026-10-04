import { z } from 'zod';
import { apiRequestPath } from '../../api/client';
import type { ABTestReport, ExtractionData, MetricsData } from './types';

const optionalNumber = z.number().optional();
const extractionNumber = z.number().nullish().transform(value => value ?? undefined);
const optionalString = z.string().optional();
const MetricsSchema = z.looseObject({
  total_calls: optionalNumber, stock_attempts: optionalNumber, stock_success: optionalNumber,
  weather_attempts: optionalNumber, weather_success: optionalNumber,
  exchange_attempts: optionalNumber, exchange_success: optionalNumber,
  speculative_filtered: optionalNumber,
  success_rates: z.looseObject({ overall: optionalNumber, stock: optionalNumber, weather: optionalNumber, exchange: optionalNumber }).optional(),
});

export const ExtractionDataSchema = z.looseObject({
  query: z.string(), search_length: z.number(), has_top1_json: z.boolean(),
  extracted: z.looseObject({
    stock_prices: z.array(z.looseObject({
      name: optionalString, ticker: optionalString, close_price: extractionNumber,
      open_price: extractionNumber, high_price: extractionNumber, low_price: extractionNumber,
      change_percent: extractionNumber, change_amount: extractionNumber, volume: extractionNumber,
    })),
    weather: z.array(z.looseObject({ location: optionalString, temperature: extractionNumber, humidity: extractionNumber, condition: optionalString })),
    exchange_rates: z.array(z.looseObject({ currency_pair: optionalString, rate: extractionNumber, change_percent: extractionNumber })),
    dates_found: z.array(z.string()),
  }),
  extraction_log: optionalString,
});

const ABTestReportSchema = z.looseObject({
  avg_accuracy: z.number(), avg_duration_ms: z.number(), total_cases: z.number(), passed: z.number(), failed: z.number(),
  by_tag: z.record(z.string(), z.number()).optional(),
  comparisons: z.array(z.looseObject({
    case_name: z.string(), accuracy_pct: z.number(), fields_matched: z.number(),
    fields_total: z.number(), duration_ms: z.number(), has_expected: z.boolean(),
  })).optional(),
});

const FailureSchema = z.object({ ok: z.literal(false), error: optionalString });
const MetricsResponseSchema = z.object({ ok: z.literal(true), metrics: MetricsSchema.nullish() });
const ExtractionResponseSchema = ExtractionDataSchema.extend({ ok: z.literal(true) });
const ABTestResponseSchema = z.object({ ok: z.literal(true), report: ABTestReportSchema });

export class ExtractionApiError extends Error {
  readonly name = 'ExtractionApiError';
  constructor(readonly operation: string, message: string) {
    super(message);
  }
}

function parseResponse<T>(schema: z.ZodType<T>, raw: unknown, operation: string): T {
  const failure = FailureSchema.safeParse(raw);
  if (failure.success) throw new ExtractionApiError(operation, failure.data.error ?? `${operation} 요청에 실패했습니다.`);
  return schema.parse(raw);
}

export async function loadExtractionMetrics(): Promise<MetricsData | null> {
  const raw = await apiRequestPath('/api/search/extraction-metrics');
  return parseResponse(MetricsResponseSchema, raw, '메트릭').metrics ?? null;
}

export async function searchExtraction(query: string): Promise<ExtractionData> {
  const raw = await apiRequestPath('/api/search/extract', { method: 'POST', body: JSON.stringify({ query }) });
  return parseResponse(ExtractionResponseSchema, raw, '데이터 추출');
}

export async function runExtractionABTest(): Promise<ABTestReport> {
  const raw = await apiRequestPath('/api/search/ab-test/run', { method: 'POST', body: JSON.stringify({ version_label: 'dashboard' }) });
  return parseResponse(ABTestResponseSchema, raw, 'A/B 테스트').report;
}
