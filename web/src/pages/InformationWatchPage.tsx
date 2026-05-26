import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ChevronDown, ChevronUp, ExternalLink, Newspaper, RefreshCw, Search, Sparkles } from 'lucide-react';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import {
  informationWatchApi,
  type InformationWatchEvent,
  type InformationWatchItem,
  type InformationWatchItemUpsertPayload,
  type InformationWatchRunOnceResponse,
  type OpenDiscoveryCandidate,
  type OpenDiscoveryProfile,
  type OpenDiscoveryRunOnceResponse,
} from '../api/informationWatch';
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, InlineAlert, PaperListBlock, PaperSectionCard, PaperSectionHeader } from '../components/common';

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const EVENT_TYPE_OPTIONS = [
  { value: 'order', label: '订单/采购' },
  { value: 'capacity_expand', label: '扩产/投产' },
  { value: 'mass_production', label: '量产/交付' },
  { value: 'price_signal', label: '涨价/价格' },
  { value: 'policy_catalyst', label: '政策/放行' },
  { value: 'technology_progress', label: '技术进展' },
  { value: 'capital_expenditure', label: '资本开支' },
  { value: 'risk_signal', label: '风险事件' },
  { value: 'opinion_only', label: '观点解读' },
] as const;

const DIRECTION_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'high_priority', label: '高优先级' },
  { key: 'positive', label: '仅正向' },
  { key: 'negative', label: '仅风险' },
  { key: 'watch_hit', label: '观察池命中' },
] as const;

const SOURCE_TIERS = [
  { key: 'L1', label: '交易所公告' },
  { key: 'L2', label: '主流财经媒体' },
  { key: 'L3', label: '社区/股吧' },
] as const;

const TIME_RANGES = [
  { key: '1h', label: '1H' },
  { key: 'today', label: '今日' },
  { key: 'yesterday', label: '昨日' },
  { key: 'week', label: '本周' },
] as const;

type DirectionKey = (typeof DIRECTION_FILTERS)[number]['key'];
type TimeRangeKey = (typeof TIME_RANGES)[number]['key'];
type SortMode = 'impact' | 'time' | 'theme';

const DISCOVERY_TEMPLATE_SCROLL_CLASS = 'max-h-[360px] overflow-y-auto pr-1';
const DISCOVERY_CANDIDATE_SCROLL_CLASS = 'max-h-[430px] overflow-y-auto pr-1';
const DISCOVERY_EVENT_SCROLL_CLASS = 'max-h-[420px] overflow-y-auto pr-1';
const WATCH_ITEM_SCROLL_CLASS = 'max-h-[360px] overflow-y-auto pr-1';

/* ------------------------------------------------------------------ */
/*  Utility functions                                                  */
/* ------------------------------------------------------------------ */

function splitTokens(value: string): string[] {
  return value.split(/[,\n/，、]+/).map((item) => item.trim()).filter(Boolean);
}

