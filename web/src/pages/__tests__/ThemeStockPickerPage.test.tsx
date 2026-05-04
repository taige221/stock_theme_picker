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
      result: {
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
      },
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
          query: {
            themeId: 'deepseek',
            themeName: 'DeepSeek',
            boardCode: 'BK1188',
            boardName: 'DeepSeek概念',
            strategyMode: 'holding',
            maxCandidates: 8,
          },
          themeName: 'DeepSeek',
          boardMappingPath: 'BK1188 -> 000771.DC -> tushare',
          stockCount: 1,
          topStockNames: ['华丰科技'],
          canRetry: true,
          result: {
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
              matchedKeywords: ['DeepSeek'],
              newsCount: 8,
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
                selectionReason: '题材强相关 + MA10/MA20 结构完整',
                miniReasons: ['MA10 仍在 MA20 上方'],
              },
            ],
            selectedStock: {
              stockCode: '688629.SH',
              stockName: '华丰科技',
              newsSummary: [],
              selectedReasons: ['题材关联度高'],
              riskReasons: [],
              dataSources: {},
            },
            sourceInfo: {
              sourcePills: ['tushare'],
            },
          },
        },
      ],
    });
    retry.mockResolvedValue({
      taskId: 'theme-task-retry-1',
      status: 'pending',
      message: '已重新加入队列',
    });
  });

  it('loads registered themes and renders picker layout with inline stock detail panel', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: '主题选股' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'DeepSeek' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'DeepSeek' }));
    fireEvent.change(screen.getByLabelText('最大股票数量'), { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: '开始筛选' }));

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith(
        expect.objectContaining({
          themeId: 'deepseek',
          strategyMode: 'holding',
          maxCandidates: 12,
        }),
      );
    });
    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({
        boardCode: 'BK1188',
      }),
    );
    await waitFor(() => {
      expect(getScanStatus).toHaveBeenCalledWith('theme-task-1');
    });

    expect(await screen.findByText('优质股票')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /华丰科技/ })).toBeInTheDocument();
    expect(screen.getAllByText('BK1188 -> 000771.DC -> tushare').length).toBeGreaterThan(0);
    expect(screen.getAllByText('题材强相关 + MA10/MA20 结构完整').length).toBeGreaterThan(0);
    expect(screen.getByText('新闻摘要')).toBeInTheDocument();
    expect(screen.getByText('为什么入选')).toBeInTheDocument();
    expect(screen.getAllByText('支撑位').length).toBeGreaterThan(0);
    expect(screen.getAllByText('压力位').length).toBeGreaterThan(0);
    expect(screen.getByText('136.00')).toBeInTheDocument();
    expect(screen.getAllByText('688629.SH').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /华丰科技/ }));
    expect(screen.getByText('强相关')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '发起深度分析' }));
    expect(navigateMock).toHaveBeenCalledWith('/chat?stock=688629.SH&name=%E5%8D%8E%E4%B8%B0%E7%A7%91%E6%8A%80');
  });

  it('restores the latest completed history result by default on first load', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    expect((await screen.findAllByText('BK1188 -> 000771.DC -> tushare')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('华丰科技').length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue('8')).toBeInTheDocument();
    expect(scan).not.toHaveBeenCalled();
  });

  it('submits board code as the only effective query field when manual board inputs are provided', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    await screen.findByRole('heading', { name: '主题选股' });

    fireEvent.change(screen.getByLabelText('主题名称'), { target: { value: '新能源' } });
    fireEvent.change(screen.getByLabelText('板块代码（可选）'), { target: { value: 'BK0457' } });
    fireEvent.change(screen.getByLabelText('板块名称（可选）'), { target: { value: '新能源概念' } });

    expect(screen.getByText('板块代码直检')).toBeInTheDocument();
    expect(screen.getByText('当前会按板块代码检索：BK0457')).toBeInTheDocument();
    expect(screen.getByText('板块名称“新能源概念”仅作辅助展示，不参与提交。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '开始筛选' }));

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
      expect.not.objectContaining({
        themeId: 'deepseek',
      }),
    );
    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({
        boardName: '新能源概念',
      }),
    );
    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({
        themeName: '新能源',
      }),
    );
  });

  it('clears stale theme binding when manually editing theme name before scan', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    expect(await screen.findByDisplayValue('DeepSeek')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('主题名称'), { target: { value: '新能源' } });
    fireEvent.click(screen.getByRole('button', { name: '开始筛选' }));

    await waitFor(() => {
      expect(scan).toHaveBeenCalledWith(
        expect.objectContaining({
          themeName: '新能源',
          strategyMode: 'holding',
          maxCandidates: 8,
        }),
      );
    });
    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({
        themeId: 'deepseek',
      }),
    );
    expect(scan).toHaveBeenCalledWith(
      expect.not.objectContaining({
        boardCode: 'BK1188',
      }),
    );
  });

  it('opens history drawer and restores a completed historical result', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '历史记录' }));

    expect(await screen.findByText('主题选股历史')).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: '恢复查看' }));

    expect(await screen.findByText('优质股票')).toBeInTheDocument();
    expect(screen.getAllByText('华丰科技').length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue('DeepSeek')).toBeInTheDocument();
    expect(screen.getByDisplayValue('BK1188')).toBeInTheDocument();
    expect(screen.getByDisplayValue('8')).toBeInTheDocument();
  });

  it('can retry a historical task from history drawer', async () => {
    render(
      <MemoryRouter>
        <ThemeStockPickerPage />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole('button', { name: '历史记录' }));
    fireEvent.click(await screen.findByRole('button', { name: '重新筛选' }));

    await waitFor(() => {
      expect(retry).toHaveBeenCalledWith('theme-task-history-1');
    });
    await waitFor(() => {
      expect(getScanStatus).toHaveBeenCalledWith('theme-task-retry-1');
    });
  });
});
