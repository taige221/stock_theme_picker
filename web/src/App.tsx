import type React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import DashboardPage from './pages/DashboardPage';
import SingleStockQueryPage from './pages/SingleStockQueryPage';
import ThemeStockPickerPage from './pages/ThemeStockPickerPage';
import WatchlistPage from './pages/WatchlistPage';
import ChatPlaceholderPage from './pages/ChatPlaceholderPage';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/theme-picker" element={<ThemeStockPickerPage />} />
          <Route path="/stock-query" element={<SingleStockQueryPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
          <Route path="/chat" element={<ChatPlaceholderPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
