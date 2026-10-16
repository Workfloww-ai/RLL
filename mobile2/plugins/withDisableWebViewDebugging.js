const { withMainApplication } = require('@expo/config-plugins');

/**
 * Expo Config Plugin to explicitly disable WebView remote debugging in production release builds.
 */
module.exports = function withDisableWebViewDebugging(config) {
  return withMainApplication(config, (config) => {
    let mainApplication = config.modResults.contents;

    if (!mainApplication.includes('setWebContentsDebuggingEnabled')) {
      const targetPattern = /super\.onCreate\(\)/;
      const codeToInject = `    super.onCreate()
    if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.KITKAT) {
      val isDebuggable = (applicationContext.applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
      android.webkit.WebView.setWebContentsDebuggingEnabled(isDebuggable)
    }`;

      if (targetPattern.test(mainApplication)) {
        mainApplication = mainApplication.replace(targetPattern, codeToInject);
      }
    }

    config.modResults.contents = mainApplication;
    return config;
  });
};
