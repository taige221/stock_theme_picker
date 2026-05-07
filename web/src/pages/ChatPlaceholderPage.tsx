import type React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowLeft, BrainCircuit } from 'lucide-react';
import { AppPage, Button, Card } from '../components/common';

const ChatPlaceholderPage: React.FC = () => {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const stockCode = params.get('stock') ?? '--';
  const stockName = params.get('name') ?? '目标股票';

  return (
    <AppPage className="py-8">
      <div className="mx-auto max-w-4xl">
        <Card variant="bordered" padding="lg" className="rounded-[28px] border-border/60 bg-card/95">
          <div className="flex flex-col gap-6">
            <div className="flex items-center gap-4">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan/12 text-cyan">
                <BrainCircuit className="h-7 w-7" />
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-secondary-text">Deep Analysis Placeholder</p>
                <h1 className="mt-2 text-3xl font-semibold text-foreground">独立前端模式下的问股占位页</h1>
              </div>
            </div>

            <div className="rounded-2xl border border-border/60 bg-background/70 p-5">
              <p className="text-sm text-secondary-text">当前从主题选股页发起了深度分析请求。独立前端子仓库默认只包含主题选股页面，因此这里先保留一个占位入口。</p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl bg-card px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">股票代码</p>
                  <p className="mt-2 text-xl font-semibold text-foreground">{stockCode}</p>
                </div>
                <div className="rounded-2xl bg-card px-4 py-4">
                  <p className="text-xs uppercase tracking-[0.14em] text-secondary-text">股票名称</p>
                  <p className="mt-2 text-xl font-semibold text-foreground">{stockName}</p>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <Button className="rounded-2xl" onClick={() => window.history.back()}>
                <ArrowLeft className="h-4 w-4" />
                返回上一页
              </Button>
              <Link to="/theme-picker" className="inline-flex">
                <Button variant="secondary" className="rounded-2xl">
                  返回主题选股
                </Button>
              </Link>
            </div>
          </div>
        </Card>
      </div>
    </AppPage>
  );
};

export default ChatPlaceholderPage;
