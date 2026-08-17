import { Dimensions, PixelRatio } from 'react-native';

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

// Standard design baseline (iPhone 13 / 14 / Android standard)
const BASE_WIDTH = 375;
const BASE_HEIGHT = 812;

export function scaleWidth(size: number): number {
  return Math.round((SCREEN_WIDTH / BASE_WIDTH) * size);
}

export function scaleHeight(size: number): number {
  return Math.round((SCREEN_HEIGHT / BASE_HEIGHT) * size);
}

export function scaleFont(size: number): number {
  const scale = SCREEN_WIDTH / BASE_WIDTH;
  const newSize = size * scale;
  return Math.round(PixelRatio.roundToNearestPixel(newSize));
}

/**
 * Dynamically calculates ideal card height so that exactly 3 full cards
 * plus ~35% of a 4th card are visible initially in the scrollable viewport.
 */
export function getDynamicCardDimensions(windowHeight: number) {
  // Approximate non-card heights: safe area (~44) + header (~135) + banner (~40) + search (~50) + footer (~65) + margins (~30)
  const occupiedHeight = 364;
  const availableScrollHeight = Math.max(windowHeight - occupiedHeight, 350);
  
  // Fit 3.35 cards in available scroll height
  const idealCardHeight = Math.min(Math.max(Math.floor(availableScrollHeight / 3.35), 105), 145);
  const cardPaddingVertical = idealCardHeight < 115 ? 10 : 14;
  const innerBoxPaddingVertical = idealCardHeight < 115 ? 6 : 10;
  const metricFontSize = idealCardHeight < 115 ? 14 : 16;
  const titleFontSize = idealCardHeight < 115 ? 14 : 16;

  return {
    cardHeight: idealCardHeight,
    cardPaddingVertical,
    innerBoxPaddingVertical,
    metricFontSize,
    titleFontSize,
  };
}
