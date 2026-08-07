import React, { useState } from 'react';
import { Lock, Mail, ShieldCheck, ArrowRight } from 'lucide-react';
import { loginMobileUser } from '../lib/api';

interface LoginScreenProps {
  onLoginSuccess: (user: any) => void;
}

export function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please enter your email and password');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await loginMobileUser(email, password);
      if (res && res.user) {
        onLoginSuccess(res.user);
      } else {
        setError('Invalid credentials');
      }
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 bg-[#0F2042] text-white flex flex-col justify-between p-6 overflow-y-auto">
      {/* Top Branding Section */}
      <div className="mt-4 text-center space-y-2">
        <div className="w-14 h-14 bg-white/10 rounded-2xl flex items-center justify-center mx-auto border border-white/20 shadow-lg backdrop-blur-xs">
          <ShieldCheck className="w-7 h-7 text-amber-400" />
        </div>
        <div>
          <h1 className="text-lg font-black tracking-tight text-white">RLL Mobile Analytics</h1>
          <p className="text-[11px] text-slate-300 mt-0.5">Rajasthan Liquor Limited Executive Portal</p>
        </div>
      </div>

      {/* Login / Sign Up Form */}
      <form onSubmit={handleSubmit} className="space-y-3.5 bg-white/5 border border-white/10 p-5 rounded-2xl backdrop-blur-md my-auto">
        <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-1">
          <h2 className="text-xs font-bold text-white uppercase tracking-wider">
            {isSignUp ? 'Create Executive Account' : 'Sign In to Portal'}
          </h2>
        </div>

        {error && (
          <div className="bg-red-500/20 border border-red-500/40 text-red-200 text-xs p-2.5 rounded-xl text-center">
            {error}
          </div>
        )}

        {isSignUp && (
          <div>
            <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1">
              Full Name
            </label>
            <input
              type="text"
              placeholder="Full Name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              className="w-full bg-slate-900/60 border border-slate-700/80 rounded-xl px-3 py-2 text-xs font-medium text-white placeholder-slate-500 focus:outline-none focus:border-amber-400 transition-all"
            />
          </div>
        )}

        <div>
          <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1">
            Email Address
          </label>
          <div className="relative">
            <Mail className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="email"
              placeholder="user@rll.gov.in"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-slate-900/60 border border-slate-700/80 rounded-xl pl-9 pr-3 py-2 text-xs font-medium text-white placeholder-slate-500 focus:outline-none focus:border-amber-400 transition-all"
            />
          </div>
        </div>

        <div>
          <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1">
            Password
          </label>
          <div className="relative">
            <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-slate-900/60 border border-slate-700/80 rounded-xl pl-9 pr-3 py-2 text-xs font-medium text-white placeholder-slate-500 focus:outline-none focus:border-amber-400 transition-all"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 shadow-md hover:shadow-lg transition-all disabled:opacity-50 mt-2 cursor-pointer"
        >
          {loading ? 'Processing...' : (isSignUp ? 'Create Account & Sign In' : 'Sign In to Dashboard')}
          {!loading && <ArrowRight className="w-4 h-4" />}
        </button>

        <div className="text-center pt-2 border-t border-white/10">
          <button
            type="button"
            onClick={() => setIsSignUp(!isSignUp)}
            className="text-[11px] text-amber-300 hover:text-amber-200 font-semibold cursor-pointer underline underline-offset-2"
          >
            {isSignUp ? 'Already have an account? Sign In' : "Don't have an account? Create one"}
          </button>
        </div>
      </form>

      {/* Footer Info */}
      <div className="text-center text-[10px] text-slate-400 space-y-0.5 mb-1">
        <p>Secured with Supabase Audit Logging</p>
        <p className="text-slate-500">v1.0 Enterprise Mobile Release</p>
      </div>
    </div>
  );
}
