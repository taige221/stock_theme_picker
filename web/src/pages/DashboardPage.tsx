import type React from 'react';
import { ArrowRight, Layers3, Newspaper, Orbit, Radar, Sparkles, Star } from 'lucide-react';
import { Link } from 'react-router-dom';
import { AppPage, Badge, Button, Card } from '../components/common';

const summaryCards = [
  { label: '主题任务', value: '12', detail: '+3 新增' },
  { label: '候选股票', value: '28', detail: '+5 净新增' },
  { label: '触发提醒', value: '4', detail: '2 高优先级' },
  { label: '观察池盈亏', value: '+4.82%', detail: '本周累计' },
] as const;

const themeStates = [
  {
    tone: 'TRIGGERED',
    index: '1 / 4',
    title: 'DeepSeek 关联',
    note: '公告披露后板块在 13:25 出现合力拉升，量能 2.1×，候选池新增 2 只标的。',
    metrics: ['候选股票 4', '平均涨幅 +5.7%', '量比 2.1×'],
    variant: 'danger' as const,
  },
  {
    tone: 'STRONG',
    index: '2 / 4',
    title: 'AI 算力 / 光模块',
    note: '中际旭创、寒武纪连续放量突破，板块相对强度继续提升。',
    metrics: ['候选股票 6', '平均涨幅 +4.8%', '量比 2.4×'],
    variant: 'success' as const,
  },
  {
    tone: 'WATCH',
    index: '3 / 4',
    title: '机器人 · 减速器',
    note: '华丰科技靠近支撑位，绿的谐波、中大力德量价配合相对更好。',
    metrics: ['候选股票 5', '平均涨幅 +0.9%', '量比 1.4×'],
    variant: 'warning' as const,
  },
  {
    tone: 'COOLING',
    index: '4 / 4',
    title: '低空经济',
    note: '万丰奥威量价背离，莱斯信息在尾盘自动剔除，主题进入冷却期。',
    metrics: ['候选股票 1', '平均涨幅 -3.2%', '量比 0.7×'],
    variant: 'default' as const,
  },
] as const;

const candidatePool = [
  ['中际旭创', '300308', 'AI 算力 / 光模块', '突破 + 放量', '+6.42%', '2.8×'],
  ['拓维信息', '002261', 'DeepSeek 关联', '涨停', '+9.98%', '3.4×'],
  ['海光信息', '688041', 'DeepSeek 关联', '放量启动', '+4.81%', '2.1×'],
  ['寒武纪', '688256', 'AI 算力', '加速突破', '+5.24%', '2.4×'],
  ['工业富联', '601138', 'AI 算力', '突破前高', '+3.78%', '1.9×'],
  ['中大力德', '002896', '机器人 · 减速器', '回踩支撑', '+2.31%', '1.5×'],
] as const;

const quickLinks = [
  {
    title: '主题因子',
    detail: '先看主题为什么重新触发，再决定是否继续下钻。',
    to: '/theme-factor-scans',
    icon: Orbit,
  },
  {
    title: '主题选股',
    detail: '从任务历史里看新增、移除和排序变化。',
    to: '/theme-picker',
    icon: Sparkles,
  },
  {
    title: '单股查询',
    detail: '反向验证龙头、跟风和未入选原因。',
    to: '/stock-query',
    icon: Radar,
  },
  {
    title: '单 ETF',
    detail: '用 ETF 做主线确认，不把个股热度误判成板块合力。',
    to: '/etf-query',
    icon: Layers3,
  },
  {
    title: '观察池',
    detail: '把值得继续看的票沉淀下来，等位置和提醒。',
    to: '/watchlist',
    icon: Star,
  },
  {
    title: '信息观察',
    detail: '回到最前链路，先看今天到底发生了什么。',
    to: '/information-watch',
    icon: Newspaper,
  },
] as const;

