import { createContext, type ReactNode, use, useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "./api";
import type { User, UserPreferences } from "./platformTypes";
import { useTheme } from "./theme";

interface SignUpData {
  name: string;
  email: string;
  organization: string;
  password: string;
}

interface SessionValue {
  user: User | null;
  loading: boolean;
  logIn: (email: string, password: string) => Promise<void>;
  signUp: (data: SignUpData) => Promise<void>;
  logOut: () => Promise<void>;
  /** troca o usuário em memória (depois de editar o perfil) */
  replaceUser: (user: User) => void;
  /** grava tema/fundo no perfil (sem sessão, fica só neste navegador) */
  savePreferences: (prefs: UserPreferences) => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const { setPreference } = useTheme();
  const savedTheme = user?.preferences.theme;

  // o tema salvo no perfil vale em qualquer aparelho em que a pessoa entrar
  useEffect(() => {
    if (savedTheme) setPreference(savedTheme);
  }, [savedTheme, setPreference]);

  useEffect(() => {
    api<{ user: User }>("me")
      .then((body) => setUser(body.user))
      .catch((error: unknown) => {
        if (!(error instanceof ApiError && error.status === 401)) console.warn(error);
        setUser(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const logIn = useCallback(async (email: string, password: string) => {
    const body = await api<{ user: User }>("auth/login", {
      method: "POST",
      json: { email, password },
    });
    setUser(body.user);
  }, []);

  const signUp = useCallback(async (data: SignUpData) => {
    const body = await api<{ user: User }>("auth/signup", {
      method: "POST",
      json: { ...data, organization: data.organization || null },
    });
    setUser(body.user);
  }, []);

  const logOut = useCallback(async () => {
    await api("auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
  }, []);

  const replaceUser = useCallback((next: User) => setUser(next), []);

  const savePreferences = useCallback(
    (prefs: UserPreferences) => {
      if (!user) return;
      setUser({ ...user, preferences: { ...user.preferences, ...prefs } });
      void api<{ user: User }>("me", { method: "PATCH", json: { preferences: prefs } }).catch(() => undefined);
    },
    [user],
  );

  const value = useMemo(
    () => ({ user, loading, logIn, signUp, logOut, replaceUser, savePreferences }),
    [user, loading, logIn, signUp, logOut, replaceUser, savePreferences],
  );
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): SessionValue {
  const value = use(SessionContext);
  if (!value) throw new Error("useSession fora do SessionProvider");
  return value;
}
