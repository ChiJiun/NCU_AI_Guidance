/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { onAuthStateChanged } from 'firebase/auth';
import { authAPI } from '../api/services';
import { firebaseAuth, signInWithGoogle, signOutOfFirebase } from './firebase';
import { DEMO_MODE } from '../demo/config';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  picture: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  // 展示模式不提供登入：不監聽 Firebase 登入狀態，user 永遠是 null
  const [loading, setLoading] = useState(!DEMO_MODE);

  useEffect(() => {
    if (DEMO_MODE) return;
    return onAuthStateChanged(firebaseAuth, async (firebaseUser) => {
      if (!firebaseUser) {
        setUser(null);
        setLoading(false);
        return;
      }

      try {
        setUser(await authAPI.me());
      } catch {
        setUser({
          id: `firebase:${firebaseUser.uid}`,
          email: firebaseUser.email ?? '',
          name: firebaseUser.displayName ?? firebaseUser.email ?? '',
          picture: firebaseUser.photoURL ?? '',
        });
      } finally {
        setLoading(false);
      }
    });
  }, []);

  const loginWithGoogle = useCallback(async () => {
    if (DEMO_MODE) return;
    await signInWithGoogle();
  }, []);

  const logout = useCallback(async () => {
    await signOutOfFirebase();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, loginWithGoogle, logout }),
    [user, loading, loginWithGoogle, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
