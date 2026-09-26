import React, { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import { BrowserRouter as Router } from 'react-router-dom';
import { LanguageProvider } from './contexts/LanguageContext';
import { AuthProvider } from './contexts/AuthContext';
import { NotificationProvider } from './contexts/NotificationContext';
import ReminderAlert from './components/ReminderAlert';
import { AppToaster } from './lib/notify';
import MaintenanceGate from './components/MaintenanceGate';

createRoot(document.getElementById("root")).render(
  <>
    <ErrorBoundary>
      <Router>
        <AuthProvider>
          <LanguageProvider>
            <NotificationProvider>
              <App />
              <ReminderAlert />
              <AppToaster />
            </NotificationProvider>
          </LanguageProvider>
        </AuthProvider>
      </Router>
    </ErrorBoundary>
    {/* Fora do ErrorBoundary: continua exibindo a manutenção e recarregando mesmo se o app quebrar */}
    <MaintenanceGate />
  </>
);