function formatDateTime(value?: string | null): string {
  if (!value) return '暂无时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function formatTimeOnly(value?: string | null): string {
  if (!value) return '--:--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--:--';
  return date.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function formatRelativeTime(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const diff = Date.now() - date.getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

function eventTypeLabel(eventType: string): string {
  return { order: '订单/采购', capacity_expand: '扩产/投产', mass_production: '量产/交付', price_signal: '涨价/价格', policy_catalyst: '政策/放行', technology_progress: '技术进展', capital_expenditure: '资本开支', risk_signal: '风险事件', opinion_only: '观点解读' }[eventType] ?? eventType;
}

function tierVariant(sourceTier?: string | null): 'default' | 'success' | 'warning' | 'info' {
  if (sourceTier === 'L1') return 'success';
  if (sourceTier === 'L2') return 'info';
  if (sourceTier === 'L3') return 'warning';
  return 'default';
}

function tierLabel(sourceTier?: string | null): string {
  if (sourceTier === 'L1') return '公告/监管';
  if (sourceTier === 'L2') return '主流媒体';
  if (sourceTier === 'L3') return '社区/弱源';
  return sourceTier ?? '';
}

function directionLabel(direction?: string | null): string {
  if (direction === 'positive') return '正向';
  if (direction === 'negative') return '负向';
  return '中性';
}

function directionVariant(direction?: string | null): 'success' | 'danger' | 'default' {
  if (direction === 'positive') return 'success';
  if (direction === 'negative') return 'danger';
  return 'default';
}

function statusVariant(status: string): 'default' | 'success' | 'warning' | 'info' {
  if (status === 'promoted') return 'success';
  if (status === 'repeated') return 'warning';
  if (status === 'new') return 'info';
  return 'default';
}

interface EventGroup {
  key: string;
  label: string;
  watchItemId: string | null;
  events: InformationWatchEvent[];
  status: 'TRIGGERED' | 'WATCH' | 'COOLING';
  avgStrength: number;
}

function deriveGroupStatus(events: InformationWatchEvent[]): 'TRIGGERED' | 'WATCH' | 'COOLING' {
  if (events.some((e) => e.status === 'promoted')) return 'TRIGGERED';
  if (events.every((e) => e.status === 'repeated')) return 'COOLING';
  return 'WATCH';
}

function groupStatusVariant(status: string): 'danger' | 'warning' | 'default' {
  if (status === 'TRIGGERED') return 'danger';
  if (status === 'WATCH') return 'warning';
  return 'default';
}

function createEmptyDraft(): Required<Pick<InformationWatchItemUpsertPayload, 'name' | 'eventType'>> & {
  itemId?: string;
  seedTermsText: string;
  aliasesText: string;
  themesText: string;
  chainTagsText: string;
  notes: string;
  freshnessDays: string;
  allowL1: boolean;
  allowL2: boolean;
  allowL3: boolean;
} {
  return { itemId: undefined, name: '', eventType: 'order', seedTermsText: '', aliasesText: '', themesText: '', chainTagsText: '', notes: '', freshnessDays: '3', allowL1: true, allowL2: true, allowL3: false };
}

function mapItemToDraft(item: InformationWatchItem) {
  return { itemId: item.itemId, name: item.name, eventType: item.eventType, seedTermsText: item.seedTerms.join(', '), aliasesText: item.aliases.join(', '), themesText: item.themes.join(', '), chainTagsText: item.chainTags.join(', '), notes: item.notes ?? '', freshnessDays: String(item.freshnessDays ?? 3), allowL1: item.sourceTiers.includes('L1'), allowL2: item.sourceTiers.includes('L2'), allowL3: item.sourceTiers.includes('L3') };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const InformationWatchPage: React.FC = () => {
  /* ---- existing data state ---- */
  const [items, setItems] = useState<InformationWatchItem[]>([]);
  const [events, setEvents] = useState<InformationWatchEvent[]>([]);
  const [discoveryProfiles, setDiscoveryProfiles] = useState<OpenDiscoveryProfile[]>([]);
  const [discoveryEvents, setDiscoveryEvents] = useState<InformationWatchEvent[]>([]);
  const [discoveryCandidates, setDiscoveryCandidates] = useState<OpenDiscoveryCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runningDiscovery, setRunningDiscovery] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [actionError, setActionError] = useState<ParsedApiError | null>(null);
  const [runSummary, setRunSummary] = useState<InformationWatchRunOnceResponse | null>(null);
  const [discoveryRunSummary, setDiscoveryRunSummary] = useState<OpenDiscoveryRunOnceResponse | null>(null);
  const [savingItem, setSavingItem] = useState(false);
  const [deletingItemId, setDeletingItemId] = useState<string | null>(null);
  const [promotingEventId, setPromotingEventId] = useState<string | null>(null);
  const [promotingCandidateKey, setPromotingCandidateKey] = useState<string | null>(null);
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [draft, setDraft] = useState(createEmptyDraft);
  const formAnchorRef = useRef<HTMLDivElement | null>(null);

  /* ---- signal feed UI state ---- */
  const [searchQuery, setSearchQuery] = useState('');
  const [sortMode, setSortMode] = useState<SortMode>('time');
  const [directionFilter, setDirectionFilter] = useState<DirectionKey>('all');
  const [sourceTierFilter, setSourceTierFilter] = useState<Set<string>>(new Set());
  const [timeRange, setTimeRange] = useState<TimeRangeKey>('today');
  const [showManagement, setShowManagement] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  /* ---- data loading ---- */

  const loadData = useCallback(async (): Promise<void> => {
    try {
      setError(null);
      const [itemsResponse, eventsResponse, discoveryProfilesResponse, discoveryEventsResponse, discoveryCandidatesResponse] = await Promise.all([
        informationWatchApi.listItems(),
        informationWatchApi.listEvents(80),
        informationWatchApi.listDiscoveryProfiles(),
        informationWatchApi.listDiscoveryEvents(18, true),
        informationWatchApi.listDiscoveryCandidates(12, true),
      ]);
      setItems(itemsResponse.items);
      setEvents(eventsResponse.items);
      setDiscoveryProfiles(discoveryProfilesResponse.items);
      setDiscoveryEvents(discoveryEventsResponse.items);
      setDiscoveryCandidates(discoveryCandidatesResponse.items);
    } catch (requestError) {
      setError(getParsedApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  /* ---- action handlers ---- */

  const handleRunOnce = useCallback(async (): Promise<void> => {
    try { setRunning(true); setActionError(null); const response = await informationWatchApi.runOnce({ limit: 20 }); setRunSummary(response); await loadData(); } catch (requestError) { setActionError(getParsedApiError(requestError)); } finally { setRunning(false); }
  }, [loadData]);

  const handleRunDiscoveryOnce = useCallback(async (): Promise<void> => {
    try { setRunningDiscovery(true); setActionError(null); const response = await informationWatchApi.runDiscoveryOnce({ limit: 8 }); setDiscoveryRunSummary(response); await loadData(); } catch (requestError) { setActionError(getParsedApiError(requestError)); } finally { setRunningDiscovery(false); }
  }, [loadData]);

  const handleCreateItem = useCallback(async (): Promise<void> => {
    try {
      setSavingItem(true); setActionError(null);
      await informationWatchApi.upsertItem({
        itemId: draft.itemId, name: draft.name.trim(), eventType: draft.eventType,
        seedTerms: splitTokens(draft.seedTermsText), aliases: splitTokens(draft.aliasesText),
        themes: splitTokens(draft.themesText), chainTags: splitTokens(draft.chainTagsText),
        sourceTiers: [draft.allowL1 ? 'L1' : null, draft.allowL2 ? 'L2' : null, draft.allowL3 ? 'L3' : null].filter(Boolean) as string[],
        freshnessDays: Number(draft.freshnessDays || 3), notes: draft.notes.trim() || null,
      });
      setDraft(createEmptyDraft()); setEditingItemId(null); await loadData();
    } catch (requestError) { setActionError(getParsedApiError(requestError)); } finally { setSavingItem(false); }
  }, [draft, loadData]);

  const handleEditItem = useCallback((item: InformationWatchItem): void => { setEditingItemId(item.itemId); setDraft(mapItemToDraft(item)); }, []);
  const handleCancelEdit = useCallback((): void => { setEditingItemId(null); setDraft(createEmptyDraft()); }, []);

  const handleDeleteItem = useCallback(async (item: InformationWatchItem): Promise<void> => {
    if (!window.confirm(`确认删除观察项「${item.name}」吗？`)) return;
    try { setDeletingItemId(item.itemId); setActionError(null); await informationWatchApi.deleteItem(item.itemId); await loadData(); } catch (requestError) { setActionError(getParsedApiError(requestError)); } finally { setDeletingItemId(null); }
  }, [loadData]);

  const focusFormCard = useCallback((): void => { window.requestAnimationFrame(() => { formAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }); }, []);

  const handlePromoteDiscoveryEvent = useCallback(async (event: InformationWatchEvent): Promise<void> => {
    const linkedItemId = String(event.watchItemId ?? '').trim();
    if (linkedItemId) { const existing = items.find((i) => i.itemId === linkedItemId); if (existing) { handleEditItem(existing); focusFormCard(); return; } }
    try { setPromotingEventId(event.eventId); setActionError(null); const item = await informationWatchApi.promoteDiscoveryEventToWatchItem(event.eventId); setEditingItemId(item.itemId); setDraft(mapItemToDraft(item)); await loadData(); focusFormCard(); } catch (requestError) { setActionError(getParsedApiError(requestError)); } finally { setPromotingEventId(null); }
  }, [focusFormCard, handleEditItem, items, loadData]);

  const handlePromoteDiscoveryCandidate = useCallback(async (candidate: OpenDiscoveryCandidate): Promise<void> => {
    const linkedItemId = String(candidate.watchItemId ?? '').trim();
    if (linkedItemId) { const existing = items.find((i) => i.itemId === linkedItemId); if (existing) { handleEditItem(existing); focusFormCard(); return; } }
    try { setPromotingCandidateKey(candidate.clusterKey); setActionError(null); const item = await informationWatchApi.promoteDiscoveryCandidateToWatchItem(candidate.clusterKey); setEditingItemId(item.itemId); setDraft(mapItemToDraft(item)); await loadData(); focusFormCard(); } catch (requestError) { setActionError(getParsedApiError(requestError)); } finally { setPromotingCandidateKey(null); }
  }, [focusFormCard, handleEditItem, items, loadData]);

  /* ---- derived data ---- */

  const filteredEvents = useMemo(() => {
    let result = events;
    // search
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter((e) => e.title.toLowerCase().includes(q) || (e.summary ?? '').toLowerCase().includes(q) || (e.watchItemName ?? '').toLowerCase().includes(q) || e.themes.some((t) => t.toLowerCase().includes(q)) || e.chainTags.some((t) => t.toLowerCase().includes(q)));
    }
    // direction
    if (directionFilter === 'high_priority') result = result.filter((e) => e.status === 'promoted');
    else if (directionFilter === 'positive') result = result.filter((e) => e.impactDirection === 'positive');
    else if (directionFilter === 'negative') result = result.filter((e) => e.impactDirection === 'negative' || e.impactDirection === 'risk');
    else if (directionFilter === 'watch_hit') result = result.filter((e) => e.watchItemId != null);
    // source tier
    if (sourceTierFilter.size > 0) result = result.filter((e) => sourceTierFilter.has(e.sourceTier));
    // time range
    const now = new Date();
    if (timeRange === '1h') { const cutoff = new Date(now.getTime() - 3600000); result = result.filter((e) => e.publishedAt && new Date(e.publishedAt) >= cutoff); }
    else if (timeRange === 'today') { const start = new Date(now); start.setHours(0, 0, 0, 0); result = result.filter((e) => e.publishedAt && new Date(e.publishedAt) >= start); }
    else if (timeRange === 'yesterday') { const start = new Date(now); start.setDate(start.getDate() - 1); start.setHours(0, 0, 0, 0); const end = new Date(now); end.setHours(0, 0, 0, 0); result = result.filter((e) => e.publishedAt && new Date(e.publishedAt) >= start && new Date(e.publishedAt) < end); }
    else if (timeRange === 'week') { const start = new Date(now); start.setDate(start.getDate() - 7); result = result.filter((e) => e.publishedAt && new Date(e.publishedAt) >= start); }
    // sort
    if (sortMode === 'impact') result = [...result].sort((a, b) => b.signalStrength - a.signalStrength);
    else if (sortMode === 'time') result = [...result].sort((a, b) => new Date(b.publishedAt ?? b.createdAt ?? 0).getTime() - new Date(a.publishedAt ?? a.createdAt ?? 0).getTime());
    else if (sortMode === 'theme') result = [...result].sort((a, b) => (a.watchItemName ?? '').localeCompare(b.watchItemName ?? ''));
    return result;
  }, [events, searchQuery, directionFilter, sourceTierFilter, timeRange, sortMode]);

  const eventGroups = useMemo((): EventGroup[] => {
    const map = new Map<string, { label: string; watchItemId: string | null; events: InformationWatchEvent[] }>();
    for (const event of filteredEvents) {
      const key = event.watchItemName ?? event.clusterLabel ?? eventTypeLabel(event.eventType);
      if (!map.has(key)) map.set(key, { label: key, watchItemId: event.watchItemId ?? null, events: [] });
      map.get(key)!.events.push(event);
    }
    return Array.from(map.values()).map((g) => ({
      key: g.label,
      label: g.label,
      watchItemId: g.watchItemId,
      events: g.events,
      status: deriveGroupStatus(g.events),
      avgStrength: g.events.length > 0 ? Math.round(g.events.reduce((sum, e) => sum + e.signalStrength, 0) / g.events.length) : 0,
    }));
  }, [filteredEvents]);

  const feedStats = useMemo(() => {
    const highPriority = events.filter((e) => e.status === 'promoted').length;
    const uniqueThemes = new Set(events.map((e) => e.watchItemName).filter(Boolean));
    const uniqueEntities = new Set(events.flatMap((e) => [...e.themes, ...e.chainTags]));
    return { total: events.length, highPriority, themes: uniqueThemes.size, entities: uniqueEntities.size };
  }, [events]);

  const filterCounts = useMemo(() => ({
    all: events.length,
    high_priority: events.filter((e) => e.status === 'promoted').length,
    positive: events.filter((e) => e.impactDirection === 'positive').length,
    negative: events.filter((e) => e.impactDirection === 'negative' || e.impactDirection === 'risk').length,
    watch_hit: events.filter((e) => e.watchItemId != null).length,
  }), [events]);

  const sourceCounts = useMemo(() => ({
    L1: events.filter((e) => e.sourceTier === 'L1').length,
    L2: events.filter((e) => e.sourceTier === 'L2').length,
    L3: events.filter((e) => e.sourceTier === 'L3').length,
  }), [events]);

  const triggeredThemes = useMemo(() => {
    const countMap = new Map<string, { count: number; hasPromoted: boolean }>();
    for (const e of events) {
      if (!e.watchItemId) continue;
      const name = e.watchItemName ?? e.watchItemId;
      const prev = countMap.get(name) ?? { count: 0, hasPromoted: false };
      countMap.set(name, { count: prev.count + 1, hasPromoted: prev.hasPromoted || e.status === 'promoted' });
    }
    return Array.from(countMap.entries()).map(([name, v]) => ({ name, ...v })).sort((a, b) => b.count - a.count).slice(0, 8);
  }, [events]);

  const keywordCloud = useMemo(() => {
    const freq = new Map<string, number>();
    for (const event of events) { for (const tag of [...event.themes, ...event.chainTags]) { freq.set(tag, (freq.get(tag) ?? 0) + 1); } }
    return Array.from(freq.entries()).sort((a, b) => b[1] - a[1]).slice(0, 16).map(([tag, count]) => ({ tag, count }));
  }, [events]);

  const toggleSourceTier = (tier: string) => {
    setSourceTierFilter((prev) => { const next = new Set(prev); if (next.has(tier)) next.delete(tier); else next.add(tier); return next; });
  };

  const toggleGroupExpand = (key: string) => {
    setExpandedGroups((prev) => { const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  };

  /* ================================================================ */
  /*  RENDER                                                           */
  /* ================================================================ */

  return (
    <AppPage className="!max-w-none space-y-5">

      {/* ---- Search bar ---- */}
      <div className="search-bar-card flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <Search className="h-4 w-4 shrink-0 text-secondary-text" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="输入关键词、主题或股票名称筛选..."
            className="min-w-0 flex-1 border-0 bg-transparent text-sm text-foreground outline-none placeholder:text-secondary-text/60"
          />
        </div>
        <div className="flex items-center gap-1 text-xs">
          <span className="text-secondary-text">排序:</span>
          {([['impact', '影响力'], ['time', '时间'], ['theme', '主题']] as const).map(([key, label]) => (
            <button key={key} type="button" onClick={() => setSortMode(key)} className={`rounded-md px-2.5 py-1 transition-colors ${sortMode === key ? 'bg-foreground text-background' : 'text-secondary-text hover:text-foreground'}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* ---- Hero stats ---- */}
      <Card padding="lg" className="!rounded-2xl">
        <div className="grid gap-6 lg:grid-cols-[1fr_auto]">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">信息观察池 · Information Pool</p>
            <h2 className="mt-2 text-2xl font-bold tracking-tight text-foreground md:text-3xl">
              今日新增 <span className="rounded bg-foreground/10 px-1.5">{feedStats.total}</span> 条触发信号，
              <span className="rounded bg-foreground/10 px-1.5">{feedStats.highPriority}</span> 项处于高优先级
            </h2>
            <p className="mt-3 text-sm leading-6 text-secondary-text">过滤后池中信息按主题归并展示。下方为今日重点线索 — 已自动按主题聚合，影响力降序排列。</p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button size="lg" isLoading={running} loadingText="扫描中..." onClick={() => void handleRunOnce()}>立即扫描</Button>
            <Button variant="secondary" size="lg" onClick={() => void loadData()} isLoading={loading} loadingText="刷新中...">
              <RefreshCw className="h-4 w-4" /> 刷新
            </Button>
          </div>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-4">
          <div className="rounded-xl border border-border/60 px-4 py-3">
            <p className="text-xs text-secondary-text">今日新增</p>
            <p className="mt-1 text-2xl font-bold text-foreground">{feedStats.total}</p>
          </div>
          <div className="rounded-xl border border-border/60 px-4 py-3">
            <p className="text-xs text-secondary-text">高优先级</p>
            <p className="mt-1 text-2xl font-bold text-foreground">{feedStats.highPriority}</p>
            <p className="mt-0.5 text-[11px] text-secondary-text">需立即查看</p>
          </div>
          <div className="rounded-xl border border-border/60 px-4 py-3">
            <p className="text-xs text-secondary-text">关联主题</p>
            <p className="mt-1 text-2xl font-bold text-foreground">{feedStats.themes}</p>
            <p className="mt-0.5 text-[11px] text-secondary-text">其中 {triggeredThemes.filter((t) => t.hasPromoted).length} 项已触发</p>
          </div>
          <div className="rounded-xl border border-border/60 px-4 py-3">
            <p className="text-xs text-secondary-text">关联标的</p>
            <p className="mt-1 text-2xl font-bold text-foreground">{feedStats.entities}</p>
            <p className="mt-0.5 text-[11px] text-secondary-text">观察池命中 {filterCounts.watch_hit}</p>
          </div>
        </div>
      </Card>

      {/* ---- Alerts ---- */}
      {error ? <ApiErrorAlert error={error} /> : null}
      {actionError ? <ApiErrorAlert error={actionError} /> : null}
      {runSummary ? <InlineAlert variant="success" title="扫描完成" message={`扫描 ${runSummary.scannedItems} 个观察项，生成 ${runSummary.createdEvents} 条事件，${runSummary.promotedEvents} 条高质量。`} /> : null}
      {discoveryRunSummary ? <InlineAlert variant="success" title="开放发现扫描完成" message={`扫描 ${discoveryRunSummary.scannedProfiles} 个模板，生成 ${discoveryRunSummary.createdEvents} 条事件。`} /> : null}

      {/* ---- 3-Column Feed ---- */}
      <section className="grid gap-5 xl:grid-cols-[220px_1fr_280px]">

        {/* LEFT SIDEBAR */}
        <div className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          {/* Filters */}
          <Card padding="md" className="!rounded-2xl">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">筛选 · Filters</p>
              {directionFilter !== 'all' ? <span className="text-[11px] text-secondary-text">已应用 1</span> : null}
            </div>
            <div className="mt-3 space-y-0.5">
              {DIRECTION_FILTERS.map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setDirectionFilter(f.key)}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors ${directionFilter === f.key ? 'bg-foreground text-background' : 'text-foreground hover:bg-elevated/40'}`}
                >
                  <span>{f.label}</span>
                  <span className={`text-xs tabular-nums ${directionFilter === f.key ? 'text-background/70' : 'text-secondary-text'}`}>{filterCounts[f.key]}</span>
                </button>
              ))}
            </div>
          </Card>

          {/* Sources */}
          <Card padding="md" className="!rounded-2xl">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">来源 · Sources</p>
            <div className="mt-3 space-y-2">
              {SOURCE_TIERS.map((s) => (
                <label key={s.key} className="flex cursor-pointer items-center justify-between text-sm">
                  <span className="flex items-center gap-2">
                    <input type="checkbox" checked={sourceTierFilter.size === 0 || sourceTierFilter.has(s.key)} onChange={() => toggleSourceTier(s.key)} className="accent-foreground" />
                    <span className="text-foreground">{s.label}</span>
                  </span>
                  <span className="text-xs tabular-nums text-secondary-text">{sourceCounts[s.key as keyof typeof sourceCounts]}</span>
                </label>
              ))}
            </div>
          </Card>

          {/* Time range */}
          <Card padding="md" className="!rounded-2xl">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">时间范围 · Range</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {TIME_RANGES.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  onClick={() => setTimeRange(t.key)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${timeRange === t.key ? 'bg-foreground text-background' : 'border border-border/60 text-secondary-text hover:text-foreground'}`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </Card>
        </div>

        {/* CENTER FEED */}
        <div className="min-w-0 space-y-4">
          {/* Feed header */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-secondary-text">
              <span className="font-semibold text-foreground">{filteredEvents.length}</span> 条信号
              {' · '}<span className="font-semibold text-foreground">{filterCounts.high_priority}</span> 高优先级
              {' · '}<span className="font-semibold text-foreground">{eventGroups.filter((g) => g.status === 'TRIGGERED').length}</span> 触发主题
            </p>
            <div className="flex items-center gap-2">
              <Badge variant="success" size="sm">实时数据</Badge>
              <Badge variant="default" size="sm">自动归并</Badge>
            </div>
          </div>

          {/* Grouped events */}
          {eventGroups.map((group) => {
            const isExpanded = expandedGroups.has(group.key);
            const visibleEvents = isExpanded ? group.events : group.events.slice(0, 3);
            return (
              <Card key={group.key} padding="lg" className={`!rounded-2xl ${group.status === 'TRIGGERED' ? 'border-l-[3px] border-l-danger/60' : ''}`}>
                {/* Group header */}
                <div className="flex items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-base font-semibold text-foreground">{group.label}</h4>
                    <Badge variant={groupStatusVariant(group.status)} size="sm" className={group.status === 'TRIGGERED' ? 'border-danger/30 bg-danger/90 text-white' : ''}>{group.status}</Badge>
                    <span className="text-xs text-secondary-text">{group.events.length} 条信号</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-secondary-text">影响力</span>
                    {Array.from({ length: 5 }, (_, i) => (
                      <span key={i} className={`inline-block h-2 w-2 rounded-full ${i < Math.ceil(group.avgStrength / 20) ? 'bg-danger' : 'bg-border/40'}`} />
                    ))}
                  </div>
                </div>

                {/* Event list */}
                <div className="mt-3 space-y-3">
                  {visibleEvents.map((event) => (
                    <div key={event.eventId} className="rounded-xl border border-border/40 px-4 py-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-secondary-text">
                        <span className="font-semibold text-foreground">{formatTimeOnly(event.publishedAt)}</span>
                        <span>{formatRelativeTime(event.publishedAt)}</span>
                        <span>·</span>
                        <span>{event.provider ?? event.sourceHost ?? tierLabel(event.sourceTier)}</span>
                        {event.impactDirection ? (
                          <Badge variant={directionVariant(event.impactDirection)} size="sm">{directionLabel(event.impactDirection)}{event.signalStrength > 0 ? ` ${event.impactDirection === 'negative' ? '−' : '+'}${(event.signalStrength / 100).toFixed(2)}` : ''}</Badge>
                        ) : null}
                      </div>
                      <h5 className="mt-1.5 text-sm font-semibold text-foreground">{event.title}</h5>
                      {event.summary ? <p className="mt-1 line-clamp-2 text-xs leading-5 text-secondary-text">{event.summary}</p> : null}
                      {event.themes.length > 0 || event.chainTags.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {event.themes.map((t) => <span key={`${event.eventId}-t-${t}`} className="rounded-md bg-foreground/5 px-2 py-0.5 text-[11px] text-secondary-text">#{t}</span>)}
                          {event.chainTags.map((t) => <span key={`${event.eventId}-c-${t}`} className="rounded-md bg-foreground/5 px-2 py-0.5 text-[11px] text-secondary-text">#{t}</span>)}
                        </div>
                      ) : null}
                      {event.url ? (
                        <a href={event.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-[11px] text-secondary-text hover:text-foreground">
                          原文 <ExternalLink className="h-3 w-3" />
                        </a>
                      ) : null}
                    </div>
                  ))}
                </div>

                {/* Expand / collapse */}
                {group.events.length > 3 ? (
                  <button type="button" onClick={() => toggleGroupExpand(group.key)} className="mt-3 text-xs text-secondary-text hover:text-foreground">
                    {isExpanded ? '收起' : `查看全部 ${group.events.length} 条 →`}
                  </button>
                ) : null}
                {group.events.length > 1 ? (
                  <p className="mt-2 text-right text-[11px] text-secondary-text/60">已自动归并为同一主题线索</p>
                ) : null}
              </Card>
            );
          })}

          {/* Empty */}
          {!loading && filteredEvents.length === 0 ? (
            <EmptyState title="暂无匹配信号" description="调整筛选条件或运行扫描获取信息事件。" icon={<Newspaper className="h-6 w-6" />} action={<Button onClick={() => void handleRunOnce()}>立即扫描</Button>} />
          ) : null}

          {/* Footer */}
          {filteredEvents.length > 0 ? (
            <p className="py-4 text-center text-xs text-secondary-text/60">— 今日信号已全部呈现 —</p>
          ) : null}
        </div>

        {/* RIGHT SIDEBAR */}
        <div className="space-y-4 xl:sticky xl:top-20 xl:self-start">
          {/* Triggered themes */}
          <Card padding="md" className="!rounded-2xl">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">触发中主题 · Triggered</p>
              <span className="text-xs text-secondary-text">{triggeredThemes.length} 项</span>
            </div>
            <div className="mt-3 space-y-2">
              {triggeredThemes.map((theme, i) => (
                <div key={theme.name} className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="shrink-0 text-xs font-bold text-secondary-text/40">{String(i + 1).padStart(2, '0')}</span>
                    <span className="truncate text-sm text-foreground">{theme.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-secondary-text">{theme.count} 条</span>
                    <Badge variant={theme.hasPromoted ? 'danger' : 'default'} size="sm" className={theme.hasPromoted ? 'border-danger/30 bg-danger/90 text-white' : ''}>{theme.hasPromoted ? 'TRIGGERED' : 'WATCH'}</Badge>
                  </div>
                </div>
              ))}
              {triggeredThemes.length === 0 ? <p className="py-3 text-center text-xs text-secondary-text">暂无触发主题</p> : null}
            </div>
          </Card>

          {/* Keyword cloud */}
          <Card padding="md" className="!rounded-2xl">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">热门关键词 · Keywords</p>
              <span className="text-[11px] text-secondary-text">近 24h</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {keywordCloud.map(({ tag, count }) => (
                <button
                  key={tag}
                  type="button"
                  onClick={() => setSearchQuery(tag)}
                  className="rounded-lg border border-border/60 px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-elevated/40"
                >
                  {tag} <span className="text-secondary-text">{count}</span>
                </button>
              ))}
              {keywordCloud.length === 0 ? <p className="py-3 text-center text-xs text-secondary-text">暂无数据</p> : null}
            </div>
          </Card>
        </div>
      </section>

      {/* ---- Collapsible management panel ---- */}
      <div className="border-t border-border/40 pt-4">
        <button type="button" onClick={() => setShowManagement((p) => !p)} className="flex items-center gap-2 text-sm text-secondary-text hover:text-foreground">
          {showManagement ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          {showManagement ? '收起管理面板' : '展开管理面板 · 发现池 / 观察项 / 自定义主题'}
        </button>

        {showManagement ? (
          <div className="mt-5 space-y-6">
            {/* Discovery Pool + Watch Items */}
            <section className="grid gap-5 xl:grid-cols-12">
              <div className="grid gap-5 xl:col-span-5 xl:auto-rows-auto">
                <Card variant="bordered" padding="lg" className="paper-panel rounded-[24px]">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <span className="label-uppercase">Open Discovery Pool</span>
                      <h3 className="mt-1 text-2xl font-semibold text-foreground">开放发现池</h3>
                      <p className="mt-2 text-sm leading-6 text-secondary-text">不预设具体股票或单一主题，直接按高价值事件模板扫全局信息。</p>
                    </div>
                    <Badge variant="info" className="border-0 px-3 py-1">{discoveryProfiles.length} 个模板</Badge>
                  </div>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button size="lg" isLoading={runningDiscovery} loadingText="扫描中..." onClick={() => void handleRunDiscoveryOnce()}>开始开放发现</Button>
                    <Button variant="secondary" size="lg" onClick={() => void loadData()} isLoading={loading} loadingText="刷新中..."><RefreshCw className="h-4 w-4" /> 刷新</Button>
                  </div>
                  <div className={`mt-5 space-y-3 ${DISCOVERY_TEMPLATE_SCROLL_CLASS}`}>
                    {discoveryProfiles.map((profile) => (
                      <div key={profile.profileId} className="paper-list-card px-4 py-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <h4 className="text-base font-semibold text-foreground">{profile.name}</h4>
                            <p className="mt-1 text-sm text-secondary-text">{eventTypeLabel(profile.eventType)}</p>
                          </div>
                          <Badge variant={profile.enabled ? 'success' : 'default'} className="border-0 px-3 py-1">{profile.enabled ? '启用' : '停用'}</Badge>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {profile.queryTemplates.slice(0, 2).map((template) => (<Badge key={`${profile.profileId}-${template}`} variant="default" className="border-border/60 px-3 py-1">{template}</Badge>))}
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>

                <PaperSectionCard eyebrow="Watch Items" title="当前观察主题" icon={<Sparkles className="h-5 w-5" />}>
                  <div className={`space-y-3 ${WATCH_ITEM_SCROLL_CLASS}`}>
                    {items.map((item) => (
                      <PaperListBlock key={item.itemId}>
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <h4 className="text-base font-semibold text-foreground">{item.name}</h4>
                            <p className="mt-1 text-sm text-secondary-text">{eventTypeLabel(item.eventType)}</p>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge variant={item.isSystem ? 'info' : 'default'} className="border-0 px-3 py-1">{item.isSystem ? '系统内置' : '自定义'}</Badge>
                            <Badge variant={item.enabled ? 'success' : 'default'} className="border-0 px-3 py-1">{item.enabled ? '启用' : '停用'}</Badge>
                            <Button variant="secondary" size="sm" onClick={() => handleEditItem(item)}>编辑</Button>
                            <Button variant="ghost" size="sm" onClick={() => void handleDeleteItem(item)} disabled={item.isSystem} isLoading={deletingItemId === item.itemId} loadingText="删除中...">{item.isSystem ? '内置保护' : '删除'}</Button>
                          </div>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {item.seedTerms.slice(0, 4).map((term) => (<Badge key={`${item.itemId}-${term}`} variant="default" className="border-border/60 px-3 py-1">{term}</Badge>))}
                        </div>
                      </PaperListBlock>
                    ))}
                  </div>
                </PaperSectionCard>
              </div>

              <div className="grid gap-5 xl:col-span-7 xl:auto-rows-auto">
                {/* Discovery Candidates */}
                <Card variant="bordered" padding="lg" className="paper-panel rounded-[24px]">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <span className="label-uppercase">Discovery Candidates</span>
                      <h3 className="mt-1 text-2xl font-semibold text-foreground">开放发现候选主题</h3>
                    </div>
                    <Badge variant="default" className="border-border/60 px-3 py-1">{discoveryCandidates.length} 组</Badge>
                  </div>
                  <div className={`mt-5 space-y-3 ${DISCOVERY_CANDIDATE_SCROLL_CLASS}`}>
                    {!loading && discoveryCandidates.length === 0 ? <EmptyState title="还没有候选主题" description="先跑几轮开放发现池。" icon={<Sparkles className="h-6 w-6" />} /> : null}
                    {discoveryCandidates.map((candidate) => (
                      <div key={candidate.clusterKey} className="paper-list-card px-5 py-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="info" className="border-0 px-3 py-1">{eventTypeLabel(candidate.eventType)}</Badge>
                          <Badge variant={candidate.hardSourceConfirmed ? 'success' : 'default'} className="border-0 px-3 py-1">{candidate.hardSourceConfirmed ? 'L1 已确认' : '待硬源确认'}</Badge>
                          {candidate.watchItemName ? <Badge variant="success" className="border-0 px-3 py-1">已沉淀：{candidate.watchItemName}</Badge> : null}
                        </div>
                        <div className="mt-3">
                          <h4 className="text-lg font-semibold text-foreground">{candidate.label}</h4>
                          <p className="mt-2 text-sm text-secondary-text">{candidate.representativeTitle ?? '暂无代表标题'} · {formatDateTime(candidate.latestPublishedAt)}</p>
                        </div>
                        <div className="mt-4 flex flex-wrap items-center gap-3">
                          <Button variant={candidate.watchItemId ? 'secondary' : 'primary'} size="sm" onClick={() => void handlePromoteDiscoveryCandidate(candidate)} isLoading={promotingCandidateKey === candidate.clusterKey} loadingText={candidate.watchItemId ? '定位中...' : '加入中...'}>{candidate.watchItemId ? '编辑观察项' : '加入观察池'}</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>

                {/* Discovery Events */}
                <Card variant="bordered" padding="lg" className="paper-panel rounded-[24px]">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <span className="label-uppercase">Discovery Events</span>
                      <h3 className="mt-1 text-2xl font-semibold text-foreground">最近发现事件</h3>
                    </div>
                    <Badge variant="default" className="border-border/60 px-3 py-1">{discoveryEvents.length} 条</Badge>
                  </div>
                  <div className={`mt-5 space-y-3 ${DISCOVERY_EVENT_SCROLL_CLASS}`}>
                    {!loading && discoveryEvents.length === 0 ? <EmptyState title="还没有开放发现事件" description="先跑一轮开放发现池。" icon={<Sparkles className="h-6 w-6" />} action={<Button onClick={() => void handleRunDiscoveryOnce()}>开始第一次开放发现</Button>} /> : null}
                    {discoveryEvents.map((event) => (
                      <div key={event.eventId} className="paper-list-card px-5 py-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant="info" className="border-0 px-3 py-1">discovery</Badge>
                          <Badge variant={statusVariant(event.status)} className="border-0 px-3 py-1">{event.status}</Badge>
                          <Badge variant={tierVariant(event.sourceTier)} className="border-0 px-3 py-1">{event.sourceTier}</Badge>
                          {event.watchItemName ? <Badge variant="success" className="border-0 px-3 py-1">已关联：{event.watchItemName}</Badge> : null}
                        </div>
                        <div className="mt-3 flex items-start justify-between gap-4">
                          <div className="min-w-0 flex-1">
                            <h4 className="text-lg font-semibold text-foreground">{event.title}</h4>
                            {event.summary ? <p className="mt-2 text-sm leading-6 text-secondary-text">{event.summary}</p> : null}
                          </div>
                          {event.url ? <a href={event.url} target="_blank" rel="noreferrer" className="paper-chip-link shrink-0">原文 <ExternalLink className="h-3.5 w-3.5" /></a> : null}
                        </div>
                        <div className="mt-4 flex flex-wrap items-center gap-3">
                          <Button variant={event.watchItemId ? 'secondary' : 'primary'} size="sm" onClick={() => void handlePromoteDiscoveryEvent(event)} isLoading={promotingEventId === event.eventId} loadingText={event.watchItemId ? '定位中...' : '加入中...'}>{event.watchItemId ? '编辑观察项' : '加入观察池'}</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            </section>

            {/* Custom Watch Item Form */}
            <section className="grid gap-5 xl:grid-cols-12">
              <div className="xl:col-span-7">
                <div ref={formAnchorRef} />
                <Card variant="bordered" padding="lg" className="paper-panel rounded-[24px]">
                  <PaperSectionHeader eyebrow="Custom Watch Item" title={editingItemId ? '编辑观察主题' : '自定义观察主题'} icon={<Sparkles className="h-5 w-5" />} />
                  <div className="mt-5 grid gap-3">
                    <label className="grid gap-2">
                      <span className="text-sm font-medium text-foreground">观察主题名</span>
                      <input value={draft.name} onChange={(e) => setDraft((c) => ({ ...c, name: e.target.value }))} placeholder="例如：HBM 扩产、液冷订单" className="paper-form-control h-11 text-sm" />
                    </label>
                    <label className="grid gap-2">
                      <span className="text-sm font-medium text-foreground">事件类型</span>
                      <select value={draft.eventType} onChange={(e) => setDraft((c) => ({ ...c, eventType: e.target.value }))} className="paper-form-control h-11 text-sm">
                        {EVENT_TYPE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </select>
                    </label>
                    <label className="grid gap-2">
                      <span className="text-sm font-medium text-foreground">主检索词</span>
                      <textarea value={draft.seedTermsText} onChange={(e) => setDraft((c) => ({ ...c, seedTermsText: e.target.value }))} placeholder="逗号分隔" rows={3} className="paper-form-control text-sm" />
                    </label>
                    <label className="grid gap-2">
                      <span className="text-sm font-medium text-foreground">别名 / 主题 / 产业链标签</span>
                      <div className="grid gap-3 md:grid-cols-3">
                        <input value={draft.aliasesText} onChange={(e) => setDraft((c) => ({ ...c, aliasesText: e.target.value }))} placeholder="别名" className="paper-form-control h-11 text-sm" />
                        <input value={draft.themesText} onChange={(e) => setDraft((c) => ({ ...c, themesText: e.target.value }))} placeholder="主题" className="paper-form-control h-11 text-sm" />
                        <input value={draft.chainTagsText} onChange={(e) => setDraft((c) => ({ ...c, chainTagsText: e.target.value }))} placeholder="标签" className="paper-form-control h-11 text-sm" />
                      </div>
                    </label>
                    <label className="grid gap-2">
                      <span className="text-sm font-medium text-foreground">时间窗口与来源层级</span>
                      <div className="grid gap-3 md:grid-cols-[120px_1fr]">
                        <input value={draft.freshnessDays} onChange={(e) => setDraft((c) => ({ ...c, freshnessDays: e.target.value }))} placeholder="3" className="paper-form-control h-11 text-sm" />
                        <div className="paper-panel-muted flex flex-wrap gap-3 px-4 py-3 text-sm text-secondary-text">
                          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={draft.allowL1} onChange={(e) => setDraft((c) => ({ ...c, allowL1: e.target.checked }))} /> L1 公告/监管</label>
                          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={draft.allowL2} onChange={(e) => setDraft((c) => ({ ...c, allowL2: e.target.checked }))} /> L2 主流媒体</label>
                          <label className="inline-flex items-center gap-2"><input type="checkbox" checked={draft.allowL3} onChange={(e) => setDraft((c) => ({ ...c, allowL3: e.target.checked }))} /> L3 解读/弱源</label>
                        </div>
                      </div>
                    </label>
                    <label className="grid gap-2">
                      <span className="text-sm font-medium text-foreground">备注</span>
                      <textarea value={draft.notes} onChange={(e) => setDraft((c) => ({ ...c, notes: e.target.value }))} placeholder="说明为什么值得长期跟踪" rows={2} className="paper-form-control text-sm" />
                    </label>
                    <div className="flex flex-wrap gap-3">
                      <Button onClick={() => void handleCreateItem()} isLoading={savingItem} loadingText={editingItemId ? '更新中...' : '保存中...'} disabled={!draft.name.trim() || splitTokens(draft.seedTermsText).length === 0}>{editingItemId ? '更新观察项' : '保存观察项'}</Button>
                      {editingItemId ? <Button variant="secondary" onClick={handleCancelEdit}>取消编辑</Button> : null}
                    </div>
                  </div>
                </Card>
              </div>
              <div className="xl:col-span-5">
                <Card variant="bordered" padding="lg" className="paper-panel rounded-[24px]">
                  <PaperSectionHeader eyebrow="How It Drives Search" title="检索驱动规则" icon={<Activity className="h-5 w-5" />} />
                  <div className="mt-5 space-y-3 text-sm leading-6 text-secondary-text">
                    <div className="paper-list-card px-4 py-4">观察项按"事件新闻 / 市场反应 / 风险排查"三种意图拆开检索。</div>
                    <div className="paper-list-card px-4 py-4">只有新鲜度与可信度都过线的事件，才会继续喂给"主题因子扫描"。</div>
                    <div className="paper-list-card px-4 py-4">`L1` 公告/监管/官方口径，`L2` 主流媒体或快讯确认，`L3` 市场反应、研报解读或弱源。</div>
                  </div>
                </Card>
              </div>
            </section>
          </div>
        ) : null}
      </div>
    </AppPage>
  );
};

export default InformationWatchPage;
