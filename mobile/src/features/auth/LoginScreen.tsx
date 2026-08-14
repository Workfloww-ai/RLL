import React, { useState, useRef, useEffect } from 'react';
import { Phone, ShieldCheck, ArrowRight, KeyRound, RefreshCw, Edit2, CheckCircle2 } from 'lucide-react';
import { sendMobileOTP, verifyMobileOTP } from '../../lib/api';

interface LoginScreenProps {
  onLoginSuccess: (user: any) => void;
}

export function LoginScreen({ onLoginSuccess }: LoginScreenProps) {
  const [step, setStep] = useState<'credentials' | 'otp'>('credentials');
  const [phone, setPhone] = useState('');
  const [otpDigits, setOtpDigits] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const inputRefs = [
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
    useRef<HTMLInputElement>(null),
  ];

  // Auto focus first OTP input when step changes to 'otp'
  useEffect(() => {
    if (step === 'otp') {
      setTimeout(() => {
        inputRefs[0].current?.focus();
      }, 100);
    }
  }, [step]);

  const handleSendOTP = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!phone.trim()) {
      setError('Please enter your Mobile Phone Number');
      return;
    }

    setLoading(true);
    setError('');
    setSuccessMessage('');

    try {
      const res = await sendMobileOTP(phone.trim());
      if (res && res.success) {
        setStep('otp');
        setSuccessMessage(`6-digit OTP sent to ${phone.trim()}`);
      } else {
        setError(res.message || 'Failed to send OTP verification code');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to send OTP code. Please check your phone number.');
    } finally {
      setLoading(false);
    }
  };

  const handleOtpChange = (index: number, value: string) => {
    if (value.length > 1) {
      // Handle paste of 6 digits
      const digits = value.replace(/\D/g, '').slice(0, 6).split('');
      const newOtp = [...otpDigits];
      digits.forEach((d, i) => {
        if (i < 6) newOtp[i] = d;
      });
      setOtpDigits(newOtp);
      const nextIndex = Math.min(digits.length, 5);
      inputRefs[nextIndex].current?.focus();
      return;
    }

    const digit = value.replace(/\D/g, '');
    const newOtp = [...otpDigits];
    newOtp[index] = digit;
    setOtpDigits(newOtp);

    // Auto-advance to next input field
    if (digit && index < 5) {
      inputRefs[index + 1].current?.focus();
    }
  };

  const handleKeyDown = (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace' && !otpDigits[index] && index > 0) {
      inputRefs[index - 1].current?.focus();
    }
  };

  const handleVerifyOTP = async (e: React.FormEvent) => {
    e.preventDefault();
    const fullOtp = otpDigits.join('');
    if (fullOtp.length !== 6) {
      setError('Please enter the complete 6-digit OTP code');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const res = await verifyMobileOTP(phone.trim(), fullOtp);
      if (res && res.user) {
        onLoginSuccess(res.user);
      } else {
        setError('Invalid OTP verification code');
      }
    } catch (err: any) {
      setError(err.message || 'Verification failed. Invalid or expired OTP.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 bg-[#0F2042] text-white flex flex-col justify-between p-6 overflow-y-auto">
      {/* Top Branding Header */}
      <div className="mt-4 text-center space-y-2">
        <div className="w-14 h-14 bg-white/10 rounded-2xl flex items-center justify-center mx-auto border border-white/20 shadow-lg backdrop-blur-xs">
          <ShieldCheck className="w-7 h-7 text-amber-400" />
        </div>
        <div>
          <h1 className="text-lg font-black tracking-tight text-white">RLL Mobile Analytics</h1>
          <p className="text-[11px] text-slate-300 mt-0.5">Rajasthan Liquor Limited Executive Portal</p>
        </div>
      </div>

      {/* STEP 1: Phone Input Form */}
      {step === 'credentials' && (
        <form onSubmit={handleSendOTP} className="space-y-3.5 bg-white/5 border border-white/10 p-5 rounded-2xl backdrop-blur-md my-auto">
          <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-1">
            <h2 className="text-xs font-bold text-white uppercase tracking-wider">
              Executive Sign In
            </h2>
            <span className="text-[10px] text-amber-400 font-semibold">SMS OTP Auth</span>
          </div>

          {error && (
            <div className="bg-red-500/20 border border-red-500/40 text-red-200 text-xs p-2.5 rounded-xl text-center font-medium">
              {error}
            </div>
          )}

          <div>
            <label className="block text-[11px] font-bold text-slate-300 uppercase tracking-wider mb-1">
              Mobile Phone Number
            </label>
            <div className="relative">
              <Phone className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="tel"
                placeholder="+91 9829141481"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                required
                className="w-full bg-slate-900/60 border border-slate-700/80 rounded-xl pl-9 pr-3 py-2 text-xs font-medium text-white placeholder-slate-500 focus:outline-none focus:border-amber-400 transition-all"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 shadow-md hover:shadow-lg transition-all disabled:opacity-50 mt-2 cursor-pointer"
          >
            {loading ? 'Sending OTP via Dovesoft...' : 'Send 6-Digit OTP Code'}
            {!loading && <ArrowRight className="w-4 h-4" />}
          </button>
        </form>
      )}

      {/* STEP 2: 6-Digit OTP Verification Form */}
      {step === 'otp' && (
        <form onSubmit={handleVerifyOTP} className="space-y-4 bg-white/5 border border-white/10 p-5 rounded-2xl backdrop-blur-md my-auto text-center">
          <div className="space-y-1">
            <div className="w-10 h-10 bg-amber-400/20 border border-amber-400/40 rounded-full flex items-center justify-center mx-auto mb-2 text-amber-300">
              <KeyRound className="w-5 h-5" />
            </div>
            <h2 className="text-sm font-extrabold text-white tracking-tight">
              Enter 6-Digit Verification Code
            </h2>
            <p className="text-[11px] text-slate-300">
              OTP sent via Dovesoft SMS to <span className="font-bold text-amber-300">{phone}</span>
            </p>
            <p className="text-[10px] text-emerald-400 font-semibold flex items-center justify-center gap-1 mt-0.5">
              <CheckCircle2 className="w-3 h-3" /> Valid for 5 minutes
            </p>
          </div>

          {error && (
            <div className="bg-red-500/20 border border-red-500/40 text-red-200 text-xs p-2.5 rounded-xl text-center font-medium">
              {error}
            </div>
          )}

          {/* 6-Digit Input Box Grid */}
          <div className="flex items-center justify-center gap-1.5 py-2">
            {otpDigits.map((digit, index) => (
              <input
                key={index}
                ref={inputRefs[index]}
                type="text"
                inputMode="numeric"
                maxLength={1}
                value={digit}
                onChange={(e) => handleOtpChange(index, e.target.value)}
                onKeyDown={(e) => handleKeyDown(index, e)}
                className="w-10 h-11 text-center text-base font-black text-amber-400 bg-slate-900/80 border-2 border-slate-700/80 rounded-xl focus:outline-none focus:border-amber-400 transition-all shadow-inner"
              />
            ))}
          </div>

          <button
            type="submit"
            disabled={loading || otpDigits.join('').length !== 6}
            className="w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold py-2.5 rounded-xl text-xs flex items-center justify-center gap-2 shadow-md hover:shadow-lg transition-all disabled:opacity-50 cursor-pointer"
          >
            {loading ? 'Verifying OTP...' : 'Verify OTP & Sign In'}
            {!loading && <ArrowRight className="w-4 h-4" />}
          </button>

          <div className="flex items-center justify-between text-[11px] pt-2 border-t border-white/10 text-slate-300">
            <button
              type="button"
              onClick={() => handleSendOTP()}
              className="hover:text-amber-300 font-semibold flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className="w-3 h-3" /> Resend OTP
            </button>
            <button
              type="button"
              onClick={() => {
                setStep('credentials');
                setOtpDigits(['', '', '', '', '', '']);
                setError('');
              }}
              className="hover:text-amber-300 font-semibold flex items-center gap-1 cursor-pointer"
            >
              <Edit2 className="w-3 h-3" /> Edit Phone Number
            </button>
          </div>
        </form>
      )}

      {/* Footer Info */}
      <div className="text-center text-[10px] text-slate-400 space-y-0.5 mb-1">
        <p>Secured with Dovesoft SMS & Supabase OTP Logging</p>
        <p className="text-slate-500">v1.0 Enterprise Mobile Release</p>
      </div>
    </div>
  );
}
