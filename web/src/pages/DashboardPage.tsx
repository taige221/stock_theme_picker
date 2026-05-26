import type React from 'react';
import { useEffect } from 'react';
import { ArrowUpRight, ChevronRight, Minus, TrendingDown } from 'lucide-react';
import { Link } from 'react-router-dom';
import { AppPage, Badge, Button, Card } from '../components/common';

/* ------------------------------------------------------------------ */
/*  Static data (will be replaced with API data later)                 */
/* ------------------------------------------------------------------ */

const summaryCards = [
  { label: '主题任务', value: '12', detail: '+3 新增' },
  { label: '候选股票', value: '28', detail: '+5 净新增' },
  { label: '触发提醒', value: '4', detail: '2 高优先级' },
  { label: '观察池盈亏', value: '+4.82%', detail: '本周累计', color: 'text-red-600' },
] as const;

const themeStates = [
  {
    tone: 'TRIGGERED',
    index: '1/4',
    subtitle: '14:02 重新触发 · 第 3 次',
    title: 'DeepSeek 关联',
    note: '公告披露后板块在 13:25 出现合力拉升，量能 2.1×，候选池新增 2 只标的。',
    candidates: '4',
    avgChange: '+5.7%',
    volumeRatio: '2.1×',
    variant: 'danger' as const,
  },
  {
    tone: 'STRONG',
    index: '2/4',
    subtitle: '排名上升 #2',
    title: 'AI 算力 / 光模块',
    note: '中际旭创、寒武纪连续放量突破，板块相对强度 +5.4%。',
    candidates: '6',
    avgChange: '+4.8%',
    volumeRatio: '2.4×',
    variant: 'success' as const,
  },
  {
    tone: 'WATCH',
    index: '3/4',
    subtitle: '回踩第 3 次 · 量能未配合',
    title: '机器人 · 减速器',
    note: '华丰科技触及支撑位 131.7。绿的谐波、中大力德量价配合较好。',
    candidates: '5',
    avgChange: '+0.9%',
    volumeRatio: '1.4×',
    variant: 'warning' as const,
  },
  {
    tone: 'COOLING',
    index: '4/4',
    subtitle: '尾盘剔除 1 只',
    title: '低空经济',
    note: '万丰奥威量价背离，莱斯信息在尾盘自动剔除。主题进入冷却期。',
    candidates: '1',
    avgChange: '-3.2%',
    volumeRatio: '0.7×',
    variant: 'default' as const,
  },
] as const;

const candidatePool = [
  { name: '中际旭创', code: '300308', theme: 'AI 算力 / 光模块', signal: '突破 + 放量', change: '+6.42%', ratio: '2.8×', hot: true },
  { name: '拓维信息', code: '002261', theme: 'DeepSeek 关联', signal: '涨停', change: '+9.98%', ratio: '3.4×', hot: true },
  { name: '海光信息', code: '688041', theme: 'DeepSeek 关联', signal: '放量启动', change: '+4.81%', ratio: '2.1×', hot: true },
  { name: '寒武纪', code: '688256', theme: 'AI 算力', signal: '加速突破', change: '+5.24%', ratio: '2.4×', hot: true },
  { name: '工业富联', code: '601138', theme: 'AI 算力', signal: '突破前高', change: '+3.78%', ratio: '1.9×', hot: true },
  { name: '中大力德', code: '002896', theme: '机器人 · 减速器', signal: '回踩支撑', change: '+2.31%', ratio: '1.6×', hot: false },
  { name: '华丰科技', code: '300290', theme: '机器人 · 减速器', signal: '等待信号', change: '-0.81%', ratio: '1.2×', hot: false },
  { name: '万丰奥威', code: '002085', theme: '低空经济', signal: '量价背离', change: '-3.18%', ratio: '0.7×', hot: false },
] as const;

const sectorStrength = [
  { name: 'AI 算力', value: 92, change: '+5.4%' },
  { name: 'DeepSeek', value: 85, change: '+4.1%' },
  { name: '机器人', value: 78, change: '+3.8%' },
  { name: '固态电池', value: 65, change: '+1.6%' },
  { name: '创新药', value: 52, change: '+0.4%' },
  { name: '半导体设备', value: 45, change: '-0.8%' },
  { name: '高股息', value: 38, change: '-1.1%' },
  { name: '低空经济', value: 30, change: '-2.4%' },
] as const;

const nextSteps = [
  '跟进 DeepSeek 主题新增的 2 只标的',
  '复核华丰科技 131.7 支撑位承接力度',
  '考虑万丰奥威止损或观察',
] as const;

