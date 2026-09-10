import AsyncStorage from '@react-native-async-storage/async-storage';
import { logger } from './logger';

/**
 * FastStorage Engine: High-performance unified storage module.
 * Provides synchronous 0ms memory access with non-blocking persistent disk synchronization.
 * Compatible with react-native-mmkv and AsyncStorage.
 */
class FastStorageEngine {
  private memoryMap = new Map<string, string>();
  private isHydrated = false;
  private readonly FAST_STORAGE_PREFIX = 'rll_fast_v2::';

  constructor() {
    this.hydrateStorage();
  }

  /**
   * Hydrates memory storage from persistent disk on module import/app launch.
   */
  public async hydrateStorage(): Promise<void> {
    if (this.isHydrated) return;
    try {
      const keys = await AsyncStorage.getAllKeys();
      const fastKeys = keys.filter((k) => k.startsWith(this.FAST_STORAGE_PREFIX));
      if (fastKeys.length > 0) {
        const pairs = await AsyncStorage.multiGet(fastKeys);
        for (const [key, val] of pairs) {
          if (val) {
            const rawKey = key.replace(this.FAST_STORAGE_PREFIX, '');
            this.memoryMap.set(rawKey, val);
          }
        }
        logger.info(`FastStorage: Hydrated ${this.memoryMap.size} keys into synchronous memory cache.`);
      }
    } catch (e) {
      logger.warn(`FastStorage hydration error: ${e}`);
    } finally {
      this.isHydrated = true;
    }
  }

  /**
   * Synchronous 0ms read from memory cache.
   */
  public getString(key: string): string | null {
    return this.memoryMap.get(key) || null;
  }

  /**
   * Synchronous JSON parse helper.
   */
  public getObject<T = unknown>(key: string): T | null {
    const raw = this.getString(key);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as T;
    } catch (e) {
      logger.warn(`FastStorage getObject parse error for key '${key}': ${e}`);
      return null;
    }
  }

  /**
   * Synchronous memory write + background non-blocking disk sync.
   */
  public setString(key: string, value: string): void {
    if (!key || value === undefined || value === null) return;
    this.memoryMap.set(key, value);
    const diskKey = `${this.FAST_STORAGE_PREFIX}${key}`;
    AsyncStorage.setItem(diskKey, value).catch((e) => {
      logger.warn(`FastStorage setString disk sync error for '${key}': ${e}`);
    });
  }

  /**
   * Synchronous JSON object write + background disk sync.
   */
  public setObject(key: string, value: unknown): void {
    if (!key || value === undefined || value === null) return;
    try {
      const jsonStr = JSON.stringify(value);
      this.setString(key, jsonStr);
    } catch (e) {
      logger.warn(`FastStorage setObject stringify error for '${key}': ${e}`);
    }
  }

  /**
   * Delete key from memory and disk.
   */
  public delete(key: string): void {
    this.memoryMap.delete(key);
    const diskKey = `${this.FAST_STORAGE_PREFIX}${key}`;
    AsyncStorage.removeItem(diskKey).catch(() => {});
  }

  /**
   * Clear all FastStorage keys.
   */
  public clear(): void {
    this.memoryMap.clear();
    AsyncStorage.getAllKeys()
      .then((keys) => {
        const fastKeys = keys.filter((k) => k.startsWith(this.FAST_STORAGE_PREFIX) || k.startsWith('rll_phone_cache_') || k.startsWith('rll_disk_cache::'));
        if (fastKeys.length > 0) {
          AsyncStorage.multiRemove(fastKeys).catch(() => {});
        }
      })
      .catch(() => {});
  }

  /**
   * Returns list of all keys currently in FastStorage memory map.
   */
  public getAllKeys(): string[] {
    return Array.from(this.memoryMap.keys());
  }
}

export const FastStorage = new FastStorageEngine();
