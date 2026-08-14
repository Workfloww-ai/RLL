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
  KeyIcon,
  RefreshIcon,
  EditIcon,
  CheckCircleIcon,
  ArrowRightIcon,
} from '../../components/Icons';

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

    setLoading(true);
    setError('');
    setSuccessMessage('');
    logger.info(`LoginScreen: Requesting OTP for phone: ${phone.trim()}`);

    try {
      const res = await sendMobileOTP(phone.trim());
      if (res && res.success) {
        logger.info(`LoginScreen: OTP requested successfully. Advancing to verification step.`);
        setStep('otp');
        setSuccessMessage(`6-digit OTP sent to ${phone.trim()}`);
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
        setError('Invalid OTP verification code');
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
      >
        <View style={styles.container}>
          {/* Top Branding Header */}
          <View style={styles.brandingHeader}>
            <View style={styles.logoBadge}>
              <Text style={styles.logoText}>🛡️</Text>
            </View>
            <Text style={styles.titleText}>RLL Mobile Analytics</Text>
            <Text style={styles.subtitleText}>Rajasthan Liquor Limited Executive Portal</Text>
          </View>

          {/* STEP 1: Phone Input Form */}
          {step === 'credentials' && (
            <View style={styles.formCard}>
              <View style={styles.formHeader}>
                <Text style={styles.formTitle}>Executive Sign In</Text>
                <Text style={styles.formBadge}>SMS OTP Auth</Text>
              </View>

              {error ? (
                <View style={styles.errorBanner}>
                  <Text style={styles.errorText}>{error}</Text>
                </View>
              ) : null}

              <View style={styles.inputGroup}>
                <Text style={styles.label}>Mobile Phone Number</Text>
                <View style={styles.inputWrapper}>
                  <Text style={styles.inputIcon}>📞</Text>
                  <TextInput
                    style={styles.textInput}
                    placeholder="+91 98291 41481"
                    placeholderTextColor="#64748B"
                    keyboardType="phone-pad"
                    value={phone}
                    onChangeText={setPhone}
                  />
                </View>
              </View>

              <TouchableOpacity
                style={styles.button}
                onPress={handleSendOTP}
                disabled={loading}
              >
                {loading ? (
                  <ActivityIndicator color="#0F2042" size="small" />
                ) : (
                  <View style={styles.buttonInner}>
                    <Text style={styles.buttonText}>Send 6-Digit OTP Code</Text>
                    <ArrowRightIcon color="#0F2042" size={14} />
                  </View>
                )}
              </TouchableOpacity>
            </View>
          )}

          {/* STEP 2: 6-Digit OTP Verification Form */}
          {step === 'otp' && (
            <View style={styles.formCard}>
              <View style={styles.otpHeader}>
                <View style={styles.otpIconCircle}>
                  <KeyIcon color="#F59E0B" size={24} />
                </View>
                <Text style={styles.otpTitle}>Enter Verification Code</Text>
                <Text style={styles.otpSubtitle}>
                  OTP sent to <Text style={styles.highlightPhone}>{phone}</Text>
                </Text>
                <View style={styles.validBadge}>
                  <CheckCircleIcon color="#10B981" size={12} />
                  <Text style={styles.validText}>Valid for 5 minutes</Text>
                </View>
              </View>

              {error ? (
                <View style={styles.errorBanner}>
                  <Text style={styles.errorText}>{error}</Text>
                </View>
              ) : null}

              {successMessage ? (
                <View style={styles.successBanner}>
                  <Text style={styles.successText}>{successMessage}</Text>
                </View>
              ) : null}

              {/* 6-Digit Input Box Grid */}
              <View style={styles.otpGrid}>
                {otpDigits.map((digit, index) => (
                  <TextInput
                    key={index}
                    ref={inputRefs[index]}
                    style={styles.otpInput}
                    keyboardType="numeric"
                    maxLength={1}
                    value={digit}
                    onChangeText={(val) => handleOtpChange(index, val)}
                    onKeyPress={({ nativeEvent }) => handleKeyPress(index, nativeEvent.key)}
                  />
                ))}
              </View>

              <TouchableOpacity
                style={[
                  styles.button,
                  otpDigits.join('').length !== 6 ? styles.buttonDisabled : null,
                ]}
                onPress={handleVerifyOTP}
                disabled={loading || otpDigits.join('').length !== 6}
              >
                {loading ? (
                  <ActivityIndicator color="#0F2042" size="small" />
                ) : (
                  <View style={styles.buttonInner}>
                    <Text style={styles.buttonText}>Verify OTP & Sign In</Text>
                    <ArrowRightIcon color="#0F2042" size={14} />
                  </View>
                )}
              </TouchableOpacity>

              <View style={styles.otpActions}>
                <TouchableOpacity
                  onPress={handleSendOTP}
                  style={styles.actionBtn}
                >
                  <RefreshIcon color="#F59E0B" size={12} />
                  <Text style={styles.actionText}>Resend OTP</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={() => {
                    setStep('credentials');
                    setOtpDigits(['', '', '', '', '', '']);
                    setError('');
                    setSuccessMessage('');
                  }}
                  style={styles.actionBtn}
                >
                  <EditIcon color="#F59E0B" size={12} />
                  <Text style={styles.actionText}>Edit Phone</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* Footer Info */}
          <View style={styles.footer}>
            <Text style={styles.footerText}>Secured with Dovesoft SMS Gateway</Text>
            <Text style={styles.footerVersion}>v1.0 Enterprise Mobile Release</Text>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  keyboardContainer: {
    flex: 1,
    backgroundColor: '#0F2042',
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: 'space-between',
  },
  container: {
    flex: 1,
    justifyContent: 'space-between',
    padding: 24,
    paddingTop: Platform.OS === 'ios' ? 60 : 40,
    paddingBottom: 20,
  },
  brandingHeader: {
    alignItems: 'center',
    marginTop: 20,
  },
  logoBadge: {
    width: 60,
    height: 60,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 20,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.2)',
    marginBottom: 12,
  },
  logoText: {
    fontSize: 28,
  },
  titleText: {
    fontSize: 20,
    fontWeight: '900',
    color: '#FFFFFF',
    letterSpacing: -0.5,
  },
  subtitleText: {
    fontSize: 12,
    color: '#94A3B8',
    marginTop: 4,
    textAlign: 'center',
  },
  formCard: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
    padding: 20,
    marginVertical: 40,
  },
  formHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.1)',
    paddingBottom: 12,
    marginBottom: 20,
  },
  formTitle: {
    fontSize: 13,
    fontWeight: 'bold',
    color: '#FFFFFF',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  formBadge: {
    fontSize: 10,
    fontWeight: '600',
    color: '#F59E0B',
  },
  errorBanner: {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
    borderColor: 'rgba(239, 68, 68, 0.4)',
    borderWidth: 1,
    borderRadius: 12,
    padding: 10,
    marginBottom: 16,
  },
  errorText: {
    color: '#FECACA',
    fontSize: 12,
    textAlign: 'center',
    fontWeight: '500',
  },
  successBanner: {
    backgroundColor: 'rgba(16, 185, 129, 0.2)',
    borderColor: 'rgba(16, 185, 129, 0.4)',
    borderWidth: 1,
    borderRadius: 12,
    padding: 10,
    marginBottom: 16,
  },
  successText: {
    color: '#D1FAE5',
    fontSize: 12,
    textAlign: 'center',
    fontWeight: '500',
  },
  inputGroup: {
    marginBottom: 20,
  },
  label: {
    fontSize: 11,
    fontWeight: 'bold',
    color: '#94A3B8',
    textTransform: 'uppercase',
    marginBottom: 6,
    letterSpacing: 0.5,
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(15, 20, 40, 0.6)',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 12,
    paddingHorizontal: 12,
  },
  inputIcon: {
    marginRight: 10,
    fontSize: 16,
  },
  textInput: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 14,
    paddingVertical: Platform.OS === 'ios' ? 12 : 8,
  },
  button: {
    backgroundColor: '#F59E0B',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 8,
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonInner: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonText: {
    color: '#0F2042',
    fontSize: 13,
    fontWeight: 'bold',
    marginRight: 6,
  },
  otpHeader: {
    alignItems: 'center',
    marginBottom: 20,
  },
  otpIconCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(245, 158, 11, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(245, 158, 11, 0.3)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 10,
  },
  otpTitle: {
    fontSize: 15,
    fontWeight: 'bold',
    color: '#FFFFFF',
  },
  otpSubtitle: {
    fontSize: 12,
    color: '#94A3B8',
    marginTop: 4,
  },
  highlightPhone: {
    fontWeight: 'bold',
    color: '#F59E0B',
  },
  validBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.1)',
    borderColor: 'rgba(16, 185, 129, 0.2)',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    marginTop: 8,
  },
  validText: {
    color: '#34D399',
    fontSize: 10,
    fontWeight: '600',
    marginLeft: 4,
  },
  otpGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  otpInput: {
    width: 42,
    height: 48,
    borderWidth: 1.5,
    borderColor: '#475569',
    borderRadius: 12,
    backgroundColor: 'rgba(15, 20, 40, 0.8)',
    color: '#F59E0B',
    fontSize: 18,
    fontWeight: '900',
    textAlign: 'center',
  },
  otpActions: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: 'rgba(255, 255, 255, 0.1)',
    paddingTop: 16,
    marginTop: 16,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  actionText: {
    color: '#94A3B8',
    fontSize: 11,
    fontWeight: '600',
    marginLeft: 4,
  },
  footer: {
    alignItems: 'center',
  },
  footerText: {
    color: '#64748B',
    fontSize: 10,
  },
  footerVersion: {
    color: '#475569',
    fontSize: 9,
    marginTop: 2,
  },
});
