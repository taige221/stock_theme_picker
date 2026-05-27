import type React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import DashboardPage from './pages/DashboardPage';
import DeepAnalysisPage from './pages/DeepAnalysisPage';
import EtfQueryPage from './pages/EtfQueryPage';
import InformationWatchPage from './pages/InformationWatchPage';
import SettingsPage from './pages/SettingsPage';
import SingleStockQueryPage from './pages/SingleStockQueryPage';
import StrategyBacktestPage from './pages/StrategyBacktestPage';
import ThemeStockPickerPage from './pages/ThemeStockPickerPage';
import ThemeFactorScanPage from './pages/ThemeFactorScanPage';
import WatchlistPage from './pages/WatchlistPage';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/information-watch" element={<InformationWatchPage />} />
          <Route path="/theme-factor-scans" element={<ThemeFactorScanPage />} />
          <Route path="/theme-picker" element={<ThemeStockPickerPage />} />
          <Route path="/stock-query" element={<SingleStockQueryPage />} />
          <Route path="/etf-query" element={<EtfQueryPage />} />
          <Route path="/strategy-backtest" element={<StrategyBacktestPage />} />
          <Route path="/deep-analysis" element={<DeepAnalysisPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/chat" element={<DeepAnalysisPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
