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
    <div className="min-h-screen bg-gradient-to-br from-slate-100 via-blue-50/50 to-slate-200/80 flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans relative overflow-hidden selection:bg-[#0D3B8E] selection:text-white">
      {/* High-Intensity Ambient Glassmorphism Background Orbs */}
      <div className="absolute top-1/4 -left-32 w-[480px] h-[480px] bg-gradient-to-tr from-[#0D3B8E]/20 to-blue-400/15 rounded-full blur-[100px] pointer-events-none animate-pulse" style={{ animationDuration: '7s' }} />
      <div className="absolute top-1/2 -right-32 -translate-y-1/2 w-[480px] h-[480px] bg-gradient-to-br from-indigo-500/15 to-[#0D3B8E]/20 rounded-full blur-[110px] pointer-events-none animate-pulse" style={{ animationDuration: '9s' }} />
      <div className="absolute -bottom-32 left-1/3 w-[500px] h-[500px] bg-gradient-to-t from-sky-400/15 to-[#0D3B8E]/15 rounded-full blur-[120px] pointer-events-none animate-pulse" style={{ animationDuration: '11s' }} />

      {/* Subtle Frosted Grid Lines Overlay */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#0d3b8e0a_1px,transparent_1px),linear-gradient(to_bottom,#0d3b8e0a_1px,transparent_1px)] bg-[size:3.5rem_3.5rem] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_50%,#000_70%,transparent_100%)] pointer-events-none" />

      {/* Brand Header */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="sm:mx-auto sm:w-full sm:max-w-md text-center z-10"
      >
        <div className="inline-flex p-4 bg-white/60 backdrop-blur-2xl rounded-3xl shadow-[0_12px_40px_rgba(13,59,142,0.08)] border border-white/80 mb-4 transition-all duration-300 hover:scale-105 hover:bg-white/80 hover:border-white">
          <img src="/images/rll logo.svg" alt="RLL Logo" className="w-28 h-28 object-contain filter drop-shadow-xs" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 drop-shadow-xs">
          RLL Admin Portal
        </h1>
        <p className="mt-1.5 text-xs text-slate-500 font-medium tracking-wide">
          Rajasthan Liquor Limited Administrative Dashboard
        </p>
      </motion.div>

      {/* Maximum Glassmorphism Auth Card */}
      <motion.div 
        initial={{ opacity: 0, y: 25, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
        className="mt-6 sm:mx-auto sm:w-full sm:max-w-md relative z-10 px-4 sm:px-0"
      >
        <div className="bg-white/55 backdrop-blur-3xl border border-white/80 shadow-[0_20px_60px_rgba(13,59,142,0.12),0_0_30px_rgba(255,255,255,0.6)_inset] rounded-3xl p-6 sm:p-9 relative overflow-hidden">
          {/* Glossy Top Border Specular Reflection Line */}
          <div className="absolute inset-x-0 top-0 h-[1.5px] bg-gradient-to-r from-transparent via-white to-transparent pointer-events-none opacity-90" />
          <div className="absolute -inset-x-20 top-0 h-32 bg-gradient-to-b from-white/30 via-transparent to-transparent pointer-events-none" />

          {/* Notifications */}
          {error && (
            <motion.div 
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 p-3.5 rounded-2xl text-xs font-medium bg-red-50/80 border border-red-200/80 text-red-700 flex items-start gap-2.5 shadow-sm backdrop-blur-xl leading-relaxed"
            >
              <AlertCircle className="w-4 h-4 shrink-0 text-red-600 mt-0.5" />
              <span>{error}</span>
            </motion.div>
          )}

          {successMessage && (
            <motion.div 
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 p-3.5 rounded-2xl text-xs font-medium bg-emerald-50/80 border border-emerald-200/80 text-emerald-700 flex items-start gap-2.5 shadow-sm backdrop-blur-xl leading-relaxed"
            >
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 mt-0.5" />
              <span>{successMessage}</span>
            </motion.div>
          )}

          <AnimatePresence mode="wait">
            {/* VIEW 1: LOGIN FORM */}
            {view === 'login' && (
              <motion.form 
                key="login"
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 12 }}
                transition={{ duration: 0.2 }}
                className="space-y-4.5" 
                onSubmit={handleLoginSubmit}
              >
                <div>
                  <label htmlFor="email" className="block text-xs font-bold text-slate-700 tracking-wide mb-1.5">
                    Email Address
                  </label>
                  <div className="relative group">
                    <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 transition-colors group-focus-within:text-[#0D3B8E]" />
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-2xl border border-white/60 pl-10 pr-4 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-white/40 backdrop-blur-xl shadow-[inset_0_1px_2px_rgba(255,255,255,0.7)] focus:bg-white/80 focus:border-[#0D3B8E] focus:outline-none focus:ring-4 focus:ring-[#0D3B8E]/15 transition-all duration-200"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="password" className="block text-xs font-bold text-slate-700 tracking-wide mb-1.5">
                    Password
                  </label>
                  <div className="relative group">
                    <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 transition-colors group-focus-within:text-[#0D3B8E]" />
                    <input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="block w-full rounded-2xl border border-white/60 pl-10 pr-10 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-white/40 backdrop-blur-xl shadow-[inset_0_1px_2px_rgba(255,255,255,0.7)] focus:bg-white/80 focus:border-[#0D3B8E] focus:outline-none focus:ring-4 focus:ring-[#0D3B8E]/15 transition-all duration-200"
                      placeholder="••••••••"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer p-1 rounded-lg hover:bg-white/50"
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
                      className="h-4 w-4 rounded-md border-slate-300 text-[#0D3B8E] focus:ring-[#0D3B8E]/20 cursor-pointer accent-[#0D3B8E]"
                    />
                    <label htmlFor="remember-me" className="ml-2 text-xs font-medium text-slate-600 cursor-pointer select-none">
                      Remember me
                    </label>
                  </div>

                  <button 
                    type="button" 
                    onClick={() => { setView('forgot-password'); setError(null); setSuccessMessage(null); }} 
                    className="text-xs font-bold text-[#0D3B8E] hover:text-blue-800 hover:underline transition-all cursor-pointer"
                  >
                    Forgot password?
                  </button>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center items-center gap-2 py-3 px-4 rounded-2xl bg-gradient-to-r from-[#0D3B8E] to-[#0A2F73] hover:from-[#0B337D] hover:to-[#082459] active:scale-[0.99] text-white text-xs font-bold shadow-lg shadow-[#0D3B8E]/25 hover:shadow-xl hover:shadow-[#0D3B8E]/35 border border-white/30 backdrop-blur-xl transition-all duration-200 mt-2 disabled:opacity-60 cursor-pointer"
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
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
                className="space-y-4.5"
                onSubmit={handleSendResetLinkSubmit}
              >
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Reset Password
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                    Enter your registered email address and we'll send you a password recovery link.
                  </p>
                </div>

                <div>
                  <label htmlFor="reset-email" className="block text-xs font-bold text-slate-700 tracking-wide mb-1.5">
                    Registered Email Address
                  </label>
                  <div className="relative group">
                    <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 transition-colors group-focus-within:text-[#0D3B8E]" />
                    <input
                      id="reset-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-2xl border border-white/60 pl-10 pr-4 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-white/40 backdrop-blur-xl shadow-[inset_0_1px_2px_rgba(255,255,255,0.7)] focus:bg-white/80 focus:border-[#0D3B8E] focus:outline-none focus:ring-4 focus:ring-[#0D3B8E]/15 transition-all duration-200"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center items-center gap-2 py-3 px-4 rounded-2xl bg-gradient-to-r from-[#0D3B8E] to-[#0A2F73] hover:from-[#0B337D] hover:to-[#082459] active:scale-[0.99] text-white text-xs font-bold shadow-lg shadow-[#0D3B8E]/25 hover:shadow-xl hover:shadow-[#0D3B8E]/35 border border-white/30 backdrop-blur-xl transition-all duration-200 cursor-pointer disabled:opacity-60"
                >
                  <Send className="w-3.5 h-3.5" />
                  {loading ? 'Sending Link...' : 'Send Reset Link'}
                </button>

                <div className="pt-2 flex items-center justify-between text-xs border-t border-slate-100/80">
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
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
                className="space-y-4.5"
                onSubmit={handleResetPasswordSubmit}
              >
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Set New Password
                  </h3>
                  <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                    Enter your registered email and choose a new password.
                  </p>
                </div>

                <div>
                  <label htmlFor="reset-email" className="block text-xs font-bold text-slate-700 tracking-wide mb-1.5">
                    Registered Email Address
                  </label>
                  <div className="relative group">
                    <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 transition-colors group-focus-within:text-[#0D3B8E]" />
                    <input
                      id="reset-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-2xl border border-white/60 pl-10 pr-4 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-white/40 backdrop-blur-xl shadow-[inset_0_1px_2px_rgba(255,255,255,0.7)] focus:bg-white/80 focus:border-[#0D3B8E] focus:outline-none focus:ring-4 focus:ring-[#0D3B8E]/15 transition-all duration-200"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="new-password" className="block text-xs font-bold text-slate-700 tracking-wide mb-1.5">
                    New Password
                  </label>
                  <div className="relative group">
                    <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 transition-colors group-focus-within:text-[#0D3B8E]" />
                    <input
                      id="new-password"
                      type={showNewPassword ? "text" : "password"}
                      required
                      minLength={6}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="At least 6 characters"
                      className="block w-full rounded-2xl border border-white/60 pl-10 pr-10 py-2.5 text-xs font-medium text-slate-900 placeholder-slate-400 bg-white/40 backdrop-blur-xl shadow-[inset_0_1px_2px_rgba(255,255,255,0.7)] focus:bg-white/80 focus:border-[#0D3B8E] focus:outline-none focus:ring-4 focus:ring-[#0D3B8E]/15 transition-all duration-200"
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPassword(!showNewPassword)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors cursor-pointer p-1 rounded-lg hover:bg-white/50"
                      title={showNewPassword ? "Hide password" : "Show password"}
                    >
                      {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center items-center gap-2 py-3 px-4 rounded-2xl bg-gradient-to-r from-[#0D3B8E] to-[#0A2F73] hover:from-[#0B337D] hover:to-[#082459] active:scale-[0.99] text-white text-xs font-bold shadow-lg shadow-[#0D3B8E]/25 hover:shadow-xl hover:shadow-[#0D3B8E]/35 border border-white/30 backdrop-blur-xl transition-all duration-200 cursor-pointer disabled:opacity-60"
                >
                  {loading ? 'Resetting Password...' : 'Reset Password & Sign In'}
                </button>

                <div className="pt-2 text-center border-t border-slate-100/80">
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

        {/* Security Glass Badge */}
        <div className="mt-6 text-center text-[11px] text-slate-600 font-medium flex items-center justify-center gap-1.5 backdrop-blur-md py-1.5 px-4 rounded-full bg-white/50 border border-white/70 mx-auto w-fit shadow-xs">
          <ShieldCheck className="w-3.5 h-3.5 text-[#0D3B8E]" />
          <span>Rajasthan State Enterprise Portal • 256-Bit Encrypted</span>
        </div>
      </motion.div>
    </div>
  );
}
