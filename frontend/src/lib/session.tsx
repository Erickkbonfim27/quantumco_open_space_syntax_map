import { createContext, type ReactNode, use, useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "./api";
import type { User } from "./platformTypes";

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
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

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

  const value = useMemo(
    () => ({ user, loading, logIn, signUp, logOut }),
    [user, loading, logIn, signUp, logOut],
  );
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): SessionValue {
  const value = use(SessionContext);
  if (!value) throw new Error("useSession fora do SessionProvider");
  return value;
}
