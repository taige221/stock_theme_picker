import type React from 'react';
import { ArrowRight, Bell, Layers3, Radar, Sparkles, Star, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { AppPage, Badge, Button, Card } from '../components/common';

const recentTasks = [
  { theme: 'DeepSeek', status: 'triggered', delta: '+2 新增股票', cta: '查看结果' },
  { theme: '机器人', status: 'cooling', delta: '-1 移除股票', cta: '查看对比' },
  { theme: 'AI Infra', status: 'heating', delta: '+4 新闻催化', cta: '继续跟踪' },
];

const watchlistHighlights = [
  { stock: '华丰科技', signal: '持有候选', theme: 'DeepSeek', risk: 'MA20 回踩观察' },
  { stock: '优博讯', signal: '短线异动', theme: 'AI 应用', risk: '前高抛压接近' },
  { stock: '景旺电子', signal: '低吸观察', theme: '算力链', risk: '量能仍需确认' },
];

const recentAlerts = [
  'DeepSeek 主题重新触发，候选池新增 2 只股票',
  '华丰科技接近支撑位 131.7，可关注承接',
  '机器人主题热度下降，候选排名出现明显回撤',
];

const actionCards = [
  {
    title: '主题选股',
    description: '从题材、板块和催化出发，快速收敛一批值得继续看的股票。',
    to: '/theme-picker',
    icon: Sparkles,
  },
  {
    title: '单股查询',
    description: '从单只股票反查关联主题、信号状态和未入选原因。',
    to: '/stock-query',
    icon: Radar,
  },
  {
    title: '观察池',
    description: '把高价值股票和主题沉淀下来，做长期跟踪和提醒。',
    to: '/watchlist',
    icon: Star,
  },
];

const DashboardPage: React.FC = () => {
  return (
    <AppPage className="space-y-6 !max-w-[1680px] px-3 md:px-5 lg:px-6">
      <section className="overflow-hidden rounded-[32px] border border-border/60 bg-[radial-gradient(circle_at_top_left,_rgba(6,182,212,0.18),_transparent_32%),radial-gradient(circle_at_bottom_right,_rgba(129,140,248,0.16),_transparent_28%),linear-gradient(180deg,rgba(255,255,255,0.98),rgba(246,249,252,0.96))] shadow-soft-card dark:bg-[radial-gradient(circle_at_top_left,_rgba(34,211,238,0.2),_transparent_30%),radial-gradient(circle_at_bottom_right,_rgba(129,140,248,0.14),_transparent_30%),linear-gradient(180deg,rgba(10,15,26,0.98),rgba(14,20,32,0.96))]">
        <div className="grid gap-6 px-5 py-6 lg:grid-cols-[1.15fr_0.85fr] lg:px-7 lg:py-7">
          <div className="space-y-5">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan/10 text-cyan shadow-soft-card">
                <TrendingUp className="h-7 w-7" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Daily Research Hub</p>
                <h2 className="mt-1 text-3xl font-semibold tracking-tight text-foreground">今天先看哪些变化最值得跟进</h2>
                <p className="mt-2 max-w-3xl text-sm leading-7 text-secondary-text">
                  这版工作台把主题扫描、单股反查、观察池和提醒入口都摆在一层，优先回答“今天发生了什么”和“我下一步该点哪里”。
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">观察主题</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">12</p>
                <p className="mt-2 text-sm text-secondary-text">其中 3 个主题今天出现新增催化</p>
              </Card>
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">观察股票</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">28</p>
                <p className="mt-2 text-sm text-secondary-text">4 只股票接近自定义观察区间</p>
              </Card>
              <Card variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-card/85">
                <p className="text-xs uppercase tracking-[0.16em] text-secondary-text">今日提醒</p>
                <p className="mt-3 text-3xl font-semibold text-foreground">4</p>
                <p className="mt-2 text-sm text-secondary-text">2 条主题变化，2 条单股位置提醒</p>
              </Card>
            </div>
          </div>

          <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/90">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Quick Start</p>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">直接进入今天的工作流</h3>
              </div>
              <Badge variant="info" className="border-0 px-3 py-1">First Stage UI</Badge>
            </div>
            <div className="mt-5 space-y-3">
              {actionCards.map((card) => {
                const Icon = card.icon;
                return (
                  <Link key={card.title} to={card.to} className="block">
                    <Card hoverable variant="bordered" padding="lg" className="rounded-[24px] border-border/60 bg-background/75">
                      <div className="flex items-start gap-4">
                        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">
                          <Icon className="h-5 w-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-3">
                            <h4 className="text-lg font-semibold text-foreground">{card.title}</h4>
                            <ArrowRight className="h-4 w-4 text-secondary-text" />
                          </div>
                          <p className="mt-2 text-sm leading-6 text-secondary-text">{card.description}</p>
                        </div>
                      </div>
                    </Card>
                  </Link>
                );
              })}
            </div>
          </Card>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-5">
          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <span className="label-uppercase">Recent Theme Tasks</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">最近主题任务</h3>
              </div>
              <Link to="/theme-picker">
                <Button variant="secondary" className="rounded-2xl">进入主题选股</Button>
              </Link>
            </div>
            <div className="mt-5 space-y-3">
              {recentTasks.map((task) => (
                <div key={task.theme} className="rounded-[24px] border border-border/60 bg-background/72 px-5 py-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <div className="flex items-center gap-3">
                        <h4 className="text-lg font-semibold text-foreground">{task.theme}</h4>
                        <Badge
                          variant={task.status === 'triggered' ? 'success' : task.status === 'cooling' ? 'warning' : 'info'}
                          className="border-0 px-3 py-1"
                        >
                          {task.status}
                        </Badge>
                      </div>
                      <p className="mt-2 text-sm text-secondary-text">{task.delta}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="secondary" className="rounded-2xl">{task.cta}</Button>
                      <Button variant="outline" className="rounded-2xl">加入观察池</Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center justify-between gap-3">
              <div>
                <span className="label-uppercase">Watchlist Highlights</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">观察池亮点</h3>
              </div>
              <Link to="/watchlist">
                <Button variant="secondary" className="rounded-2xl">查看全部</Button>
              </Link>
            </div>
            <div className="mt-5 grid gap-3">
              {watchlistHighlights.map((item) => (
                <div key={item.stock} className="grid gap-3 rounded-[24px] border border-border/60 bg-background/72 px-5 py-4 md:grid-cols-[1fr_160px_180px] md:items-center">
                  <div>
                    <h4 className="text-lg font-semibold text-foreground">{item.stock}</h4>
                    <p className="mt-1 text-sm text-secondary-text">{item.theme}</p>
                  </div>
                  <div>
                    <Badge variant={item.signal === '持有候选' ? 'warning' : item.signal === '短线异动' ? 'danger' : 'info'} className="border-0 px-3 py-1">
                      {item.signal}
                    </Badge>
                  </div>
                  <p className="text-sm text-secondary-text">{item.risk}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-5">
          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan/10 text-cyan">
                <Bell className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Recent Alerts</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">最近提醒</h3>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {recentAlerts.map((alert) => (
                <div key={alert} className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4 text-sm leading-6 text-foreground">
                  {alert}
                </div>
              ))}
            </div>
          </Card>

          <Card variant="bordered" padding="lg" className="rounded-[28px]">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-purple/10 text-purple">
                <Layers3 className="h-5 w-5" />
              </div>
              <div>
                <span className="label-uppercase">Next Workflow</span>
                <h3 className="mt-1 text-2xl font-semibold text-foreground">接下来建议补齐</h3>
              </div>
            </div>
            <ul className="mt-5 space-y-3 text-sm leading-7 text-secondary-text">
              <li className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">把单股查询和主题选股结果接到统一的“加入观察池”动作。</li>
              <li className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">补结果 diff 引擎，让每次扫描都能解释新增、移除和排序变化。</li>
              <li className="rounded-[22px] border border-border/60 bg-background/72 px-4 py-4">把提醒规则先做成 in-app 版本，验证真正有价值的触发条件。</li>
            </ul>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link to="/stock-query">
                <Button className="rounded-2xl">先看单股查询</Button>
              </Link>
              <Link to="/watchlist">
                <Button variant="secondary" className="rounded-2xl">查看观察池</Button>
              </Link>
            </div>
          </Card>
        </div>
      </section>
    </AppPage>
  );
};

export default DashboardPage;
