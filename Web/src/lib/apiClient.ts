import CryptoJS from 'crypto-js';

const ENVIRONMENT = import.meta.env.VITE_ENVIRONMENT || 'development';
const ENCRYPTION_KEY = import.meta.env.VITE_PAYLOAD_ENCRYPTION_KEY || '';

export function encryptPayload(data: string): string {
    if (!ENCRYPTION_KEY || ENCRYPTION_KEY.length !== 64) {
        console.error("Invalid VITE_PAYLOAD_ENCRYPTION_KEY length. Expected 64 characters.");
        return data;
    }
    try {
        const key = CryptoJS.enc.Hex.parse(ENCRYPTION_KEY);
        const iv = CryptoJS.lib.WordArray.random(16);
        const encrypted = CryptoJS.AES.encrypt(data, key, {
            iv: iv,
            mode: CryptoJS.mode.CBC,
            padding: CryptoJS.pad.Pkcs7
        });
        const ivAndCiphertext = iv.clone().concat(encrypted.ciphertext);
        return CryptoJS.enc.Base64.stringify(ivAndCiphertext);
    } catch (e) {
        console.error("Encryption failed", e);
        return data;
    }
}

export function decryptPayload(encryptedB64: string): string {
    if (!ENCRYPTION_KEY || ENCRYPTION_KEY.length !== 64) {
        console.error("Invalid VITE_PAYLOAD_ENCRYPTION_KEY length. Expected 64 characters.");
        return encryptedB64;
    }
    try {
        const key = CryptoJS.enc.Hex.parse(ENCRYPTION_KEY);
        const encryptedWords = CryptoJS.enc.Base64.parse(encryptedB64);
        
        const iv = CryptoJS.lib.WordArray.create(encryptedWords.words.slice(0, 4), 16);
        const ciphertext = CryptoJS.lib.WordArray.create(encryptedWords.words.slice(4), encryptedWords.sigBytes - 16);
        const cipherParams = CryptoJS.lib.CipherParams.create({ ciphertext: ciphertext });
        
        const decrypted = CryptoJS.AES.decrypt(cipherParams, key, {
            iv: iv,
            mode: CryptoJS.mode.CBC,
            padding: CryptoJS.pad.Pkcs7
        });
        return decrypted.toString(CryptoJS.enc.Utf8);
    } catch (e) {
        console.error("Decryption failed", e);
        return encryptedB64;
    }
}

export async function secureFetch(url: string, options: RequestInit = {}): Promise<Response> {
    const isProduction = ENVIRONMENT === 'production';
    
    // Encrypt request body if applicable
    if (isProduction && options.body && typeof options.body === 'string') {
        const encrypted = encryptPayload(options.body);
        options.body = JSON.stringify({ encrypted_data: encrypted });
        
        if (!options.headers) options.headers = {};
        (options.headers as Record<string, string>)['Content-Type'] = 'application/json';
    }

    const response = await fetch(url, options);

    // If production, decrypt response body if it's encrypted
    if (isProduction && response.ok) {
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            const responseClone = response.clone();
            const text = await responseClone.text();
            
            try {
                const json = JSON.parse(text);
                if (json.encrypted_data) {
                    const decryptedStr = decryptPayload(json.encrypted_data);
                    
                    return new Response(decryptedStr, {
                        status: response.status,
                        statusText: response.statusText,
                        headers: response.headers
                    });
                }
            } catch (e) {
                // If it's not JSON or parsing fails, just return original response
                console.warn("Failed to parse or decrypt response", e);
            }
        }
    }

    return response;
}