const DashboardPage: React.FC = () => {
  return (
    <AppPage className="space-y-6">
      <section className="grid gap-5 xl:grid-cols-[1.4fr_0.8fr]">
        <Card className="rounded-[2rem] p-0">
          <div className="grid gap-6 px-6 py-6 lg:grid-cols-[1.15fr_0.85fr] lg:px-7">
            <div className="space-y-5">
              <div className="space-y-2">
                <p className="label-uppercase">Theme Picker · 工作台</p>
                <h2 className="font-display text-4xl font-semibold tracking-tight text-foreground">
                  今天先看哪些主题变化
                </h2>
                <p className="max-w-3xl text-sm leading-7 text-secondary-text">
                  保持信息密度，但把第一屏只留给真正要用的信息: 今日简报、主题状态、候选池和下一步入口。
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {summaryCards.map((item) => (
                  <Card key={item.label} padding="md" className="rounded-[1.5rem] bg-card/88">
                    <p className="label-uppercase">{item.label}</p>
                    <p className="mt-3 text-3xl font-semibold text-foreground">{item.value}</p>
                    <p className="mt-2 text-sm text-secondary-text">{item.detail}</p>
                  </Card>
                ))}
              </div>
            </div>

            <Card padding="lg" className="rounded-[1.75rem] bg-[linear-gradient(180deg,hsl(var(--elevated)/0.96),hsl(var(--card)/0.92))]">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="label-uppercase">Today's Brief · 今日要看</p>
                  <h3 className="mt-2 font-display text-2xl font-semibold text-foreground">12 个主题里有 3 个值得现在跟进</h3>
                </div>
                <Badge variant="info" className="border-0 px-3 py-1">Tue · 5/19</Badge>
              </div>
              <p className="mt-4 text-sm leading-7 text-secondary-text">
                DeepSeek 关联主题在午盘后重新触发并伴随放量；AI 算力与机器人板块延续强势；低空经济进入冷却期，已自动剔除 1 只候选股。
              </p>
              <div className="mt-5 flex flex-wrap gap-3">
                <Link to="/theme-picker">
                  <Button>进入主题选股</Button>
                </Link>
                <Link to="/theme-factor-scans">
                  <Button variant="secondary">查看主题因子</Button>
                </Link>
              </div>
            </Card>
          </div>
        </Card>

        <Card className="rounded-[2rem]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="label-uppercase">Quick Access</p>
              <h3 className="mt-2 font-display text-2xl font-semibold text-foreground">直接进入今天的工作链路</h3>
            </div>
            <Badge variant="default" className="border-0 px-3 py-1">6 个入口</Badge>
          </div>
          <div className="mt-5 space-y-3">
            {quickLinks.map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.title} to={item.to} className="block">
                  <div className="rounded-[1.4rem] border border-border/70 bg-background/64 px-4 py-4 transition hover:bg-foreground/4">
                    <div className="flex items-start gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-foreground/8 bg-foreground/5 text-foreground">
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-3">
                          <h4 className="text-base font-semibold text-foreground">{item.title}</h4>
                          <ArrowRight className="h-4 w-4 text-secondary-text" />
                        </div>
                        <p className="mt-1 text-sm leading-6 text-secondary-text">{item.detail}</p>
                      </div>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </Card>
      </section>

      <section className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <Card className="rounded-[2rem]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="label-uppercase">Active Themes</p>
              <h3 className="mt-2 font-display text-2xl font-semibold text-foreground">主题状态</h3>
            </div>
            <Link to="/theme-picker">
              <Button variant="secondary">+ 新建扫描</Button>
            </Link>
          </div>

          <div className="mt-5 space-y-3">
            {themeStates.map((theme) => (
              <div key={theme.title} className="rounded-[1.5rem] border border-border/70 bg-background/66 px-5 py-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Badge variant={theme.variant} className="border-0 px-3 py-1">{theme.tone}</Badge>
                  <span className="text-xs tracking-[0.2em] text-secondary-text">{theme.index}</span>
                </div>
                <h4 className="mt-3 text-lg font-semibold text-foreground">{theme.title}</h4>
                <p className="mt-2 text-sm leading-6 text-secondary-text">{theme.note}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {theme.metrics.map((metric) => (
                    <span key={metric} className="rounded-full border border-border/70 bg-card/86 px-3 py-1.5 text-xs text-secondary-text">
                      {metric}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="rounded-[2rem]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="label-uppercase">Candidate Pool</p>
              <h3 className="mt-2 font-display text-2xl font-semibold text-foreground">候选股票</h3>
            </div>
            <Badge variant="default" className="border-0 px-3 py-1">8 / 28 · 按 RS 排序</Badge>
          </div>

          <div className="mt-5 overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-0 text-left">
              <thead>
                <tr className="text-xs uppercase tracking-[0.18em] text-secondary-text">
                  <th className="border-b border-border/70 px-3 py-3 font-medium">名称</th>
                  <th className="border-b border-border/70 px-3 py-3 font-medium">主题</th>
                  <th className="border-b border-border/70 px-3 py-3 font-medium">信号</th>
                  <th className="border-b border-border/70 px-3 py-3 font-medium">涨幅</th>
                  <th className="border-b border-border/70 px-3 py-3 font-medium">量比</th>
                </tr>
              </thead>
              <tbody>
                {candidatePool.map((row) => (
                  <tr key={`${row[0]}-${row[1]}`} className="align-top">
                    <td className="border-b border-border/50 px-3 py-4">
                      <div className="font-medium text-foreground">{row[0]}</div>
                      <div className="mt-1 text-xs tracking-[0.16em] text-secondary-text">{row[1]}</div>
                    </td>
                    <td className="border-b border-border/50 px-3 py-4 text-sm text-secondary-text">{row[2]}</td>
                    <td className="border-b border-border/50 px-3 py-4 text-sm text-foreground">{row[3]}</td>
                    <td className="border-b border-border/50 px-3 py-4 text-sm font-medium text-danger">{row[4]}</td>
                    <td className="border-b border-border/50 px-3 py-4 text-sm text-foreground">{row[5]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </section>
    </AppPage>
  );
};

export default DashboardPage;
