// src/contexts/AuthContext.jsx
import { createContext, useContext, useEffect, useState } from "react";
import { supabase } from "../lib/supabase";

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 🔥 초기 세션 로드
    const initSession = async () => {
      const { data, error } = await supabase.auth.getSession();

      if (error) {
        console.error("Get session error:", error.message);
      }

      const session = data?.session ?? null;
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    };

    initSession();

    // 🔥 auth 상태 변경 감지
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      setUser(session?.user ?? null);
      setLoading(false);
    });

    return () => {
      subscription?.unsubscribe();
    };
  }, []);

  // 🔐 로그인
  const signIn = async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (error) {
      console.error("Login error:", error.message);
      return { error: error.message };
    }

    setSession(data.session);
    setUser(data.session?.user ?? null);

    return { user: data.user };
  };

  // 🚪 로그아웃
  const signOut = async () => {
    const { error } = await supabase.auth.signOut();

    if (error) {
      console.error("Logout error:", error.message);
    }

    setSession(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        loading,
        signIn,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// 🔥 커스텀 훅
export const useAuth = () => {
  return useContext(AuthContext);
};