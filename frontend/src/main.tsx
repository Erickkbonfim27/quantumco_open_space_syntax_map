import "@fontsource/outfit/200.css";
import "@fontsource/outfit/300.css";
import "@fontsource/outfit/400.css";
import "@fontsource/outfit/500.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";

import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router";

import { SessionProvider, useSession } from "./lib/session";
import { ThemeProvider } from "./lib/theme";
import { ConfirmEmail, ForgotPassword, ResetPassword } from "./pages/AccountLinks";
import { Auth } from "./pages/Auth";
import { Dashboard } from "./pages/Dashboard";
import { DataPage } from "./pages/DataPage";
import { MethodologyPage } from "./pages/MethodologyPage";
import { Landing } from "./pages/Landing";
import { Profile } from "./pages/Profile";
import { PublicMap } from "./pages/PublicMap";
import { WorkspaceMap } from "./pages/WorkspaceMap";
import "./styles.css";
import "./platform.css";
import "./scenario.css";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useSession();
  const location = useLocation();
  if (loading) return <div className="center-message">Carregando…</div>;
  if (!user) return <Navigate to="/entrar" replace state={{ from: location.pathname }} />;
  return children;
}

const root = document.getElementById("root");
if (!root) throw new Error("elemento #root não encontrado");

createRoot(root).render(
  <StrictMode>
    <ThemeProvider>
    <BrowserRouter>
      <SessionProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/map" element={<PublicMap />} />
          <Route path="/dados" element={<DataPage />} />
          <Route path="/metodologia" element={<MethodologyPage />} />
          <Route path="/entrar" element={<Auth mode="login" />} />
          <Route path="/criar-conta" element={<Auth mode="signup" />} />
          <Route path="/esqueci-senha" element={<ForgotPassword />} />
          <Route path="/redefinir-senha" element={<ResetPassword />} />
          <Route path="/confirmar-email" element={<ConfirmEmail />} />
          <Route
            path="/perfil"
            element={
              <RequireAuth>
                <Profile />
              </RequireAuth>
            }
          />
          <Route
            path="/painel"
            element={
              <RequireAuth>
                <Dashboard />
              </RequireAuth>
            }
          />
          <Route
            path="/painel/cenario/:id"
            element={
              <RequireAuth>
                <WorkspaceMap />
              </RequireAuth>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </SessionProvider>
    </BrowserRouter>
    </ThemeProvider>
  </StrictMode>,
);
