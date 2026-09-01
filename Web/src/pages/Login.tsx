import React, { useState, useEffect } from 'react';
import { LogIn, Mail, ArrowLeft, CheckCircle2, Lock, Send, KeyRound, Eye, EyeOff, ShieldCheck, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { API_BASE_URL } from '../config';

interface LoginProps {
  onLogin: (userName: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [view, setView] = useState<'login' | 'forgot-password' | 'reset-password'>('login');
  
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);

  const [rememberMe, setRememberMe] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Auto-detect password recovery link and load remembered email
  useEffect(() => {
    const savedEmail = localStorage.getItem('rll_remembered_email');
    if (savedEmail) {
      setEmail(savedEmail);
      setRememberMe(true);
    }
    const hash = window.location.hash;
    const search = window.location.search;
    if (hash.includes('type=recovery') || search.includes('type=recovery') || hash.includes('access_token')) {
      setView('reset-password');
      setSuccessMessage('Recovery link verified. Please enter your email and new password below to reset.');
    }
  }, []);

  // Helper to extract clean error message from API response
  const formatErrorMessage = (detail: any, fallback: string): string => {
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const item = detail[0];
      if (typeof item === 'string') return item;
      if (item && typeof item === 'object' && item.msg) return item.msg;
    }
    return fallback;
  };

  // 1. Email & Password Admin Login Submit
  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const cleanEmail = email.trim();
    if (!cleanEmail || !password) return;

    setLoading(true);
    const namePart = cleanEmail.split('@')[0];
    const formattedName = namePart
      .split(/[._-]/)
      .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(' ');
    const fallbackName = formattedName || 'User';

    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify({ email: cleanEmail, password, remember_me: rememberMe }),
      });

      if (response.ok) {
        const data = await response.json();
        if (rememberMe) {
          localStorage.setItem('rll_remembered_email', cleanEmail);
        } else {
          localStorage.removeItem('rll_remembered_email');
        }
        localStorage.setItem('token', data.access_token);
        const displayName = data.user?.first_name 
          ? `${data.user.first_name} ${data.user.last_name || ''}`.trim() 
          : (data.user?.name || fallbackName);
        localStorage.setItem('user_name', displayName);
        onLogin(displayName);
      } else {
        const errData = await response.json().catch(() => ({}));
        setError(formatErrorMessage(errData.detail, 'Login failed. Please check your email and password.'));
      }
    } catch (err) {
      console.error('Backend authentication connection failed:', err);
      setError('Unable to connect to authentication server. Please check your connection.');
    } finally {
      setLoading(false);
    }
  };

  // 2. Request Password Reset Link via Email
  const handleSendResetLinkSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim();
    if (!cleanEmail) {
      setError('Please enter your registered email address.');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/forgot-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: cleanEmail }),
      });

      const data = await response.json().catch(() => ({}));

      if (response.ok) {
        setSuccessMessage(`Password reset link dispatched to ${cleanEmail}. Please check your email inbox!`);
      } else {
        setError(formatErrorMessage(data.detail, 'Failed to send password reset link. Please check your email.'));
      }
    } catch (err) {
      console.error('Send reset link error:', err);
      setError('Unable to send reset link. Connection error.');
    } finally {
      setLoading(false);
    }
  };

  // 3. Direct Password Reset (Updates password & automatically returns to login page)
  const handleResetPasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim();
    const cleanNewPassword = newPassword.trim();

    if (!cleanEmail || !cleanNewPassword) {
      setError('Please enter your registered email address and new password.');
      return;
    }

    if (cleanNewPassword.length < 6) {
      setError('New password must be at least 6 characters long.');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/reset-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: cleanEmail,
          new_password: cleanNewPassword,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (response.ok) {
        setPassword('');
        setSuccessMessage('Password reset successfully! Please sign in with your new password.');
        setView('login');
      } else {
        setError(formatErrorMessage(data.detail, 'Failed to reset password. Please verify your email.'));
      }
    } catch (err) {
      console.error('Password reset error:', err);
      setError('Unable to reset password. Connection error.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans relative overflow-hidden">
      {/* Background Soft Glow Accents */}
      <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-blue-600/5 rounded-full blur-3xl pointer-events-none" />

      {/* Brand Header */}
      <motion.div 
        initial={{ opacity: 0, y: -15 }}
        animate={{ opacity: 1, y: 0 }}
        className="sm:mx-auto sm:w-full sm:max-w-md text-center z-10"
      >
        <div className="inline-flex p-3 bg-white rounded-3xl shadow-sm border border-slate-200/80 mb-3">
          <img src="/images/rll logo.svg" alt="RLL Logo" className="w-28 h-28 object-contain" />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-slate-900">
          RLL Admin Portal
        </h1>
        <p className="mt-1 text-xs text-slate-500 font-medium">
          Rajasthan Liquor Limited Administrative Dashboard
        </p>
      </motion.div>

      {/* Login Card */}
      <motion.div 
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08 }}
        className="mt-6 sm:mx-auto sm:w-full sm:max-w-md relative z-10 px-4 sm:px-0"
      >
        <div className="bg-white border border-slate-200/80 shadow-xl shadow-slate-200/50 rounded-2xl p-6 sm:p-8">
          
          {/* Notifications */}
          {error && (
            <div className="mb-5 p-3 rounded-xl text-xs font-medium bg-red-50 border border-red-200/80 text-red-700 flex items-start gap-2 leading-relaxed">
              <AlertCircle className="w-4 h-4 shrink-0 text-red-600 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {successMessage && (
            <div className="mb-5 p-3 rounded-xl text-xs font-medium bg-emerald-50 border border-emerald-200/80 text-emerald-700 flex items-start gap-2 leading-relaxed">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 mt-0.5" />
              <span>{successMessage}</span>
            </div>
          )}

          <AnimatePresence mode="wait">
            {/* VIEW 1: LOGIN FORM */}
            {view === 'login' && (
              <motion.form 
                key="login"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 8 }}
                transition={{ duration: 0.15 }}
                className="space-y-4" 
                onSubmit={handleLoginSubmit}
              >
                <div>
                  <label htmlFor="email" className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5">
                    Email Address
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-xl border border-slate-200 pl-10 pr-4 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-slate-50/50 shadow-2xs focus:bg-white focus:border-[#0D3B8E] focus:outline-none focus:ring-2 focus:ring-[#0D3B8E]/15 transition-all"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="password" className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="block w-full rounded-xl border border-slate-200 pl-10 pr-10 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-slate-50/50 shadow-2xs focus:bg-white focus:border-[#0D3B8E] focus:outline-none focus:ring-2 focus:ring-[#0D3B8E]/15 transition-all"
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                      title={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs pt-1">
                  <div className="flex items-center">
                    <input
                      id="remember-me"
                      name="remember-me"
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 text-[#0D3B8E] focus:ring-[#0D3B8E]/20 cursor-pointer"
                    />
                    <label htmlFor="remember-me" className="ml-2 text-xs font-medium text-slate-600 cursor-pointer">
                      Remember me
                    </label>
                  </div>

                  <button 
                    type="button" 
                    onClick={() => { setView('forgot-password'); setError(null); setSuccessMessage(null); }} 
                    className="text-xs font-semibold text-[#0D3B8E] hover:text-blue-800 transition-colors cursor-pointer"
                  >
                    Forgot password?
                  </button>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center items-center gap-2 py-2.5 px-4 rounded-xl bg-[#0D3B8E] hover:bg-[#0A2F73] active:bg-[#082459] text-white text-xs font-bold shadow-md shadow-blue-900/10 transition-all mt-2 disabled:opacity-60 cursor-pointer"
                >
                  <LogIn className="w-4 h-4" />
                  {loading ? 'Authenticating...' : 'Sign In'}
                </button>
              </motion.form>
            )}

            {/* VIEW 2: FORGOT PASSWORD */}
            {view === 'forgot-password' && (
              <motion.form
                key="forgot-password"
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.15 }}
                className="space-y-4"
                onSubmit={handleSendResetLinkSubmit}
              >
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Reset Password
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Enter your registered email address and we'll send you a password recovery link.
                  </p>
                </div>

                <div>
                  <label htmlFor="reset-email" className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5">
                    Registered Email Address
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      id="reset-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-xl border border-slate-200 pl-10 pr-4 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-slate-50/50 shadow-2xs focus:bg-white focus:border-[#0D3B8E] focus:outline-none focus:ring-2 focus:ring-[#0D3B8E]/15 transition-all"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center items-center gap-2 py-2.5 px-4 rounded-xl bg-[#0D3B8E] hover:bg-[#0A2F73] text-white text-xs font-bold shadow-md shadow-blue-900/10 transition-all cursor-pointer disabled:opacity-60"
                >
                  <Send className="w-3.5 h-3.5" />
                  {loading ? 'Sending Link...' : 'Send Reset Link'}
                </button>

                <div className="pt-2 flex items-center justify-between text-xs border-t border-slate-100">
                  <button 
                    type="button" 
                    onClick={() => { setView('login'); setError(null); }} 
                    className="inline-flex items-center text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
                  >
                    <ArrowLeft className="w-3.5 h-3.5 mr-1" />
                    Back to Sign In
                  </button>
                </div>
              </motion.form>
            )}

            {/* VIEW 3: RESET PASSWORD FORM */}
            {view === 'reset-password' && (
              <motion.form
                key="reset-password"
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.15 }}
                className="space-y-4"
                onSubmit={handleResetPasswordSubmit}
              >
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Set New Password
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Enter your registered email and choose a new password.
                  </p>
                </div>

                <div>
                  <label htmlFor="reset-email" className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5">
                    Registered Email Address
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      id="reset-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-xl border border-slate-200 pl-10 pr-4 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-slate-50/50 shadow-2xs focus:bg-white focus:border-[#0D3B8E] focus:outline-none focus:ring-2 focus:ring-[#0D3B8E]/15 transition-all"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="new-password" className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5">
                    New Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      id="new-password"
                      type={showNewPassword ? "text" : "password"}
                      required
                      minLength={6}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="At least 6 characters"
                      className="block w-full rounded-xl border border-slate-200 pl-10 pr-10 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-slate-50/50 shadow-2xs focus:bg-white focus:border-[#0D3B8E] focus:outline-none focus:ring-2 focus:ring-[#0D3B8E]/15 transition-all"
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPassword(!showNewPassword)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
                      title={showNewPassword ? "Hide password" : "Show password"}
                    >
                      {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center items-center gap-2 py-2.5 px-4 rounded-xl bg-[#0D3B8E] hover:bg-[#0A2F73] text-white text-xs font-bold shadow-md shadow-blue-900/10 transition-all cursor-pointer disabled:opacity-60"
                >
                  {loading ? 'Resetting Password...' : 'Reset Password & Sign In'}
                </button>

                <div className="pt-2 text-center border-t border-slate-100">
                  <button 
                    type="button" 
                    onClick={() => { setView('login'); setError(null); }} 
                    className="inline-flex items-center text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors cursor-pointer"
                  >
                    <ArrowLeft className="w-3.5 h-3.5 mr-1" />
                    Back to Sign In
                  </button>
                </div>
              </motion.form>
            )}
          </AnimatePresence>
        </div>

        {/* Security Footer Badge */}
        <div className="mt-6 text-center text-[11px] text-slate-400 font-medium flex items-center justify-center gap-1.5">
          <ShieldCheck className="w-3.5 h-3.5 text-slate-400" />
          <span>Rajasthan State Enterprise Portal • 256-Bit Encrypted</span>
        </div>
      </motion.div>
    </div>
  );
}
