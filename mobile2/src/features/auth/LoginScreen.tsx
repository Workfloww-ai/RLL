import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import {
  RefreshIcon,
  EditIcon,
  CheckCircleIcon,
  ShieldAlertIcon,
  ArrowRightIcon,
} from '../../components/Icons';

import LogoSvg from '../../assets/rll logo.svg';
import { sendMobileOTP, verifyMobileOTP } from '../../lib/api';
import { logger } from '../../lib/logger';

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
  const [phoneFocused, setPhoneFocused] = useState(false);
  const [focusedOtpIndex, setFocusedOtpIndex] = useState<number | null>(null);

  const inputRefs = [
    useRef<any>(null),
    useRef<any>(null),
    useRef<any>(null),
    useRef<any>(null),
    useRef<any>(null),
    useRef<any>(null),
  ];

  // Auto focus first OTP input when step changes to 'otp'
  useEffect(() => {
    if (step === 'otp') {
      setTimeout(() => {
        inputRefs[0].current?.focus();
      }, 100);
    }
  }, [step]);

  const handleSendOTP = async () => {
    if (!phone.trim()) {
      setError('Please enter your Mobile Phone Number');
      return;
    }

    if (phone.trim().length < 10) {
      setError('Please enter a valid 10-digit phone number');
      return;
    }

    setLoading(true);
    setError('');
    setSuccessMessage('');
    logger.info(`LoginScreen: Requesting OTP for phone: ${phone.trim()}`);

    try {
      const res = await sendMobileOTP(phone.trim());
      if (res && res.success) {
        logger.info(`LoginScreen: OTP requested successfully. Advancing to verification step.`);
        setStep('otp');
        setSuccessMessage(`6-digit code sent to +91 ${phone.trim()}`);
      } else {
        logger.warn(`LoginScreen: Server response success false on OTP request: ${res.message}`);
        setError(res.message || 'Failed to send OTP verification code');
      }
    } catch (err: any) {
      logger.error('LoginScreen: Error requesting OTP:', err);
      setError(err.message || 'Failed to send OTP. Please check your phone number.');
    } finally {
      setLoading(false);
    }
  };

  const handleOtpChange = (index: number, value: string) => {
    const digit = value.replace(/\D/g, '');
    const newOtp = [...otpDigits];
    newOtp[index] = digit;
    setOtpDigits(newOtp);

    // Auto-advance to next input field
    if (digit && index < 5) {
      inputRefs[index + 1].current?.focus();
    }
  };

  const handleKeyPress = (index: number, key: string) => {
    if (key === 'Backspace' && !otpDigits[index] && index > 0) {
      inputRefs[index - 1].current?.focus();
    }
  };

  const handleVerifyOTP = async () => {
    const fullOtp = otpDigits.join('');
    if (fullOtp.length !== 6) {
      setError('Please enter the complete 6-digit OTP code');
      return;
    }

    setLoading(true);
    setError('');
    logger.info(`LoginScreen: Submitting OTP verification for phone: ${phone.trim()}`);

    try {
      const res = await verifyMobileOTP(phone.trim(), fullOtp);
      if (res && res.user) {
        logger.info(`LoginScreen: OTP verification successful. User session logged in: ${res.user.email}`);
        onLoginSuccess(res.user);
      } else {
        logger.warn('LoginScreen: Verification response does not contain user profile details.');
        setError('Invalid OTP verification code. Please try again.');
      }
    } catch (err: any) {
      logger.error('LoginScreen: Exception during OTP verification:', err);
      setError(err.message || 'Verification failed. Invalid or expired OTP.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      style={styles.keyboardContainer}
    >
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.container}>
          {/* Header Branding */}
          <View style={styles.brandingHeader}>
            <LogoSvg width={76} height={76} style={styles.logoImage} />
            <Text style={styles.titleText}>LucidX360</Text>
            <Text style={styles.subtitleText}>RAJASTHAN LIQUOR LIMITED</Text>
          </View>

          {/* Minimalist Card Box */}
          <View style={styles.cardBox}>
            {/* STEP 1: Phone Input */}
            {step === 'credentials' && (
              <View style={styles.stepBlock}>
                <Text style={styles.stepTitle}>Sign In</Text>
                <Text style={styles.stepSubtitle}>Enter your registered mobile number</Text>

                {error ? (
                  <View style={styles.errorBanner}>
                    <ShieldAlertIcon size={15} color="#DC2626" />
                    <Text style={styles.errorText}>{error}</Text>
                  </View>
                ) : null}

                <View style={styles.inputGroup}>
                  <Text style={styles.label}>MOBILE NUMBER</Text>
                  <View
                    style={[
                      styles.inputWrapper,
                      phoneFocused ? styles.inputWrapperFocused : null,
                    ]}
                  >
                    <View style={styles.prefixPill}>
                      <Text style={styles.prefixText}>+91</Text>
                    </View>
                    <TextInput
                      style={styles.textInput}
                      placeholder="98765 43210"
                      placeholderTextColor="#94A3B8"
                      keyboardType="phone-pad"
                      maxLength={10}
                      value={phone}
                      onChangeText={setPhone}
                      onFocus={() => setPhoneFocused(true)}
                      onBlur={() => setPhoneFocused(false)}
                    />
                  </View>
                </View>

                <TouchableOpacity
                  style={[
                    styles.submitButton,
                    (!phone.trim() || phone.trim().length < 10) ? styles.submitButtonDisabled : null,
                  ]}
                  onPress={handleSendOTP}
                  disabled={loading || !phone.trim() || phone.trim().length < 10}
                  activeOpacity={0.8}
                >
                  {loading ? (
                    <ActivityIndicator color="#FFFFFF" size="small" />
                  ) : (
                    <View style={styles.buttonInner}>
                      <Text style={styles.buttonText}>Get OTP</Text>
                      <ArrowRightIcon color="#FFFFFF" size={14} />
                    </View>
                  )}
                </TouchableOpacity>
              </View>
            )}

            {/* STEP 2: OTP Input (Non-Redundant Modern UI) */}
            {step === 'otp' && (
              <View style={styles.stepBlock}>
                <Text style={styles.stepTitle}>Verification Code</Text>
                
                {/* Single Combined Phone Line with Inline Edit */}
                <View style={styles.phoneLineRow}>
                  <Text style={styles.phoneLineText}>Sent to +91 {phone}</Text>
                  <TouchableOpacity
                    onPress={() => {
                      setStep('credentials');
                      setOtpDigits(['', '', '', '', '', '']);
                      setError('');
                      setSuccessMessage('');
                    }}
                    style={styles.inlineEditBtn}
                    activeOpacity={0.7}
                  >
                    <EditIcon size={12} color="#0D3B8E" />
                    <Text style={styles.inlineEditText}>Edit</Text>
                  </TouchableOpacity>
                </View>

                {error ? (
                  <View style={styles.errorBanner}>
                    <ShieldAlertIcon size={15} color="#DC2626" />
                    <Text style={styles.errorText}>{error}</Text>
                  </View>
                ) : null}

                {/* 6-Digit OTP Box Grid */}
                <View style={styles.otpGrid}>
                  {otpDigits.map((digit, index) => {
                    const isFocused = focusedOtpIndex === index;
                    const isFilled = Boolean(digit);
                    return (
                      <TextInput
                        key={index}
                        ref={inputRefs[index]}
                        style={[
                          styles.otpBox,
                          isFilled ? styles.otpBoxFilled : null,
                          isFocused ? styles.otpBoxFocused : null,
                        ]}
                        keyboardType="numeric"
                        maxLength={1}
                        value={digit}
                        onChangeText={(val) => handleOtpChange(index, val)}
                        onKeyPress={({ nativeEvent }) => handleKeyPress(index, nativeEvent.key)}
                        onFocus={() => setFocusedOtpIndex(index)}
                        onBlur={() => setFocusedOtpIndex(null)}
                      />
                    );
                  })}
                </View>

                <TouchableOpacity
                  style={[
                    styles.submitButton,
                    otpDigits.join('').length !== 6 ? styles.submitButtonDisabled : null,
                  ]}
                  onPress={handleVerifyOTP}
                  disabled={loading || otpDigits.join('').length !== 6}
                  activeOpacity={0.8}
                >
                  {loading ? (
                    <ActivityIndicator color="#FFFFFF" size="small" />
                  ) : (
                    <View style={styles.buttonInner}>
                      <Text style={styles.buttonText}>Verify OTP</Text>
                      <ArrowRightIcon color="#FFFFFF" size={14} />
                    </View>
                  )}
                </TouchableOpacity>

                {/* Streamlined Resend Button */}
                <TouchableOpacity
                  onPress={handleSendOTP}
                  disabled={loading}
                  style={styles.resendLinkBtn}
                  activeOpacity={0.7}
                >
                  <RefreshIcon color="#0D3B8E" size={12} />
                  <Text style={styles.resendLinkText}>Resend Code</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>

          {/* Minimalist Footer */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>Powered by Workfloww.ai</Text>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  keyboardContainer: {
    flex: 1,
    backgroundColor: '#FAFAFA',
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'space-between',
  },
  container: {
    flex: 1,
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingTop: Platform.OS === 'ios' ? 60 : 40,
    paddingBottom: 24,
  },
  brandingHeader: {
    alignItems: 'center',
    marginTop: 12,
    marginBottom: 8,
  },
  logoImage: {
    marginBottom: 12,
  },
  titleText: {
    fontSize: 26,
    fontWeight: '800',
    color: '#0D3B8E',
    letterSpacing: -0.3,
  },
  subtitleText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#64748B',
    letterSpacing: 2,
    marginTop: 4,
    textAlign: 'center',
  },
  cardBox: {
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 24,
    marginVertical: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.03,
    shadowRadius: 12,
  },
  stepBlock: {
    width: '100%',
  },
  stepTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#0F172A',
  },
  stepSubtitle: {
    fontSize: 13,
    color: '#64748B',
    marginTop: 4,
    marginBottom: 20,
  },
  phoneLineRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
    marginBottom: 20,
  },
  phoneLineText: {
    fontSize: 13,
    color: '#64748B',
  },
  inlineEditBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    backgroundColor: '#F0F4FF',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  inlineEditText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#0D3B8E',
  },
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#FEF2F2',
    borderColor: '#FCA5A5',
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 16,
  },
  errorText: {
    color: '#DC2626',
    fontSize: 12,
    fontWeight: '500',
    flex: 1,
  },
  inputGroup: {
    marginBottom: 20,
  },
  label: {
    fontSize: 11,
    fontWeight: '700',
    color: '#64748B',
    letterSpacing: 0.8,
    marginBottom: 8,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 12,
    paddingHorizontal: 12,
    height: 48,
  },
  inputWrapperFocused: {
    borderColor: '#0D3B8E',
    backgroundColor: '#FFFFFF',
  },
  prefixPill: {
    paddingRight: 8,
    borderRightWidth: 1,
    borderRightColor: '#CBD5E1',
    marginRight: 10,
  },
  prefixText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#0D3B8E',
  },
  textInput: {
    flex: 1,
    color: '#0F172A',
    fontSize: 16,
    fontWeight: '600',
    height: '100%',
    paddingVertical: 0,
  },
  submitButton: {
    backgroundColor: '#0D3B8E',
    borderRadius: 12,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submitButtonDisabled: {
    opacity: 0.5,
  },
  buttonInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  otpGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 20,
  },
  otpBox: {
    width: 42,
    height: 48,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 10,
    backgroundColor: '#F8FAFC',
    color: '#0F172A',
    fontSize: 18,
    fontWeight: '800',
    textAlign: 'center',
  },
  otpBoxFilled: {
    borderColor: '#0D3B8E',
    backgroundColor: '#F0F4FF',
    color: '#0D3B8E',
  },
  otpBoxFocused: {
    borderColor: '#0D3B8E',
    backgroundColor: '#FFFFFF',
  },
  resendLinkBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    marginTop: 16,
    paddingVertical: 4,
  },
  resendLinkText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0D3B8E',
  },
  footer: {
    alignItems: 'center',
    marginTop: 8,
  },
  footerText: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '500',
  },
});
