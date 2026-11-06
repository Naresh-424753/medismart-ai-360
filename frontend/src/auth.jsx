import { createContext, useContext, useEffect, useState } from "react";
import { api, tokenStore } from "./api.js";

const Ctx = createContext(null);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!tokenStore.get());

  useEffect(() => {
    if (!tokenStore.get()) return;
    api("/auth/me")
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, []);

  const finish = (r) => { tokenStore.set(r.token); setUser(r.user); return r; };
  // Returns {requires_otp:true} when 2FA is on; then call verifyLoginOtp.
  const login = async (email, password) => {
    const r = await api("/auth/login", { method: "POST", body: { email, password } });
    return r.requires_otp ? r : finish(r);
  };
  const verifyLoginOtp = async (email, otp) =>
    finish(await api("/auth/verify-otp", { method: "POST", body: { email, otp, purpose: "login" } }));
  const logout = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {}
    tokenStore.clear();
    setUser(null);
  };
  return <Ctx.Provider value={{ user, loading, login, verifyLoginOtp, logout, setUser }}>{children}</Ctx.Provider>;
}
