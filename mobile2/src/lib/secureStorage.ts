import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

function assertNativeSecureStore(): void {
  if (Platform.OS === 'web') {
    throw new Error(
      'Native SecureStore is unavailable on web.'
    );
  }
}

export const secureStorage = {
  async setItem(key: string, value: string): Promise<void> {
    assertNativeSecureStore();
    await SecureStore.setItemAsync(key, value);
  },

  async getItem(key: string): Promise<string | null> {
    assertNativeSecureStore();
    return SecureStore.getItemAsync(key);
  },

  async removeItem(key: string): Promise<void> {
    assertNativeSecureStore();
    await SecureStore.deleteItemAsync(key);
  },
};
