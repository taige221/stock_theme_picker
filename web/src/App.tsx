import type React from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import ThemeStockPickerPage from './pages/ThemeStockPickerPage';
import ChatPlaceholderPage from './pages/ChatPlaceholderPage';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/theme-picker" replace />} />
        <Route path="/theme-picker" element={<ThemeStockPickerPage />} />
        <Route path="/chat" element={<ChatPlaceholderPage />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
