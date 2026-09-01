import React, { useState, useEffect } from 'react';
import { LogIn, Mail, ArrowLeft, CheckCircle2, Lock, Send, KeyRound } from 'lucide-react';
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

  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Auto-detect password recovery link from email hash or parameters
  useEffect(() => {
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
    if (!email.trim() || !password) return;

    setLoading(true);
    const namePart = email.split('@')[0];
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
        body: JSON.stringify({ email: email.trim(), password }),
      });

      if (response.ok) {
        const data = await response.json();
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
    <div className="min-h-screen bg-#F8F8F8 flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans">
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="sm:mx-auto sm:w-full sm:max-w-md"
      >
        <div className="flex justify-center mb-4">
          <img src="/images/rll.png" alt="RLL Logo" className="w-24 h-24 object-contain bg-white rounded-xl shadow-sm p-1" />
        </div>
        <h2 className="mt-4 text-center text-2xl font-black tracking-tight text-#222222 drop-shadow-sm">
          RLL Admin Dashboard
        </h2>
        <p className="mt-1 text-center text-xs text-#666666 font-medium">
          Rajasthan Liquor Limited Executive Portal
        </p>
      </motion.div>

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mt-5 sm:mx-auto sm:w-full sm:max-w-md relative px-4 sm:px-0"
      >
        <div className="bg-linear-to-br from-#0D3B8E to-#0A2F73 py-6 px-4 shadow-2xl rounded-2xl sm:px-8 border border-#0D3B8E overflow-hidden relative">
          
          {error && (
            <div className="mb-4 p-3 text-xs text-red-100 bg-red-600/40 border border-red-400/50 rounded-xl backdrop-blur-sm font-medium leading-relaxed">
              {error}
            </div>
          )}

          {successMessage && (
            <div className="mb-4 p-3 text-xs text-emerald-100 bg-emerald-600/30 border border-emerald-400/40 rounded-xl backdrop-blur-sm font-medium flex items-center gap-1.5 leading-relaxed">
              <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-300" />
              {successMessage}
            </div>
          )}

          <AnimatePresence mode="wait">
            {/* VIEW 1: LOGIN FORM (EMAIL + PASSWORD) */}
            {view === 'login' && (
              <motion.form 
                key="login"
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -10 }}
                className="space-y-4" 
                onSubmit={handleLoginSubmit}
              >
                <div className="border-b border-white/15 pb-2 mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                    Admin Sign In
                  </h3>
                  <span className="text-[10px] text-amber-400 font-semibold flex items-center gap-1">
                    <Lock className="w-3 h-3" /> Protected Portal
                  </span>
                </div>

                <div>
                  <label htmlFor="email" className="block text-xs font-bold text-blue-100 uppercase tracking-wider mb-1">
                    Email Address
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-blue-300 absolute left-3 top-2.5" />
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-xl border border-white/20 pl-9 pr-3 py-2 text-xs font-medium placeholder-blue-300/60 shadow-sm focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400 bg-black/20 text-white"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="password" className="block text-xs font-bold text-blue-100 uppercase tracking-wider mb-1">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-blue-300 absolute left-3 top-2.5" />
                    <input
                      id="password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="block w-full rounded-xl border border-white/20 pl-9 pr-3 py-2 text-xs font-medium placeholder-blue-300/60 shadow-sm focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400 bg-black/20 text-white"
                      placeholder="••••••••"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between text-xs pt-1">
                  <div className="flex items-center">
                    <input
                      id="remember-me"
                      name="remember-me"
                      type="checkbox"
                      className="h-3.5 w-3.5 rounded border-white/30 bg-white/10 text-blue-500 focus:ring-white"
                    />
                    <label htmlFor="remember-me" className="ml-2 text-[11px] text-blue-100">
                      Remember me
                    </label>
                  </div>

                  <button 
                    type="button" 
                    onClick={() => { setView('forgot-password'); setError(null); setSuccessMessage(null); }} 
                    className="text-[11px] font-semibold text-amber-400 hover:text-amber-300 transition-colors cursor-pointer"
                  >
                    Forgot your password?
                  </button>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="flex w-full justify-center rounded-xl bg-white py-2.5 px-4 text-xs font-extrabold text-#0D3B8E shadow-md hover:bg-blue-50 transition-colors gap-2 items-center mt-3 disabled:opacity-70 cursor-pointer"
                >
                  <LogIn className="w-4 h-4" />
                  {loading ? 'Authenticating Admin...' : 'Sign In'}
                </button>
              </motion.form>
            )}

            {/* VIEW 2: REQUEST PASSWORD RESET LINK VIA EMAIL */}
            {view === 'forgot-password' && (
              <motion.form
                key="forgot-password"
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                className="space-y-4"
                onSubmit={handleSendResetLinkSubmit}
              >
                <div className="border-b border-white/15 pb-2 mb-2">
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                    Send Password Reset Link
                  </h3>
                  <p className="text-[11px] text-blue-200 mt-0.5">
                    Enter your registered email to receive a password recovery link.
                  </p>
                </div>

                <div>
                  <label htmlFor="reset-email" className="block text-xs font-bold text-blue-100 uppercase tracking-wider mb-1">
                    Registered Email Address
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-blue-300 absolute left-3 top-2.5" />
                    <input
                      id="reset-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-xl border border-white/20 pl-9 pr-3 py-2 text-xs font-medium placeholder-blue-300/60 shadow-sm focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400 bg-black/20 text-white"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="flex w-full justify-center rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold py-2.5 px-4 text-xs shadow-md transition-colors gap-2 items-center cursor-pointer"
                >
                  <Send className="w-3.5 h-3.5" />
                  {loading ? 'Sending Reset Link...' : 'Send Password Reset Link'}
                </button>

                <div className="pt-2 flex items-center justify-between text-xs">
                  <button 
                    type="button" 
                    onClick={() => { setView('login'); setError(null); }} 
                    className="inline-flex items-center text-xs font-semibold text-blue-200 hover:text-white transition-colors cursor-pointer"
                  >
                    <ArrowLeft className="w-3.5 h-3.5 mr-1" />
                    Back to Sign In
                  </button>

                  <button 
                    type="button" 
                    onClick={() => { setView('reset-password'); setError(null); }} 
                    className="text-[11px] font-semibold text-amber-400 hover:text-amber-300 transition-colors cursor-pointer flex items-center gap-1"
                  >
                    <KeyRound className="w-3 h-3" />
                    Set New Password
                  </button>
                </div>
              </motion.form>
            )}

            {/* VIEW 3: RESET PASSWORD FORM */}
            {view === 'reset-password' && (
              <motion.form
                key="reset-password"
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                className="space-y-4"
                onSubmit={handleResetPasswordSubmit}
              >
                <div className="border-b border-white/15 pb-2 mb-2">
                  <h3 className="text-xs font-bold text-white uppercase tracking-wider">
                    Reset Account Password
                  </h3>
                  <p className="text-[11px] text-blue-200 mt-0.5">
                    Enter your registered email and your new password to reset.
                  </p>
                </div>

                <div>
                  <label htmlFor="reset-email" className="block text-xs font-bold text-blue-100 uppercase tracking-wider mb-1">
                    Registered Email Address
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-blue-300 absolute left-3 top-2.5" />
                    <input
                      id="reset-email"
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full rounded-xl border border-white/20 pl-9 pr-3 py-2 text-xs font-medium placeholder-blue-300/60 shadow-sm focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400 bg-black/20 text-white"
                      placeholder="admin@rll.gov.in"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="new-password" className="block text-xs font-bold text-blue-100 uppercase tracking-wider mb-1">
                    New Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-blue-300 absolute left-3 top-2.5" />
                    <input
                      id="new-password"
                      type="password"
                      required
                      minLength={6}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="Enter new password (min 6 chars)"
                      className="block w-full rounded-xl border border-white/20 pl-9 pr-3 py-2 text-xs font-medium placeholder-blue-300/60 shadow-sm focus:border-amber-400 focus:outline-none focus:ring-1 focus:ring-amber-400 bg-black/20 text-white"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="flex w-full justify-center rounded-xl bg-amber-400 hover:bg-amber-300 text-slate-950 font-bold py-2.5 px-4 text-xs shadow-md transition-colors gap-2 items-center cursor-pointer mt-2"
                >
                  {loading ? 'Resetting Password...' : 'Reset Password & Return to Sign In'}
                </button>

                <div className="pt-2 text-center">
                  <button 
                    type="button" 
                    onClick={() => { setView('login'); setError(null); }} 
                    className="inline-flex items-center text-xs font-semibold text-blue-200 hover:text-white transition-colors cursor-pointer"
                  >
                    <ArrowLeft className="w-3.5 h-3.5 mr-1" />
                    Back to Sign In
                  </button>
                </div>
              </motion.form>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}