const todayAlerts = [
  { time: '14:02', icon: 'up' as const, title: 'DeepSeek', desc: '主题重新触发，候选池新增', highlight: '2 只', right: '4 候选股' },
  { time: '13:31', icon: 'neutral' as const, title: '华丰科技', desc: '触及支撑位 131.7，第 3 次回踩', highlight: null, right: '¥132.16' },
  { time: '10:42', icon: 'up' as const, title: '中际旭创', desc: '突破 172.0 阻力位，量比 2.8×', highlight: null, right: '+6.42%' },
  { time: '09:47', icon: 'down' as const, title: '万丰奥威', desc: '跌破 5 日均线，量价背离', highlight: null, right: '-3.18%' },
  { time: '09:31', icon: 'neutral' as const, title: '开盘扫描完成', desc: '12 主题进入候选池', highlight: null, right: '28 标的' },
] as const;

/* ------------------------------------------------------------------ */
/*  Sub-components                                                     */
/* ------------------------------------------------------------------ */

function StatCell({ label, value, detail, color }: { label: string; value: string; detail: string; color?: string }) {
  return (
    <div className="rounded-xl border border-border/40 px-4 py-4">
      <p className="text-xs uppercase tracking-wider text-secondary-text">{label}</p>
      <p className={`mt-2 text-2xl font-semibold ${color ?? 'text-foreground'}`}>{value}</p>
      <p className={`mt-1 text-xs ${color ?? 'text-secondary-text'}`}>{detail}</p>
    </div>
  );
}

