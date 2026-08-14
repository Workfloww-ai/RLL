const isDev = __DEV__;

export const logger = {
  info: (message: string, ...optionalParams: any[]) => {
    if (isDev) {
      console.log(
        `[INFO] [${new Date().toLocaleTimeString()}] ${message}`,
        ...optionalParams,
      );
    }
  },
  warn: (message: string, ...optionalParams: any[]) => {
    if (isDev) {
      console.warn(
        `[WARN] [${new Date().toLocaleTimeString()}] ${message}`,
        ...optionalParams,
      );
    }
  },
  error: (message: string, ...optionalParams: any[]) => {
    if (isDev) {
      console.error(
        `[ERROR] [${new Date().toLocaleTimeString()}] ${message}`,
        ...optionalParams,
      );
    }
  },
};
