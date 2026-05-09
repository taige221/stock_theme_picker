import type React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import DashboardPage from './pages/DashboardPage';
import DeepAnalysisPage from './pages/DeepAnalysisPage';
import SingleStockQueryPage from './pages/SingleStockQueryPage';
import ThemeStockPickerPage from './pages/ThemeStockPickerPage';
import WatchlistPage from './pages/WatchlistPage';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/theme-picker" element={<ThemeStockPickerPage />} />
          <Route path="/stock-query" element={<SingleStockQueryPage />} />
          <Route path="/deep-analysis" element={<DeepAnalysisPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
          <Route path="/chat" element={<DeepAnalysisPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
