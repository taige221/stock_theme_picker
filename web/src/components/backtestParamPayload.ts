import type {
  BacktestPreset,
  BacktestPresetSaveRequest,
  BacktestRunDetailResponse,
  BacktestRunExecuteRequest,
} from '../api/backtests';
import type { ParamDraft, ParamDraftValue } from './BacktestParamEditor';

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function cloneRecord(value: unknown): Record<string, unknown> {
  return isRecord(value) ? JSON.parse(JSON.stringify(value)) as Record<string, unknown> : {};
}

function firstString(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim();
  }
  return undefined;
}

function recordString(record: unknown, key: string): string | undefined {
  if (!isRecord(record)) return undefined;
  const value = record[key];
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function latestImportedVersion(preset: BacktestPreset | null): NonNullable<BacktestPreset['importedVersions']>[number] | null {
  return preset?.importedVersions?.[0] ?? null;
}

function parseStockCodes(value: unknown): string[] | null {
  if (Array.isArray(value)) {
    const codes = value.map((item) => String(item).trim().toUpperCase()).filter(Boolean);
    return codes.length ? codes : null;
  }
  if (typeof value !== 'string' || !value.trim()) return null;
  const codes = value
    .split(/[\s,，;；]+/)
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
  return codes.length ? Array.from(new Set(codes)) : null;
}

function valueAtPath(payload: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((current, segment) => {
    if (!isRecord(current)) return undefined;
    return current[segment];
  }, payload);
}

function setValueAtPath(payload: Record<string, unknown>, path: string, value: unknown): void {
  const segments = path.split('.');
  let current: Record<string, unknown> = payload;
  segments.forEach((segment, index) => {
    if (index === segments.length - 1) {
      current[segment] = value;
      return;
    }
    if (!isRecord(current[segment])) current[segment] = {};
    current = current[segment] as Record<string, unknown>;
  });
}

function coerceDraftValue(value: ParamDraftValue, original: unknown): unknown {
  if (value === null) return null;
  if (typeof original === 'number') {
    if (value === '') return null;
    const numericValue = Number(value);
    return Number.isFinite(numericValue) ? numericValue : original;
  }
  if (typeof original === 'boolean') return value === true;
  if ((Array.isArray(original) || isRecord(original)) && typeof value === 'string') {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

function buildBasePayload(
  detail: BacktestRunDetailResponse | null,
  preset: BacktestPreset | null,
): Record<string, unknown> {
  const strategyCard = detail?.strategyCard;
  const presetParams = cloneRecord(preset?.params);
  const defaultParams = cloneRecord(preset?.defaultParams);
  const runParams = cloneRecord(strategyCard?.params);
  const importedVersion = latestImportedVersion(preset);
  return {
    range: {
      startDate: detail?.run.startDate ?? importedVersion?.startDate ?? '2024-01-01',
      endDate: detail?.run.endDate ?? importedVersion?.endDate ?? '2024-12-31',
    },
    stockPool: cloneRecord(strategyCard?.stockPool ?? preset?.stockPool),
    stockCodes: '',
    capital: cloneRecord(strategyCard?.capital ?? preset?.capital),
    constraints: cloneRecord(strategyCard?.constraints ?? preset?.constraints),
    config: cloneRecord(strategyCard?.config ?? preset?.config),
    params: {
      ...defaultParams,
      ...presetParams,
      ...runParams,
    },
  };
}

export function buildBacktestMutationPayload(
  detail: BacktestRunDetailResponse | null,
  preset: BacktestPreset | null,
  draft: ParamDraft,
): BacktestRunExecuteRequest & BacktestPresetSaveRequest {
  const base = buildBasePayload(detail, preset);
  Object.entries(draft).forEach(([path, value]) => {
    setValueAtPath(base, path, coerceDraftValue(value, valueAtPath(base, path)));
  });

  const constraints = cloneRecord(base.constraints);
  const stockPool = cloneRecord(base.stockPool);
  const importedVersion = latestImportedVersion(preset);
  const strategy = preset?.strategy ?? detail?.run.strategy ?? 'a_share_box';
  const sourceRunId = firstString(detail?.run.runId, preset?.importedRunId, importedVersion?.runId);
  const stockCodes = parseStockCodes(base.stockCodes);
  const stockPoolPath = firstString(
    recordString(stockPool, 'sourcePath'),
    recordString(stockPool, 'source_path'),
  );
  const range = cloneRecord(base.range);

  return {
    presetId: preset?.presetId ?? detail?.run.strategy ?? 'a_share_box',
    sourceRunId,
    name: firstString(preset?.name, detail?.run.name, 'A股箱体策略') ?? 'A股箱体策略',
    strategy,
    strategyVersion: detail?.run.strategyVersion ?? preset?.strategyVersion,
    stockPool,
    capital: cloneRecord(base.capital),
    constraints,
    config: cloneRecord(base.config),
    params: cloneRecord(base.params),
    startDate: firstString(range.startDate, range.start_date, detail?.run.startDate, importedVersion?.startDate, '2024-01-01') ?? '2024-01-01',
    endDate: firstString(range.endDate, range.end_date, detail?.run.endDate, importedVersion?.endDate, '2024-12-31') ?? '2024-12-31',
    priceAdjustment: firstString(
      recordString(constraints, 'priceAdjustment'),
      recordString(constraints, 'price_adjustment'),
      'qfq',
    ),
    tradingConstraints: firstString(
      recordString(constraints, 'tradingConstraints'),
      recordString(constraints, 'trading_constraints'),
      'daily_limits',
    ),
    stockPoolPath: stockCodes ? null : stockPoolPath,
    stockCodes,
    baseRunId: sourceRunId,
    importDb: true,
    equityMode: 'traded_daily',
  };
}
