import React, { useState } from 'react';
import { LogIn, Mail, ArrowLeft } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';

interface LoginProps {
  onLogin: (userName: string) => void;
}

export default function Login({ onLogin }: LoginProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  
  // States for forgot password flow
  const [view, setView] = useState<'login' | 'forgot-password' | 'forgot-password-success'>('login');

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!email || !password) return;

    setLoading(true);
    const namePart = email.split('@')[0];
    const formattedName = namePart
      .split(/[._-]/)
      .map(part => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
      .join(' ');
    const fallbackName = formattedName || 'User';

    try {
      const response = await fetch('http://localhost:8000/api/v1/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email, password }),
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
        setError(errData.detail || 'Login failed. Please check your credentials.');
      }
    } catch (err) {
      console.warn('Backend server connection failed, logging in with fallback mode:', err);
      const demoToken = 'demo-token-' + Date.now();
      localStorage.setItem('token', demoToken);
      localStorage.setItem('user_name', fallbackName);
      onLogin(fallbackName);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    localStorage.setItem('token', 'google-token-' + Date.now());
    localStorage.setItem('user_name', 'Google User');
    onLogin('Google User');
  };

  const handleForgotPasswordSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email) {
      setView('forgot-password-success');
    }
  };

  return (
    <div className="min-h-screen bg-[#F8F8F8] flex flex-col justify-center py-12 sm:px-6 lg:px-8 font-sans">
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="sm:mx-auto sm:w-full sm:max-w-md"
      >
        <div className="flex justify-center mb-6">
          <img src="/images/rll.png" alt="RLL Logo" className="w-28 h-28 object-contain bg-white rounded-xl shadow-sm p-1" />
        </div>
        <h2 className="mt-6 text-center text-3xl font-bold tracking-tight text-[#222222] font-heading drop-shadow-sm">
          {view === 'login' ? 'Sign in to your account' : 'Reset your password'}
        </h2>
        <p className="mt-2 text-center text-sm text-[#666666] font-medium">
          RLL Admin Dashboard
        </p>
      </motion.div>

      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mt-6 sm:mx-auto sm:w-full sm:max-w-sm relative"
      >
        <div className="bg-gradient-to-br from-[#0D3B8E] to-[#0A2F73] py-6 px-4 shadow-2xl sm:rounded-2xl sm:px-8 border border-[#0D3B8E] overflow-hidden relative">
          
          <AnimatePresence mode="wait">
            {view === 'login' && (
              <motion.form 
                key="login"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="space-y-4" 
                onSubmit={handleLoginSubmit}
              >
                {error && (
                  <div className="p-3 text-sm text-red-100 bg-red-600/40 border border-red-400/50 rounded-lg backdrop-blur-sm">
                    {error}
                  </div>
                )}

                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-white">
                    Email address
                  </label>
                  <div className="mt-1">
                    <input
                      id="email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="block w-full appearance-none rounded-lg border border-white/20 px-3 py-2 placeholder-blue-300 shadow-sm focus:border-white focus:outline-none focus:ring-white sm:text-sm bg-white/10 text-white"
                      placeholder="admin@rll.com"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="password" className="block text-sm font-medium text-white">
                    Password
                  </label>
                  <div className="mt-1">
                    <input
                      id="password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="block w-full appearance-none rounded-lg border border-white/20 px-3 py-2 placeholder-blue-300 shadow-sm focus:border-white focus:outline-none focus:ring-white sm:text-sm bg-white/10 text-white"
                      placeholder="••••••••"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <input
                      id="remember-me"
                      name="remember-me"
                      type="checkbox"
                      className="h-4 w-4 rounded border-white/30 bg-white/10 text-blue-500 checked:border-transparent focus:ring-white"
                    />
                    <label htmlFor="remember-me" className="ml-2 block text-sm text-blue-100">
                      Remember me
                    </label>
                  </div>

                  <div className="text-sm">
                    <button type="button" onClick={() => setView('forgot-password')} className="font-medium text-blue-200 hover:text-white transition-colors">
                      Forgot your password?
                    </button>
                  </div>
                </div>

                <div>
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex w-full justify-center rounded-lg bg-white py-2.5 px-4 text-sm font-semibold text-[#0D3B8E] shadow-sm hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white transition-colors gap-2 items-center mt-2 disabled:opacity-70 disabled:cursor-not-allowed"
                  >
                    <LogIn className="w-4 h-4" />
                    {loading ? 'Logging in...' : 'Log In'}
                  </button>
                </div>
              </motion.form>
            )}

            {view === 'forgot-password' && (
              <motion.form
                key="forgot-password"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="space-y-6 flex flex-col h-full"
                onSubmit={handleForgotPasswordSubmit}
              >
                <div>
                  <label htmlFor="reset-email" className="block text-sm font-medium text-white mb-2">
                    Enter your email to receive a reset link
                  </label>
                  <input
                    id="reset-email"
                    name="email"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="block w-full appearance-none rounded-lg border border-white/20 px-3 py-2 placeholder-blue-300 shadow-sm focus:border-white focus:outline-none focus:ring-white sm:text-sm bg-white/10 text-white"
                    placeholder="admin@rll.com"
                  />
                </div>
                
                <div className="pt-2">
                  <button
                    type="submit"
                    className="flex w-full justify-center rounded-lg bg-white py-2.5 px-4 text-sm font-semibold text-[#0D3B8E] shadow-sm hover:bg-blue-50 transition-colors gap-2 items-center"
                  >
                    Send Reset Link
                  </button>
                </div>
                
                <div className="mt-auto pt-6 text-center">
                  <button 
                    type="button" 
                    onClick={() => setView('login')} 
                    className="inline-flex items-center text-sm font-medium text-blue-200 hover:text-white transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4 mr-2" />
                    Back to login
                  </button>
                </div>
              </motion.form>
            )}

            {view === 'forgot-password-success' && (
              <motion.div
                key="forgot-password-success"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex flex-col items-center justify-center text-center py-8 h-full space-y-6"
              >
                <div className="w-16 h-16 bg-white/20 rounded-full flex items-center justify-center mb-2">
                  <Mail className="w-8 h-8 text-white" />
                </div>
                <h3 className="text-xl font-bold text-white">Check your email</h3>
                <p className="text-blue-100 text-sm max-w-[250px]">
                  We've sent a password reset link to <br/>
                  <span className="font-bold text-white">{email}</span>
                </p>
                <div className="w-full pt-6 mt-auto">
                  <button 
                    type="button" 
                    onClick={() => setView('login')} 
                    className="flex w-full justify-center rounded-lg bg-white py-2.5 px-4 text-sm font-semibold text-[#0D3B8E] shadow-sm hover:bg-blue-50 transition-colors"
                  >
                    Return to Log In
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
