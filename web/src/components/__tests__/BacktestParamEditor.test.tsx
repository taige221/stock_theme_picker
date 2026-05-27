import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { BacktestPreset } from '../../api/backtests';
import { BacktestParamEditor } from '../BacktestParamEditor';

function renderEditor(preset: BacktestPreset) {
  return render(
    <BacktestParamEditor
      detail={null}
      preset={preset}
      values={{}}
      onChange={vi.fn()}
      onExecute={vi.fn()}
      onSave={vi.fn()}
      executing={false}
      saving={false}
    />,
  );
}

const stockPool = {
  name: '样例股票池',
  sourcePath: 'data/backtests/stock-codes-2.json',
  totalSymbols: 2,
  namedSymbols: 2,
  membersPreview: [
    { stockCode: '688629.SH', stockName: '华丰科技' },
    { stockCode: '300750.SZ', stockName: '宁德时代' },
  ],
};

describe('BacktestParamEditor', () => {
  it('hides box-only params for single-stock signal strategies and keeps stock-pool context visible', () => {
    renderEditor({
      presetId: 'stock_signal_holding',
      name: '单股趋势持有策略',
      strategy: 'stock_signal_holding',
      category: 'single_stock_signal',
      params: {
        box_lookback_days: 45,
        breakout_lookback_days: 20,
        stop_loss_pct: 0.04,
        take_profit_pct: 0.16,
        max_holding_days: 18,
        position_size_pct: 1,
      },
      defaultParams: {},
      stockPool,
      importedVersions: [
        {
          runId: 'run-1',
          startDate: '2024-01-01',
          endDate: '2024-01-31',
        },
      ],
    });

    expect(screen.getByText(/单股信号参数/)).toBeInTheDocument();
    expect(screen.queryByText('箱体观察周期')).not.toBeInTheDocument();
    expect(screen.getByText('突破观察周期')).toBeInTheDocument();
    expect(screen.getByText('时间长度')).toBeInTheDocument();
    expect(screen.getByText('31 自然日')).toBeInTheDocument();
    expect(screen.getAllByText('股票池文件').length).toBeGreaterThan(0);
    expect(screen.getByText('data/backtests/stock-codes-2.json')).toBeInTheDocument();
    expect(screen.getByText('688629.SH / 300750.SZ')).toBeInTheDocument();
    expect(screen.getByText('华丰科技 688629.SH / 宁德时代 300750.SZ')).toBeInTheDocument();
  });

  it('keeps box structure params for the box strategy', () => {
    renderEditor({
      presetId: 'a_share_box',
      name: 'A股箱体策略',
      strategy: 'a_share_box',
      category: 'box',
      params: {
        box_lookback_days: 45,
        min_box_touches: 3,
        breakout_lookback_days: 20,
      },
      defaultParams: {},
      stockPool,
    });

    expect(screen.getByText(/箱体突破\/回踩参数/)).toBeInTheDocument();
    expect(screen.getByText('箱体观察周期')).toBeInTheDocument();
    expect(screen.getByText('最低箱体触碰次数')).toBeInTheDocument();
  });
});
