import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

interface AuthUser {
  id: string;
  username: string;
  email: string;
  role: "admin" | "superadmin";
  createdAt: string;
}

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (username: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

const STORAGE_KEY = "shadowpanel_auth";

// Simulates a backend JWT auth flow.
// In production, replace with real API calls to your Node.js backend.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setUser(parsed.user);
        setToken(parsed.token);
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    setLoading(false);
  }, []);

  const persist = (u: AuthUser, t: string) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ user: u, token: t }));
    setUser(u);
    setToken(t);
  };

  const login = async (email: string, password: string) => {
    // Simulated network delay
    await new Promise((r) => setTimeout(r, 700));
    if (password.length < 4) throw new Error("Invalid credentials");
    const mockToken = `eyJhbGciOiJIUzI1NiJ9.${btoa(email)}.${Date.now()}`;
    persist(
      {
        id: "usr_" + Math.random().toString(36).slice(2, 10),
        username: email.split("@")[0] || "admin",
        email,
        role: "superadmin",
        createdAt: new Date().toISOString(),
      },
      mockToken,
    );
  };

  const register = async (username: string, email: string, password: string) => {
    await new Promise((r) => setTimeout(r, 900));
    if (password.length < 6) throw new Error("Password must be 6+ characters");
    const mockToken = `eyJhbGciOiJIUzI1NiJ9.${btoa(email)}.${Date.now()}`;
    persist(
      {
        id: "usr_" + Math.random().toString(36).slice(2, 10),
        username,
        email,
        role: "admin",
        createdAt: new Date().toISOString(),
      },
      mockToken,
    );
  };

  const logout = () => {
    localStorage.removeItem(STORAGE_KEY);
    setUser(null);
    setToken(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, token, loading, login, register, logout, isAuthenticated: !!user }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
