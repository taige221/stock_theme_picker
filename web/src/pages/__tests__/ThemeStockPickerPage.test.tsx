import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ThemeStockPickerPage from '../ThemeStockPickerPage';

const navigateMock = vi.fn();

const { getThemes, scan, getScanStatus, getHistory, retry } = vi.hoisted(() => ({
  getThemes: vi.fn(),
  scan: vi.fn(),
  getScanStatus: vi.fn(),
  getHistory: vi.fn(),
  retry: vi.fn(),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock('../../api/themePicker', () => ({
  themePickerApi: {
    getThemes,
    scan,
    getScanStatus,
    getHistory,
    retry,
  },
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({
    resolvedTheme: 'dark',
    setTheme: vi.fn(),
  }),
}));

const MOCK_RESULT = {
  query: {
    themeId: 'deepseek',
    themeName: 'DeepSeek',
    boardCode: 'BK1188',
    boardName: 'DeepSeek概念',
    strategyMode: 'holding',
    maxCandidates: 8,
  },
  themeInsight: {
    themeName: 'DeepSeek',
    eventStatus: 'triggered',
    eventScore: 100,
    matchedKeywords: ['DeepSeek', 'DeepSeek-V4'],
    newsCount: 10,
    heatLevel: 'high',
    boardMappingPath: 'BK1188 -> 000771.DC -> tushare',
    boardCandidateCount: 60,
    primaryCatalyst: '模型发布',
  },
  stocks: [
    {
      rank: 1,
      stockCode: '688629.SH',
      stockName: '华丰科技',
      signalLevel: '持有候选',
      currentPattern: '回踩后企稳',
      selectionReason: '题材强相关 + MA10/MA20 结构完整',
      riskNote: '若跌破 MA20 需要降级观察',
      currentPrice: 136.0,
      supportLevel: 131.7,
      pressureLevel: 147.2,
      trendScore: 68,
      pctChg: 2.8,
      volumeRatio: 1.2,
      turnoverRate: 18.6,
      buySignal: '买入',
      dataCompleteness: 'full_realtime',
      miniReasons: ['MA10 仍在 MA20 上方', 'MA20 维持向上'],
    },
  ],
  selectedStock: {
    stockCode: '688629.SH',
    stockName: '华丰科技',
    themeRelevance: 'high',
    trendScore: 68,
    buySignal: '买入',
    ma5: 135.2,
    ma10: 131.7,
    ma20: 122.3,
    biasMa5: 1.8,
    biasMa10: 3.1,
    biasMa20: 7.6,
    recentStrongDays: 1,
    supportLevel: 131.7,
    pressureLevel: 147.2,
    newsSummary: ['DeepSeek-V4 发布带动概念热度提升'],
    selectedReasons: ['题材关联度高', '趋势底座完整'],
    riskReasons: ['若跌破 MA20 需要降级观察'],
    dataSources: {
      daily: 'tushare',
      realtime: 'tencent',
      board: 'tushare_dc',
    },
  },
  sourceInfo: {
    boardSource: 'tushare_dc',
    boardFallbackUsed: true,
    cacheHit: false,
    sourcePills: ['tushare', 'tencent', '新闻检索'],
    note: '板块主源异常时已切换到结构化备选源',
  },
  emptyReason: null,
};

describe('ThemeStockPickerPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getThemes.mockResolvedValue({
      items: [
        {
          id: 'deepseek',
          name: 'DeepSeek',
          boardCodes: ['BK1188'],
          boardNames: ['DeepSeek概念'],
          strategyMode: 'holding',
          enabled: true,
        },
      ],
    });
    scan.mockResolvedValue({
      taskId: 'theme-task-1',
      status: 'pending',
      message: '主题选股任务已接受',
    });
    getScanStatus.mockImplementation(async (taskId: string) => ({
      taskId,
      status: 'completed',
      progress: 100,
      message: '主题选股完成',
      createdAt: '2026-04-30T10:00:00',
      startedAt: '2026-04-30T10:00:01',
      completedAt: '2026-04-30T10:00:10',
      result: MOCK_RESULT,
    }));
    getHistory.mockResolvedValue({
      items: [
        {
          taskId: 'theme-task-history-1',
          status: 'completed',
          progress: 100,
          message: '主题选股完成',
          createdAt: '2026-04-29T10:00:00',
          startedAt: '2026-04-29T10:00:01',
          completedAt: '2026-04-29T10:00:08',
          query: MOCK_RESULT.query,
          themeName: 'DeepSeek',
          boardMappingPath: 'BK1188 -> 000771.DC -> tushare',
          stockCount: 1,
          topStockNames: ['华丰科技'],
          canRetry: true,
          result: MOCK_RESULT,
        },
      ],
    });
    retry.mockResolvedValue({
      taskId: 'theme-task-retry-1',
      status: 'pending',
      message: '已重新加入队列',
    });
  });

  it('restores the latest completed history result on first load and shows scan list', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    // Left sidebar shows recent scans
    expect(await screen.findByText('最近扫描')).toBeInTheDocument();
    // History item name is shown (may appear multiple times in breadcrumb + sidebar + detail)
    expect((await screen.findAllByText('DeepSeek')).length).toBeGreaterThan(0);
    // Table with candidate stocks
    expect(screen.getAllByText('华丰科技').length).toBeGreaterThan(0);
    expect(screen.getAllByText('688629.SH').length).toBeGreaterThan(0);
    expect(scan).not.toHaveBeenCalled();
  });

  it('opens new scan form and submits a theme search', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    // Wait for history to load
    expect(await screen.findByText('最近扫描')).toBeInTheDocument();

    // Open new scan form
    fireEvent.click(screen.getByText('新建主题扫描'));

    // Find DeepSeek quick theme chip and click it
    const themeChips = await screen.findAllByText('DeepSeek');
    // Click the chip in the form (the last one since the first may be in history list)
    const chipButton = themeChips.find(
      (el) => el.closest('button')?.className?.includes('rounded-lg'),
    );
    if (chipButton) fireEvent.click(chipButton);

    fireEvent.change(screen.getByLabelText('最大股票数量'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /开始筛选/ }));

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith(
        expect.objectContaining({
          themeId: 'deepseek',
          strategyMode: 'holding',
          maxCandidates: 12,
        }),
      );
    });
  });

  it('shows table with stock data and allows viewing detail', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    // Wait for auto-restore
    const stockNames = await screen.findAllByText('华丰科技');
    expect(stockNames.length).toBeGreaterThan(0);
    // Table shows key data
    expect(screen.getAllByText('688629.SH').length).toBeGreaterThan(0);
    // Selected stock detail panel should show
    expect(screen.getAllByText('支撑位').length).toBeGreaterThan(0);
    expect(screen.getAllByText('压力位').length).toBeGreaterThan(0);
  });

  it('navigates to deep analysis when clicking the button', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    const stockNames = await screen.findAllByText('华丰科技');
    expect(stockNames.length).toBeGreaterThan(0);
    const deepAnalysisBtn = screen.getByRole('button', { name: /深度分析/ });
    fireEvent.click(deepAnalysisBtn);
    expect(navigateMock).toHaveBeenCalledWith('/chat?stock=688629.SH&name=%E5%8D%8E%E4%B8%B0%E7%A7%91%E6%8A%80');
  });

  it('submits board code as the effective field from the form', async () => {
    getHistory.mockResolvedValueOnce({ items: [] });

    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    await screen.findByText('最近扫描');
    fireEvent.click(screen.getByText('新建主题扫描'));

    fireEvent.change(screen.getByLabelText('主题名称'), { target: { value: '新能源' } });
    fireEvent.change(screen.getByLabelText('板块代码（可选）'), { target: { value: 'BK0457' } });
    fireEvent.change(screen.getByLabelText('板块名称（可选）'), { target: { value: '新能源概念' } });

    expect(screen.getByText('板块代码直检')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /开始筛选/ }));

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith(
        expect.objectContaining({
          boardCode: 'BK0457',
          strategyMode: 'holding',
          maxCandidates: 8,
        }),
      );
    });

    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({ themeId: 'deepseek' }),
    );
  });

  it('normalizes prefixed themeName from route params', async () => {
    render(
      <MemoryRouter initialEntries={['/theme-picker?from=theme-factor&themeName=theme_name%3DDeepSeek']}>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    // Open form to see the value
    await screen.findByText('最近扫描');
    fireEvent.click(screen.getByText('新建主题扫描'));

    expect(await screen.findByDisplayValue('DeepSeek')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /开始筛选/ }));

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith(
        expect.objectContaining({
          themeName: 'DeepSeek',
          strategyMode: 'holding',
          maxCandidates: 8,
        }),
      );
    });
    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({ themeName: 'theme_name=DeepSeek' }),
    );
  });

  it('normalizes prefixed boardName before submitting board-name search', async () => {
    getHistory.mockResolvedValueOnce({ items: [] });

    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    await screen.findByText('最近扫描');
    fireEvent.click(screen.getByText('新建主题扫描'));

    fireEvent.change(screen.getByLabelText('板块名称（可选）'), { target: { value: 'board_name=DeepSeek概念' } });
    expect(screen.getByDisplayValue('DeepSeek概念')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /开始筛选/ }));

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith(
        expect.objectContaining({
          boardName: 'DeepSeek概念',
          strategyMode: 'holding',
          maxCandidates: 8,
        }),
      );
    });
    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({ boardName: 'board_name=DeepSeek概念' }),
    );
  });

  it('normalizes prefixed boardCode before submitting board-code search', async () => {
    getHistory.mockResolvedValueOnce({ items: [] });

    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    await screen.findByText('最近扫描');
    fireEvent.click(screen.getByText('新建主题扫描'));

    fireEvent.change(screen.getByLabelText('板块代码（可选）'), { target: { value: 'board_code=BK1188' } });
    expect(screen.getByDisplayValue('BK1188')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /开始筛选/ }));

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith(
        expect.objectContaining({
          boardCode: 'BK1188',
          strategyMode: 'holding',
          maxCandidates: 8,
        }),
      );
    });
    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({ boardCode: 'board_code=BK1188' }),
    );
  });
});