function AlertIcon({ type }: { type: 'up' | 'down' | 'neutral' }) {
  if (type === 'up') return (
    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-red-600/10">
      <ArrowUpRight className="h-3.5 w-3.5 text-red-600" />
    </span>
  );
  if (type === 'down') return (
    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-green-600/10">
      <TrendingDown className="h-3.5 w-3.5 text-green-600" />
    </span>
  );
  return (
    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-muted/60">
      <Minus className="h-3.5 w-3.5 text-secondary-text" />
    </span>
  );
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

const DashboardPage: React.FC = () => {
  useEffect(() => { document.title = '工作台 - DSA'; }, []);

  return (
    <AppPage className="!max-w-none px-4 md:px-8 lg:px-12 xl:px-16">
      {/* ===== Hero: Today's Brief + Sentiment ===== */}
      <Card variant="bordered" padding="lg" className="rounded-2xl">
        <div className="grid gap-8 lg:grid-cols-[1fr_360px]">
          {/* Left: Brief */}
          <div>
            <p className="text-xs uppercase tracking-wider text-secondary-text">TODAY&apos;S BRIEF · 今日要看</p>
            <h1 className="mt-3 text-3xl font-bold leading-tight tracking-tight text-foreground md:text-4xl">
              <span className="rounded bg-foreground/[0.08] px-1">12 个主题</span>今天有催化，其中{' '}
              <span className="rounded bg-foreground/[0.08] px-1">3 个</span>值得现在跟进。
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-secondary-text">
              DeepSeek 关联主题在午盘后重新触发并伴随放量；AI 算力与机器人板块延续强势；低空经济进入冷却期，已自动剔除 1 只候选股。
            </p>
            <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
              {summaryCards.map((item) => (
                <StatCell key={item.label} label={item.label} value={item.value} detail={item.detail} color={'color' in item ? item.color : undefined} />
              ))}
            </div>
          </div>

          {/* Right: Theme Sentiment */}
          <div className="flex flex-col rounded-xl border border-border/40 px-6 py-6">
            <div className="flex items-start justify-between">
              <p className="text-xs text-secondary-text">主题情绪指数 · Theme Sentiment</p>
              <span className="text-sm font-semibold text-red-600">+12.4</span>
            </div>
            <div className="mt-4 flex items-baseline gap-2">
              <span className="text-5xl font-bold text-foreground">68</span>
              <span className="text-sm text-secondary-text">/ 100</span>
            </div>
            <p className="mt-1 text-xs text-secondary-text">偏多 · 高于 5 日均值</p>
            {/* Mini chart placeholder */}
            <div className="mt-auto flex-1 pt-4">
              <div className="relative h-20 w-full overflow-hidden rounded-lg bg-muted/20">
                <svg className="h-full w-full" viewBox="0 0 200 60" preserveAspectRatio="none">
                  <polyline
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    className="text-red-500/60"
                    points="0,45 20,42 40,48 60,40 80,38 100,35 120,32 140,28 160,22 180,18 200,12"
                  />
                </svg>
              </div>
              <div className="mt-2 flex justify-between text-[10px] text-secondary-text">
                <span>5/06</span>
                <span>5/12</span>
                <span>5/19</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* ===== Active Themes ===== */}
      <div className="mt-8">
        <div className="flex flex-wrap items-center justify-between gap-4 pb-5">
          <div>
            <p className="text-xs uppercase tracking-wider text-secondary-text">ACTIVE THEMES</p>
            <h2 className="mt-1 text-2xl font-bold text-foreground">主题状态</h2>
          </div>
          <div className="flex gap-2">
            <Link to="/theme-picker">
              <Button variant="outline" size="sm" className="rounded-xl">全部主题</Button>
            </Link>
            <Link to="/theme-picker">
              <Button size="sm" className="rounded-xl">+ 新建扫描</Button>
            </Link>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {themeStates.map((theme) => (
            <Card key={theme.title} variant="bordered" padding="lg" className="rounded-2xl">
              <div className="flex items-center justify-between">
                <Badge variant={theme.variant} className="border-0 px-3 py-1 text-xs font-semibold uppercase tracking-wider">
                  {theme.tone}
                </Badge>
                <span className="text-xs text-secondary-text">{theme.index}</span>
              </div>
              <p className="mt-2 text-xs text-secondary-text">{theme.subtitle}</p>
              <h3 className="mt-2 text-xl font-bold text-foreground">{theme.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-secondary-text">{theme.note}</p>
              <div className="mt-4 flex gap-6">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-secondary-text">候选股票</p>
                  <p className="mt-1 text-lg font-semibold text-foreground">{theme.candidates}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-secondary-text">平均涨幅</p>
                  <p className={`mt-1 text-lg font-semibold ${theme.avgChange.startsWith('-') ? 'text-green-600' : 'text-red-600'}`}>
                    {theme.avgChange}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-secondary-text">量比</p>
                  <p className="mt-1 text-lg font-semibold text-foreground">{theme.volumeRatio}</p>
                </div>
              </div>
              {/* Mini sparkline placeholder */}
              <div className="mt-4 flex items-end justify-between">
                <div className="h-10 w-32 overflow-hidden rounded bg-muted/20">
                  <svg className="h-full w-full" viewBox="0 0 120 30" preserveAspectRatio="none">
                    <polyline
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className={theme.avgChange.startsWith('-') ? 'text-secondary-text' : 'text-red-500/50'}
                      points={theme.tone === 'TRIGGERED' ? '0,25 20,22 40,20 60,18 80,12 100,8 120,4'
                        : theme.tone === 'STRONG' ? '0,28 20,25 40,22 60,18 80,14 100,10 120,6'
                        : theme.tone === 'WATCH' ? '0,15 20,18 40,14 60,20 80,16 100,22 120,18'
                        : '0,8 20,10 40,14 60,18 80,22 100,24 120,26'}
                    />
                  </svg>
                </div>
                <span className="text-[10px] text-secondary-text">近 12 日</span>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* ===== Candidate Pool + Sector Strength ===== */}
      <div className="mt-8 grid gap-6 xl:grid-cols-[1fr_440px]">
        {/* Left: Candidate Pool table */}
        <Card variant="bordered" padding="lg" className="rounded-2xl">
          <div className="flex items-center justify-between pb-4">
            <h2 className="text-lg font-semibold text-foreground">候选股票 · Candidate Pool</h2>
            <span className="text-xs text-secondary-text">8 / 28 · 按 RS 排序</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border/60 text-left text-xs uppercase tracking-wider text-secondary-text">
                  <th className="pb-3 pr-4">名称</th>
                  <th className="pb-3 pr-4">信号</th>
                  <th className="pb-3 pr-4 text-right">涨幅</th>
                  <th className="pb-3 text-right">量比</th>
                </tr>
              </thead>
              <tbody>
                {candidatePool.map((stock) => (
                  <tr key={`${stock.name}-${stock.code}`} className="border-b border-border/20">
                    <td className="py-3.5 pr-4">
                      <div className="flex items-center gap-2">
                        <span className={`h-2 w-2 shrink-0 rounded-full ${stock.hot ? 'bg-red-500' : 'bg-secondary-text/40'}`} />
                        <div>
                          <span className="font-semibold text-foreground">{stock.name}</span>
                          <span className="ml-1.5 text-xs text-secondary-text">{stock.code}</span>
                          <p className="mt-0.5 text-[10px] text-secondary-text">{stock.theme}</p>
                        </div>
                      </div>
                    </td>
                    <td className="py-3.5 pr-4 text-sm text-foreground">{stock.signal}</td>
                    <td className={`py-3.5 pr-4 text-right font-mono text-sm font-medium ${
                      stock.change.startsWith('-') ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {stock.change}
                    </td>
                    <td className="py-3.5 text-right font-mono text-sm text-foreground">{stock.ratio}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Right: Sector Strength + Next steps */}
        <div className="min-w-0 space-y-4">
          <Card variant="bordered" padding="lg" className="rounded-2xl">
            <div className="flex items-center justify-between pb-3">
              <h3 className="text-sm font-semibold text-foreground">板块强度</h3>
              <span className="text-[10px] text-secondary-text">相对 5 日均值</span>
            </div>
            <div className="space-y-3">
              {sectorStrength.map((sector) => (
                <div key={sector.name} className="flex items-center gap-3">
                  <span className="w-16 shrink-0 text-xs text-foreground">{sector.name}</span>
                  <div className="relative h-5 flex-1 overflow-hidden rounded bg-muted/30">
                    <div
                      className={`absolute inset-y-0 left-0 rounded ${
                        sector.change.startsWith('-') ? 'bg-green-600/60' : 'bg-red-600/60'
                      }`}
                      style={{ width: `${sector.value}%` }}
                    />
                  </div>
                  <span className={`w-12 text-right text-xs font-medium ${
                    sector.change.startsWith('-') ? 'text-green-600' : 'text-red-600'
                  }`}>
                    {sector.change}
                  </span>
                </div>
              ))}
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-2xl">
            <h3 className="text-sm font-semibold text-secondary-text">下一步建议</h3>
            <div className="mt-3 space-y-3">
              {nextSteps.map((step, index) => (
                <div key={step} className="flex items-start gap-3 text-sm text-foreground">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted/40 text-[10px] font-semibold text-secondary-text">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span>{step}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* ===== Today's Alerts ===== */}
      <Card variant="bordered" padding="lg" className="mt-8 rounded-2xl">
        <div className="flex items-center justify-between pb-4">
          <h2 className="text-lg font-semibold text-foreground">今日提醒 · Today&apos;s Alerts</h2>
          <span className="text-xs text-secondary-text">4 提醒 · 2 高优先级</span>
        </div>
        <div className="space-y-1">
          {todayAlerts.map((alert) => (
            <div key={`${alert.time}-${alert.title}`} className="flex items-center gap-4 rounded-xl px-3 py-3 transition-colors hover:bg-hover/20">
              <span className="w-12 shrink-0 text-xs text-secondary-text">{alert.time}</span>
              <AlertIcon type={alert.icon} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground">{alert.title}</span>
                  <span className="text-sm text-secondary-text">{alert.desc}</span>
                  {alert.highlight ? (
                    <span className="text-sm font-semibold text-foreground">{alert.highlight}</span>
                  ) : null}
                </div>
              </div>
              <span className={`shrink-0 text-sm font-medium ${
                alert.right.startsWith('+') ? 'text-red-600'
                  : alert.right.startsWith('-') ? 'text-green-600'
                  : alert.right.includes('候选') ? 'text-red-600'
                  : 'text-foreground'
              }`}>
                {alert.right}
              </span>
            </div>
          ))}
        </div>
      </Card>

      {/* Quick access links */}
      <div className="mt-8 grid gap-3 md:grid-cols-3 lg:grid-cols-6">
        {[
          { title: '主题因子', desc: '先看主题为什么重新触发。', to: '/theme-factor-scans' },
          { title: '主题选股', desc: '从任务历史里看新增变化。', to: '/theme-picker' },
          { title: '单股查询', desc: '反向验证龙头和跟风。', to: '/stock-query' },
          { title: '单 ETF', desc: '用 ETF 做主线确认。', to: '/etf-query' },
          { title: '观察池', desc: '等位置和提醒。', to: '/watchlist' },
          { title: '信息观察', desc: '先看今天发生了什么。', to: '/information-watch' },
        ].map((link) => (
          <Link key={link.title} to={link.to}>
            <div className="group flex items-center justify-between rounded-xl border border-border/40 px-4 py-3.5 transition-colors hover:bg-hover/20">
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">{link.title}</p>
                <p className="mt-0.5 text-[10px] text-secondary-text">{link.desc}</p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-secondary-text transition-transform group-hover:translate-x-0.5" />
            </div>
          </Link>
        ))}
      </div>
    </AppPage>
  );
};

export default DashboardPage;
