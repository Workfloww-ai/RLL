module.exports = {
  preset: '@react-native/jest-preset',
  moduleNameMapper: {
    '^react-native/setup-env$': '<rootDir>/__mocks__/setup-env.js',
    '^expo-secure-store$': '<rootDir>/__mocks__/expo-secure-store.js',
    '^@react-native-async-storage/async-storage$': '@react-native-async-storage/async-storage/jest/async-storage-mock',
    '^expo/virtual/env$': '<rootDir>/__mocks__/expo-env.js',
    '^expo-constants$': '<rootDir>/__mocks__/expo-constants.js',
    '^expo-font$': '<rootDir>/__mocks__/expo-font.js',
    '^@expo/vector-icons(/.*)?$': '<rootDir>/__mocks__/vector-icons.js',
    '\\.svg$': '<rootDir>/__mocks__/svgMock.js',
  },
};
