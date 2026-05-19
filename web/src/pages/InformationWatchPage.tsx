import type React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ExternalLink, Newspaper, RefreshCw, Sparkles, TowerControl } from 'lucide-react';
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
import { ApiErrorAlert, AppPage, Badge, Button, Card, EmptyState, InlineAlert, Select } from '../components/common';

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

const EVENT_STATUS_OPTIONS = [
  { value: 'all', label: '全部事件' },
  { value: 'promoted', label: '仅高质量事件' },
  { value: 'new', label: '仅新事件' },
  { value: 'repeated', label: '仅重复事件' },
] as const;

function splitTokens(value: string): string[] {
  return value
    .split(/[,\n/，、]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDateTime(value?: string | null): string {
  if (!value) return '暂无时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function eventTypeLabel(eventType: string): string {
  return {
    order: '订单/采购',
    capacity_expand: '扩产/投产',
    mass_production: '量产/交付',
    price_signal: '涨价/价格',
    policy_catalyst: '政策/放行',
    technology_progress: '技术进展',
    capital_expenditure: '资本开支',
    risk_signal: '风险事件',
    opinion_only: '观点解读',
  }[eventType] ?? eventType;
}

function statusVariant(status: string): 'default' | 'success' | 'warning' | 'info' {
  if (status === 'promoted') return 'success';
  if (status === 'repeated') return 'warning';
  if (status === 'new') return 'info';
  return 'default';
}

function tierVariant(sourceTier?: string | null): 'default' | 'success' | 'warning' | 'info' {
  if (sourceTier === 'L1') return 'success';
  if (sourceTier === 'L2') return 'info';
  if (sourceTier === 'L3') return 'warning';
  return 'default';
}

function sourceTierHint(sourceTier?: string | null): string {
  if (sourceTier === 'L1') return '公告/监管/官方口径';
  if (sourceTier === 'L2') return '主流媒体/快讯确认';
  if (sourceTier === 'L3') return '市场反应/研报解读/弱源';
  return '待判定';
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
  return {
    itemId: undefined,
    name: '',
    eventType: 'order',
    seedTermsText: '',
    aliasesText: '',
    themesText: '',
    chainTagsText: '',
    notes: '',
    freshnessDays: '3',
    allowL1: true,
    allowL2: true,
    allowL3: false,
  };
}

function mapItemToDraft(item: InformationWatchItem) {
  return {
    itemId: item.itemId,
    name: item.name,
    eventType: item.eventType,
    seedTermsText: item.seedTerms.join(', '),
    aliasesText: item.aliases.join(', '),
    themesText: item.themes.join(', '),
    chainTagsText: item.chainTags.join(', '),
    notes: item.notes ?? '',
    freshnessDays: String(item.freshnessDays ?? 3),
    allowL1: item.sourceTiers.includes('L1'),
    allowL2: item.sourceTiers.includes('L2'),
    allowL3: item.sourceTiers.includes('L3'),
  };
}

const InformationWatchPage: React.FC = () => {
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
  const [eventStatusFilter, setEventStatusFilter] = useState<(typeof EVENT_STATUS_OPTIONS)[number]['value']>('all');
  const [draft, setDraft] = useState(createEmptyDraft);
  const formAnchorRef = useRef<HTMLDivElement | null>(null);

  const loadData = useCallback(async (): Promise<void> => {
    try {
      setError(null);
      const promotedOnly = eventStatusFilter === 'promoted';
      const status = eventStatusFilter === 'all' || eventStatusFilter === 'promoted' ? undefined : eventStatusFilter;
      const [itemsResponse, eventsResponse, discoveryProfilesResponse, discoveryEventsResponse, discoveryCandidatesResponse] = await Promise.all([
        informationWatchApi.listItems(),
        informationWatchApi.listEvents(30, promotedOnly, status),
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
  }, [eventStatusFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const handleRunOnce = useCallback(async (): Promise<void> => {
    try {
      setRunning(true);
      setActionError(null);
      const response = await informationWatchApi.runOnce({ limit: 20 });
      setRunSummary(response);
      await loadData();
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setRunning(false);
    }
  }, [loadData]);

  const handleRunDiscoveryOnce = useCallback(async (): Promise<void> => {
    try {
      setRunningDiscovery(true);
      setActionError(null);
      const response = await informationWatchApi.runDiscoveryOnce({ limit: 8 });
      setDiscoveryRunSummary(response);
      await loadData();
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setRunningDiscovery(false);
    }
  }, [loadData]);

  const handleCreateItem = useCallback(async (): Promise<void> => {
    try {
      setSavingItem(true);
      setActionError(null);
      await informationWatchApi.upsertItem({
        itemId: draft.itemId,
        name: draft.name.trim(),
        eventType: draft.eventType,
        seedTerms: splitTokens(draft.seedTermsText),
        aliases: splitTokens(draft.aliasesText),
        themes: splitTokens(draft.themesText),
        chainTags: splitTokens(draft.chainTagsText),
        sourceTiers: [
          draft.allowL1 ? 'L1' : null,
          draft.allowL2 ? 'L2' : null,
          draft.allowL3 ? 'L3' : null,
        ].filter(Boolean) as string[],
        freshnessDays: Number(draft.freshnessDays || 3),
        notes: draft.notes.trim() || null,
      });
      setDraft(createEmptyDraft());
      setEditingItemId(null);
      await loadData();
    } catch (requestError) {
      setActionError(getParsedApiError(requestError));
    } finally {
      setSavingItem(false);
    }
  }, [draft, loadData]);

  const handleEditItem = useCallback((item: InformationWatchItem): void => {
    setEditingItemId(item.itemId);
    setDraft(mapItemToDraft(item));
  }, []);

  const handleCancelEdit = useCallback((): void => {
    setEditingItemId(null);
    setDraft(createEmptyDraft());
  }, []);

  const handleDeleteItem = useCallback(
    async (item: InformationWatchItem): Promise<void> => {
      if (!window.confirm(`确认删除观察项「${item.name}」吗？删除后后续扫描将不再使用它。`)) {
        return;
      }
      try {
        setDeletingItemId(item.itemId);
        setActionError(null);
        await informationWatchApi.deleteItem(item.itemId);
        await loadData();
      } catch (requestError) {
        setActionError(getParsedApiError(requestError));
      } finally {
        setDeletingItemId(null);
      }
    },
    [loadData],
  );

  const focusFormCard = useCallback((): void => {
    window.requestAnimationFrame(() => {
      formAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, []);

  const handlePromoteDiscoveryEvent = useCallback(
    async (event: InformationWatchEvent): Promise<void> => {
      const linkedItemId = String(event.watchItemId ?? '').trim();
      if (linkedItemId) {
        const existing = items.find((item) => item.itemId === linkedItemId);
        if (existing) {
          handleEditItem(existing);
          focusFormCard();
          return;
        }
      }
      try {
        setPromotingEventId(event.eventId);
        setActionError(null);
        const item = await informationWatchApi.promoteDiscoveryEventToWatchItem(event.eventId);
        setEditingItemId(item.itemId);
        setDraft(mapItemToDraft(item));
        await loadData();
        focusFormCard();
      } catch (requestError) {
        setActionError(getParsedApiError(requestError));
      } finally {
        setPromotingEventId(null);
      }
    },
    [focusFormCard, handleEditItem, items, loadData],
  );

  const handlePromoteDiscoveryCandidate = useCallback(
    async (candidate: OpenDiscoveryCandidate): Promise<void> => {
      const linkedItemId = String(candidate.watchItemId ?? '').trim();
      if (linkedItemId) {
        const existing = items.find((item) => item.itemId === linkedItemId);
        if (existing) {
          handleEditItem(existing);
          focusFormCard();
          return;
        }
      }
      try {
        setPromotingCandidateKey(candidate.clusterKey);
        setActionError(null);
        const item = await informationWatchApi.promoteDiscoveryCandidateToWatchItem(candidate.clusterKey);
        setEditingItemId(item.itemId);
        setDraft(mapItemToDraft(item));
        await loadData();
        focusFormCard();
      } catch (requestError) {
        setActionError(getParsedApiError(requestError));
      } finally {
        setPromotingCandidateKey(null);
      }
    },
    [focusFormCard, handleEditItem, items, loadData],
  );

  const stats = useMemo(() => {
    const enabledItems = items.filter((item) => item.enabled).length;
    const promotedEvents = events.filter((event) => event.status === 'promoted').length;
    const tier1Events = events.filter((event) => event.sourceTier === 'L1').length;
    const discoveryPromoted = discoveryEvents.filter((event) => event.status === 'promoted').length;
    return { enabledItems, promotedEvents, tier1Events, discoveryPromoted };
  }, [discoveryEvents, events, items]);

  return (
    <AppPage className="space-y-6 !max-w-[1680px] px-3 md:px-5 lg:px-6">
      <section className="overflow-hidden rounded-[32px] border border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(6,182,212,0.18),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(59,130,246,0.16),_transparent_28%),linear-gradient(180deg,rgba(255,255,255,0.98),rgba(246,249,252,0.96))] shadow-soft-card dark:bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.18),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(59,130,246,0.14),_transparent_28%),linear-gradient(180deg,rgba(10,15,26,0.98),rgba(14,20,32,0.96))]">
        <div className="grid gap-6 px-5 py-6 lg:grid-cols-[1.15fr_0.85fr] lg:px-7 lg:py-7">
          <div className="space-y-5">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan/10 text-cyan shadow-soft-card">
                <TowerControl className="h-7 w-7" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Information Watch Pool</p>
                <h2 className="mt-1 text-3xl font-semibold tracking-tight text-foreground">先盯产业信息，再决定扫什么主题</h2>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-secondary-text">
                  这层负责每天扫描高价值产业触发点，把新闻、公告和解读归并成结构化事件，再交给主题因子扫描继续确认。
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">启用观察项</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{stats.enabledItems}</p>
                <p className="mt-2 text-sm text-secondary-text">当前以事件型主题为主，不直接扫大板块噪音。</p>
              </Card>
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">高质量事件</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{stats.promotedEvents}</p>
                <p className="mt-2 text-sm text-secondary-text">满足新鲜度和可信度门槛，适合进入主题因子层继续确认。</p>
              </Card>
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">一级线索</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">{stats.tier1Events}</p>
                <p className="mt-2 text-sm text-secondary-text">优先保留公告/监管这类硬确认来源，降低旧闻与观点噪音。</p>
              </Card>
            </div>
          </div>

          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/90">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Run Loop</p>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">先扫事件，再推主题</h3>
              </div>
              <Badge variant="info" className="border-0 px-3 py-1">MVP</Badge>
            </div>
            <div className="mt-5 space-y-3">
              <Card variant="bordered" padding="md" className="rounded-[22px] border-border/60 bg-background/75">
                <p className="text-sm font-semibold text-foreground">扫描顺序</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">事件新闻确认 → 市场反应 → 风险排查。先拿到高质量事件，再让主题因子层接手。</p>
              </Card>
              <Card variant="bordered" padding="md" className="rounded-[22px] border-border/60 bg-background/75">
                <p className="text-sm font-semibold text-foreground">当前结果</p>
                <p className="mt-2 text-sm leading-6 text-secondary-text">
                  默认优先保留与观察项本身高度相关的结果，并过滤社媒/通用噪音源，避免把普通网页当成产业催化。
                </p>
              </Card>
              <div className="flex flex-wrap gap-3">
                <Button size="lg" isLoading={running} loadingText="正在扫描信息观察池..." onClick={() => void handleRunOnce()}>
                  立即扫描
                </Button>
                <Button variant="secondary" size="lg" onClick={() => void loadData()} isLoading={loading} loadingText="刷新中...">
                  <RefreshCw className="h-4 w-4" />
                  刷新列表
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </section>

      {error ? <ApiErrorAlert error={error} /> : null}
      {actionError ? <ApiErrorAlert error={actionError} /> : null}
      {runSummary ? (
        <InlineAlert
          variant="success"
          title="本轮扫描已完成"
          message={`本次扫描 ${runSummary.scannedItems} 个观察项，生成 ${runSummary.createdEvents} 条事件，其中 ${runSummary.promotedEvents} 条进入高质量事件池。`}
        />
      ) : null}
      {discoveryRunSummary ? (
        <InlineAlert
          variant="success"
          title="开放发现池扫描已完成"
          message={`本次扫描 ${discoveryRunSummary.scannedProfiles} 个发现模板，生成 ${discoveryRunSummary.createdEvents} 条发现事件，其中 ${discoveryRunSummary.promotedEvents} 条进入高质量事件池。`}
        />
      ) : null}

      <section className="grid gap-5 xl:grid-cols-[0.98fr_1.02fr]">
        <Card variant="bordered" padding="lg" className="rounded-[28px]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="label-uppercase">Open Discovery Pool</span>
              <h3 className="mt-1 text-2xl font-semibold text-foreground">开放发现池</h3>
              <p className="mt-2 text-sm leading-7 text-secondary-text">
                不预设具体股票或单一主题，直接按高价值事件模板扫全局信息，用来发现新的产业链苗头。
              </p>
            </div>
            <Badge variant="info" className="border-0 px-3 py-1">{discoveryProfiles.length} 个模板</Badge>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <Card variant="bordered" padding="md" className="rounded-[22px] border-border/60 bg-card/80">
              <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">发现模板</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">{discoveryProfiles.filter((item) => item.enabled).length}</p>
              <p className="mt-1 text-xs text-secondary-text">订单、扩产、涨价、政策、量产等全局模板。</p>
            </Card>
            <Card variant="bordered" padding="md" className="rounded-[22px] border-border/60 bg-card/80">
              <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">高质量发现</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">{stats.discoveryPromoted}</p>
              <p className="mt-1 text-xs text-secondary-text">这些发现事件会直接进入主题因子层继续确认。</p>
            </Card>
            <Card variant="bordered" padding="md" className="rounded-[22px] border-border/60 bg-card/80">
              <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">发现模式</p>
              <p className="mt-2 text-2xl font-semibold text-foreground">全局探索</p>
              <p className="mt-1 text-xs text-secondary-text">先找事件语义，再反推主题、产业链和候选股。</p>
            </Card>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button size="lg" isLoading={runningDiscovery} loadingText="正在扫描开放发现池..." onClick={() => void handleRunDiscoveryOnce()}>
              开始开放发现
            </Button>
            <Button variant="secondary" size="lg" onClick={() => void loadData()} isLoading={loading} loadingText="刷新中...">
              <RefreshCw className="h-4 w-4" />
              刷新发现结果
            </Button>
          </div>
          <div className="mt-5 space-y-3">
            {discoveryProfiles.map((profile) => (
              <div key={profile.profileId} className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h4 className="text-base font-semibold text-foreground">{profile.name}</h4>
                    <p className="mt-1 text-sm text-secondary-text">{eventTypeLabel(profile.eventType)}</p>
                  </div>
                  <Badge variant={profile.enabled ? 'success' : 'default'} className="border-0 px-3 py-1">
                    {profile.enabled ? '启用' : '停用'}
                  </Badge>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {profile.queryTemplates.slice(0, 2).map((template) => (
                    <Badge key={`${profile.profileId}-${template}`} variant="default" className="border-border/60 px-3 py-1">
                      {template}
                    </Badge>
                  ))}
                </div>
                <p className="mt-3 text-xs leading-6 text-secondary-text">
                  主题倾向：{profile.themes.join(' / ') || '待自动发现'} · 标签：{profile.chainTags.join(' / ') || '未设置'}
                </p>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-5">
          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <span className="label-uppercase">Discovery Candidates</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">开放发现候选主题</h3>
                <p className="mt-2 text-sm leading-7 text-secondary-text">
                  系统会把重复出现、主题标签稳定、且高质量的 discovery 事件聚成候选主题，适合作为长期观察项沉淀。
                </p>
              </div>
              <Badge variant="default" className="border-border/60 px-3 py-1">{discoveryCandidates.length} 组</Badge>
            </div>
            <div className="mt-5 space-y-3">
              {!loading && discoveryCandidates.length === 0 ? (
                <EmptyState
                  title="还没有候选主题"
                  description="先跑几轮开放发现池，系统会把高频重复出现的 discovery 事件自动聚成候选方向。"
                  icon={<Sparkles className="h-6 w-6" />}
                />
              ) : null}
              {discoveryCandidates.map((candidate) => (
                <div key={candidate.clusterKey} className="rounded-[24px] border border-border/60 bg-background/72 px-5 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="info" className="border-0 px-3 py-1">{eventTypeLabel(candidate.eventType)}</Badge>
                    <Badge variant={candidate.hardSourceConfirmed ? 'success' : 'default'} className="border-0 px-3 py-1">
                      {candidate.hardSourceConfirmed ? 'L1 已确认' : '待硬源确认'}
                    </Badge>
                    {candidate.watchItemName ? (
                      <Badge variant="success" className="border-0 px-3 py-1">已沉淀：{candidate.watchItemName}</Badge>
                    ) : null}
                  </div>
                  <div className="mt-3 flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <h4 className="text-lg font-semibold text-foreground">{candidate.label}</h4>
                      <p className="mt-2 text-sm leading-6 text-secondary-text">
                        {candidate.representativeTitle ?? '暂无代表标题'} · 最近更新时间 {formatDateTime(candidate.latestPublishedAt)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">Candidate Score</p>
                      <p className="mt-2 text-2xl font-semibold text-foreground">{candidate.candidateScore.toFixed(0)}</p>
                    </div>
                  </div>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">聚类事件数</p>
                      <p className="mt-2 text-lg font-semibold text-foreground">{candidate.eventCount}</p>
                      <p className="mt-1 text-xs text-secondary-text">其中 promoted {candidate.promotedCount} 条</p>
                    </div>
                    <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">主题/链条</p>
                      <p className="mt-2 text-sm font-semibold text-foreground">
                        {[...candidate.themes.slice(0, 2), ...candidate.chainTags.slice(0, 2)].join(' / ') || '待归纳'}
                      </p>
                      <p className="mt-1 text-xs text-secondary-text">{candidate.sourceHosts.slice(0, 3).join(' · ') || '暂无来源'}</p>
                    </div>
                    <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                      <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">来源层级</p>
                      <p className="mt-2 text-sm font-semibold text-foreground">{candidate.sourceTiers.join(' / ') || '待判定'}</p>
                      <p className="mt-1 text-xs text-secondary-text">{candidate.status === 'linked' ? '已关联观察池' : '可继续沉淀'}</p>
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {candidate.themes.map((theme) => (
                      <Badge key={`${candidate.clusterKey}-${theme}`} variant="info" className="border-0 px-3 py-1">
                        {theme}
                      </Badge>
                    ))}
                    {candidate.chainTags.map((tag) => (
                      <Badge key={`${candidate.clusterKey}-${tag}`} variant="default" className="border-border/60 px-3 py-1">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <Button
                      variant={candidate.watchItemId ? 'secondary' : 'primary'}
                      size="sm"
                      onClick={() => void handlePromoteDiscoveryCandidate(candidate)}
                      isLoading={promotingCandidateKey === candidate.clusterKey}
                      loadingText={candidate.watchItemId ? '定位中...' : '加入中...'}
                    >
                      {candidate.watchItemId ? '编辑观察项' : '加入观察池'}
                    </Button>
                    <p className="text-xs leading-6 text-secondary-text">
                      {candidate.watchItemId ? '这组 discovery 候选已经沉淀为观察项，可直接回填编辑。' : '把整组高频 discovery 候选沉淀成观察主题，后续由观察池持续扫描。'}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="label-uppercase">Discovery Events</span>
              <h3 className="mt-1 text-2xl font-semibold text-foreground">最近发现事件</h3>
            </div>
            <Badge variant="default" className="border-border/60 px-3 py-1">{discoveryEvents.length} 条</Badge>
          </div>
          <div className="mt-5 space-y-3">
            {!loading && discoveryEvents.length === 0 ? (
              <EmptyState
                title="还没有开放发现事件"
                description="先跑一轮开放发现池，系统会从全局高价值事件模板里找新的产业链苗头。"
                icon={<Sparkles className="h-6 w-6" />}
                action={<Button onClick={() => void handleRunDiscoveryOnce()}>开始第一次开放发现</Button>}
              />
            ) : null}
            {discoveryEvents.map((event) => (
              <div key={event.eventId} className="rounded-[24px] border border-border/60 bg-background/72 px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="info" className="border-0 px-3 py-1">discovery</Badge>
                  <Badge variant={statusVariant(event.status)} className="border-0 px-3 py-1">{event.status}</Badge>
                  <Badge variant={tierVariant(event.sourceTier)} className="border-0 px-3 py-1">{event.sourceTier}</Badge>
                  <Badge variant="default" className="border-border/60 px-3 py-1">{eventTypeLabel(event.eventType)}</Badge>
                  {event.sourceHost ? (
                    <Badge variant="default" className="border-border/60 px-3 py-1">{event.sourceHost}</Badge>
                  ) : null}
                  {event.clusterLabel ? (
                    <Badge variant="default" className="border-border/60 px-3 py-1">{event.clusterLabel}</Badge>
                  ) : null}
                  {event.watchItemName ? (
                    <Badge variant="success" className="border-0 px-3 py-1">已关联：{event.watchItemName}</Badge>
                  ) : null}
                </div>
                <div className="mt-3 flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <h4 className="text-lg font-semibold text-foreground">{event.title}</h4>
                    {event.summary ? <p className="mt-2 text-sm leading-6 text-secondary-text">{event.summary}</p> : null}
                  </div>
                  {event.url ? (
                    <a
                      href={event.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex shrink-0 items-center gap-1 rounded-xl border border-border/60 bg-card/75 px-3 py-2 text-xs text-secondary-text transition hover:border-cyan/20 hover:text-foreground"
                    >
                      原文
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : null}
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">新鲜度</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{event.freshnessScore.toFixed(0)}</p>
                    <p className="mt-1 text-xs text-secondary-text">{formatDateTime(event.publishedAt)}</p>
                  </div>
                  <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">可信度</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{event.credibilityScore.toFixed(0)}</p>
                    <p className="mt-1 text-xs text-secondary-text">{String(event.metadata.discoveryProfileName ?? '开放模板')}</p>
                  </div>
                  <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">信号强度</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{event.signalStrength.toFixed(0)}</p>
                    <p className="mt-1 text-xs text-secondary-text">{String(event.metadata.queryGroup ?? 'event_news')}</p>
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {event.themes.map((theme) => (
                    <Badge key={`${event.eventId}-${theme}`} variant="info" className="border-0 px-3 py-1">
                      {theme}
                    </Badge>
                  ))}
                  {event.chainTags.map((tag) => (
                    <Badge key={`${event.eventId}-${tag}`} variant="default" className="border-border/60 px-3 py-1">
                      {tag}
                    </Badge>
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <Button
                    variant={event.watchItemId ? 'secondary' : 'primary'}
                    size="sm"
                    onClick={() => void handlePromoteDiscoveryEvent(event)}
                    isLoading={promotingEventId === event.eventId}
                    loadingText={event.watchItemId ? '定位中...' : '加入中...'}
                  >
                    {event.watchItemId ? '编辑观察项' : '加入观察池'}
                  </Button>
                  <p className="text-xs leading-6 text-secondary-text">
                    {event.watchItemId ? '这条发现事件已经沉淀为观察项，可直接在右侧继续调整检索词。' : '把这条开放发现事件转成长期观察主题，后续由观察池持续跟踪。'}
                  </p>
                </div>
              </div>
            ))}
          </div>
          </Card>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.18fr_0.82fr]">
        <Card variant="bordered" padding="lg" className="rounded-[28px]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="label-uppercase">Recent Events</span>
              <h3 className="mt-1 text-2xl font-semibold text-foreground">最近信息事件</h3>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-[220px]">
                <Select
                  label=""
                  value={eventStatusFilter}
                  onChange={(value) => setEventStatusFilter(value as (typeof EVENT_STATUS_OPTIONS)[number]['value'])}
                  options={EVENT_STATUS_OPTIONS.map((option) => ({ value: option.value, label: option.label }))}
                />
              </div>
              <Badge variant="default" className="border-border/60 px-3 py-1">{events.length} 条</Badge>
            </div>
          </div>

          <div className="mt-5 space-y-3">
            {!loading && events.length === 0 ? (
              <EmptyState
                title="暂时还没有信息事件"
                description="先跑一轮扫描，观察池会把高价值产业信息沉淀成结构化事件。"
                icon={<Newspaper className="h-6 w-6" />}
                action={<Button onClick={() => void handleRunOnce()}>开始第一次扫描</Button>}
              />
            ) : null}

            {events.map((event) => (
              <div key={event.eventId} className="rounded-[24px] border border-border/60 bg-background/72 px-5 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={event.sourceMode === 'discovery' ? 'info' : 'default'} className="border-0 px-3 py-1">
                    {event.sourceMode === 'discovery' ? 'discovery' : 'watch'}
                  </Badge>
                  <Badge variant={statusVariant(event.status)} className="border-0 px-3 py-1">{event.status}</Badge>
                  <Badge variant={tierVariant(event.sourceTier)} className="border-0 px-3 py-1">{event.sourceTier}</Badge>
                  <Badge variant="default" className="border-border/60 px-3 py-1">{eventTypeLabel(event.eventType)}</Badge>
                  {event.provider ? (
                    <Badge variant="default" className="border-border/60 px-3 py-1">{event.provider}</Badge>
                  ) : null}
                  {event.sourceHost ? (
                    <Badge variant="default" className="border-border/60 px-3 py-1">{event.sourceHost}</Badge>
                  ) : null}
                  {event.clusterLabel ? (
                    <Badge variant="default" className="border-border/60 px-3 py-1">{event.clusterLabel}</Badge>
                  ) : null}
                  {event.watchItemName ? (
                    <Badge variant="success" className="border-0 px-3 py-1">观察项：{event.watchItemName}</Badge>
                  ) : null}
                </div>

                <div className="mt-3 flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <h4 className="text-lg font-semibold text-foreground">{event.title}</h4>
                    {event.summary ? <p className="mt-2 text-sm leading-6 text-secondary-text">{event.summary}</p> : null}
                  </div>
                  {event.url ? (
                    <a
                      href={event.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex shrink-0 items-center gap-1 rounded-xl border border-border/60 bg-card/75 px-3 py-2 text-xs text-secondary-text transition hover:border-cyan/20 hover:text-foreground"
                    >
                      原文
                      <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                  ) : null}
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">新鲜度</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{event.freshnessScore.toFixed(0)}</p>
                    <p className="mt-1 text-xs text-secondary-text">{formatDateTime(event.publishedAt)}</p>
                  </div>
                  <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">可信度</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{event.credibilityScore.toFixed(0)}</p>
                    <p className="mt-1 text-xs text-secondary-text">来源层级 {event.sourceTier} · {sourceTierHint(event.sourceTier)}</p>
                  </div>
                  <div className="rounded-[18px] border border-border/60 bg-card/70 px-4 py-3">
                    <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">信号强度</p>
                    <p className="mt-2 text-lg font-semibold text-foreground">{event.signalStrength.toFixed(0)}</p>
                    <p className="mt-1 text-xs text-secondary-text">
                      {String(event.metadata.queryGroup ?? 'event_news')}
                    </p>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-2">
                  {event.themes.map((theme) => (
                    <Badge key={`${event.eventId}-${theme}`} variant="info" className="border-0 px-3 py-1">
                      {theme}
                    </Badge>
                  ))}
                  {event.chainTags.map((tag) => (
                    <Badge key={`${event.eventId}-${tag}`} variant="default" className="border-border/60 px-3 py-1">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-5">
          <div ref={formAnchorRef} />
          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald/10 text-emerald">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Custom Watch Item</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">{editingItemId ? '编辑观察主题' : '自定义观察主题'}</h3>
              </div>
            </div>
            <div className="mt-5 grid gap-3">
              <label className="grid gap-2">
                <span className="text-sm font-medium text-foreground">观察主题名</span>
                <input
                  value={draft.name}
                  onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                  placeholder="例如：HBM 扩产、液冷订单、先进封装验证"
                  className="h-11 rounded-2xl border border-border/60 bg-background/72 px-4 text-sm text-foreground outline-none transition focus:border-cyan/30"
                />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-foreground">事件类型</span>
                <select
                  value={draft.eventType}
                  onChange={(event) => setDraft((current) => ({ ...current, eventType: event.target.value }))}
                  className="h-11 rounded-2xl border border-border/60 bg-background/72 px-4 text-sm text-foreground outline-none transition focus:border-cyan/30"
                >
                  {EVENT_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-foreground">主检索词</span>
                <textarea
                  value={draft.seedTermsText}
                  onChange={(event) => setDraft((current) => ({ ...current, seedTermsText: event.target.value }))}
                  placeholder="逗号分隔，例如：HBM，扩产，产能，封装"
                  rows={3}
                  className="rounded-2xl border border-border/60 bg-background/72 px-4 py-3 text-sm text-foreground outline-none transition focus:border-cyan/30"
                />
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-foreground">别名 / 主题 / 产业链标签</span>
                <div className="grid gap-3 md:grid-cols-3">
                  <input
                    value={draft.aliasesText}
                    onChange={(event) => setDraft((current) => ({ ...current, aliasesText: event.target.value }))}
                    placeholder="别名，如 CXMT"
                    className="h-11 rounded-2xl border border-border/60 bg-background/72 px-4 text-sm text-foreground outline-none transition focus:border-cyan/30"
                  />
                  <input
                    value={draft.themesText}
                    onChange={(event) => setDraft((current) => ({ ...current, themesText: event.target.value }))}
                    placeholder="主题，如 存储,芯片"
                    className="h-11 rounded-2xl border border-border/60 bg-background/72 px-4 text-sm text-foreground outline-none transition focus:border-cyan/30"
                  />
                  <input
                    value={draft.chainTagsText}
                    onChange={(event) => setDraft((current) => ({ ...current, chainTagsText: event.target.value }))}
                    placeholder="产业链标签，如 材料,设备"
                    className="h-11 rounded-2xl border border-border/60 bg-background/72 px-4 text-sm text-foreground outline-none transition focus:border-cyan/30"
                  />
                </div>
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-foreground">时间窗口与来源层级</span>
                <div className="grid gap-3 md:grid-cols-[120px_1fr]">
                  <input
                    value={draft.freshnessDays}
                    onChange={(event) => setDraft((current) => ({ ...current, freshnessDays: event.target.value }))}
                    placeholder="3"
                    className="h-11 rounded-2xl border border-border/60 bg-background/72 px-4 text-sm text-foreground outline-none transition focus:border-cyan/30"
                  />
                  <div className="flex flex-wrap gap-3 rounded-2xl border border-border/60 bg-background/72 px-4 py-3 text-sm text-secondary-text">
                    <label className="inline-flex items-center gap-2">
                      <input type="checkbox" checked={draft.allowL1} onChange={(event) => setDraft((current) => ({ ...current, allowL1: event.target.checked }))} />
                      L1 公告/监管
                    </label>
                    <label className="inline-flex items-center gap-2">
                      <input type="checkbox" checked={draft.allowL2} onChange={(event) => setDraft((current) => ({ ...current, allowL2: event.target.checked }))} />
                      L2 主流媒体
                    </label>
                    <label className="inline-flex items-center gap-2">
                      <input type="checkbox" checked={draft.allowL3} onChange={(event) => setDraft((current) => ({ ...current, allowL3: event.target.checked }))} />
                      L3 解读/弱源
                    </label>
                  </div>
                </div>
              </label>
              <label className="grid gap-2">
                <span className="text-sm font-medium text-foreground">备注</span>
                <textarea
                  value={draft.notes}
                  onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
                  placeholder="说明这条观察项为什么值得长期跟踪"
                  rows={2}
                  className="rounded-2xl border border-border/60 bg-background/72 px-4 py-3 text-sm text-foreground outline-none transition focus:border-cyan/30"
                />
              </label>
              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={() => void handleCreateItem()}
                  isLoading={savingItem}
                  loadingText={editingItemId ? '更新中...' : '保存中...'}
                  disabled={!draft.name.trim() || splitTokens(draft.seedTermsText).length === 0}
                >
                  {editingItemId ? '更新观察项' : '保存观察项'}
                </Button>
                {editingItemId ? (
                  <Button variant="secondary" onClick={handleCancelEdit}>
                    取消编辑
                  </Button>
                ) : null}
                <p className="text-sm leading-7 text-secondary-text">右侧主题现在不再是只读展示，可以直接在这里补你自己的事件型主题。</p>
              </div>
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Watch Items</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">当前观察主题</h3>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {items.map((item) => (
                <div key={item.itemId} className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                  <div>
                      <h4 className="text-base font-semibold text-foreground">{item.name}</h4>
                      <p className="mt-1 text-sm text-secondary-text">{eventTypeLabel(item.eventType)}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={item.isSystem ? 'info' : 'default'} className="border-0 px-3 py-1">
                        {item.isSystem ? '系统内置' : '自定义'}
                      </Badge>
                      <Badge variant={item.enabled ? 'success' : 'default'} className="border-0 px-3 py-1">
                        {item.enabled ? '启用' : '停用'}
                      </Badge>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => handleEditItem(item)}
                      >
                        编辑
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void handleDeleteItem(item)}
                        disabled={item.isSystem}
                        isLoading={deletingItemId === item.itemId}
                        loadingText="删除中..."
                      >
                        {item.isSystem ? '内置保护' : '删除'}
                      </Button>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.seedTerms.slice(0, 4).map((term) => (
                      <Badge key={`${item.itemId}-${term}`} variant="default" className="border-border/60 px-3 py-1">
                        {term}
                      </Badge>
                    ))}
                  </div>
                  <p className="mt-3 text-xs leading-6 text-secondary-text">
                    主题：{item.themes.join(' / ') || '未设置'} · 产业链标签：{item.chainTags.join(' / ') || '未设置'}
                  </p>
                </div>
              ))}
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-purple/10 text-purple">
                <Activity className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">How It Drives Search</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">检索驱动规则</h3>
              </div>
            </div>
            <div className="mt-5 space-y-3 text-sm leading-7 text-secondary-text">
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                观察项不是直接搜大主题，而是按“事件新闻 / 市场反应 / 风险排查”三种意图拆开检索。
              </div>
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                结果会优先保留与 seed terms、主题、产业链标签同时相关的内容，减少社媒和泛搜索噪音。
              </div>
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                只有新鲜度与可信度都过线的事件，才会继续喂给“主题因子扫描”。
              </div>
              <div className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">
                `L1` 是公告/监管/官方口径，`L2` 是主流媒体或快讯确认，`L3` 是市场反应、研报解读或弱源；现在不再单靠查询组硬分。
              </div>
            </div>
          </Card>
        </div>
      </section>
    </AppPage>
  );
};

export default InformationWatchPage;
