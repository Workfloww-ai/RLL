import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';
import { logger } from './logger';

let SecureStore: any = null;
try {
  SecureStore = require('expo-secure-store');
} catch (e) {
  logger.warn('expo-secure-store module not found, using AsyncStorage fallback.');
}

const isSecureStoreAvailable = (): boolean => {
  return Platform.OS !== 'web' && SecureStore && typeof SecureStore.setItemAsync === 'function';
};

/**
 * Hardware-backed Encrypted Storage for Auth Tokens & User Identifiers.
 * Uses iOS Keychain / Android Keystore when available, with AsyncStorage fallback on web.
 */
export const secureStorage = {
  async setItem(key: string, value: string): Promise<void> {
    try {
      if (isSecureStoreAvailable()) {
        await SecureStore.setItemAsync(key, value);
      } else {
        await AsyncStorage.setItem(key, value);
      }
    } catch (e) {
      logger.error(`secureStorage.setItem error for key '${key}':`, e);
      await AsyncStorage.setItem(key, value);
    }
  },

  async getItem(key: string): Promise<string | null> {
    try {
      if (isSecureStoreAvailable()) {
        const val = await SecureStore.getItemAsync(key);
        if (val !== null) return val;
      }
      return await AsyncStorage.getItem(key);
    } catch (e) {
      logger.error(`secureStorage.getItem error for key '${key}':`, e);
      return await AsyncStorage.getItem(key);
    }
  },

  async removeItem(key: string): Promise<void> {
    try {
      if (isSecureStoreAvailable()) {
        await SecureStore.deleteItemAsync(key);
      }
      await AsyncStorage.removeItem(key);
    } catch (e) {
      logger.error(`secureStorage.removeItem error for key '${key}':`, e);
      await AsyncStorage.removeItem(key);
    }
  }
};
