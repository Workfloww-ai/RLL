import React, { useState } from 'react';
import {
  View,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  StyleProp,
  ViewStyle,
  TextStyle,
  ReturnKeyTypeOptions,
} from 'react-native';
import { SearchIcon, XIcon } from './Icons';

export interface SearchBarProps {
  /** The current search text value */
  value: string;
  /** Callback fired when the search text changes */
  onChangeText: (text: string) => void;
  /** Optional placeholder text */
  placeholder?: string;
  /** Optional callback fired when the clear button (X) is clicked */
  onClear?: () => void;
  /** Optional callback fired when search is submitted via soft keyboard */
  onSubmitEditing?: () => void;
  /** Optional scale factor for dynamic font/icon sizing */
  scaleFactor?: number;
  /** Custom container style overrides */
  containerStyle?: StyleProp<ViewStyle>;
  /** Custom text input style overrides */
  inputStyle?: StyleProp<TextStyle>;
  /** Color of search and clear icons */
  iconColor?: string;
  /** Color of placeholder text */
  placeholderTextColor?: string;
  /** Auto focus on mount */
  autoFocus?: boolean;
  /** Whether input is editable */
  editable?: boolean;
  /** Return key type for soft keyboard */
  returnKeyType?: ReturnKeyTypeOptions;
  /** Active focus border highlight */
  showFocusBorder?: boolean;
}

export const SearchBar = React.memo(function SearchBar({
  value,
  onChangeText,
  placeholder = 'Search...',
  onClear,
  onSubmitEditing,
  scaleFactor = 1,
  containerStyle,
  inputStyle,
  iconColor = '#94A3B8',
  placeholderTextColor = '#94A3B8',
  autoFocus = false,
  editable = true,
  returnKeyType = 'search',
  showFocusBorder = true,
}: SearchBarProps) {
  const [isFocused, setIsFocused] = useState(false);
  const scaledIconSize = Math.round(15 * scaleFactor);
  const scaledFontSize = Math.round(13 * scaleFactor);

  const handleClear = () => {
    onChangeText('');
    if (onClear) onClear();
  };

  return (
    <View
      style={[
        styles.container,
        showFocusBorder && isFocused ? styles.containerFocused : null,
        containerStyle,
      ]}
    >
      <SearchIcon size={scaledIconSize} color={isFocused ? '#0D3B8E' : iconColor} />
      
      <TextInput
        style={[
          styles.input,
          { fontSize: scaledFontSize },
          inputStyle,
        ]}
        placeholder={placeholder}
        placeholderTextColor={placeholderTextColor}
        value={value}
        onChangeText={onChangeText}
        autoCorrect={false}
        autoCapitalize="none"
        autoFocus={autoFocus}
        editable={editable}
        returnKeyType={returnKeyType}
        onSubmitEditing={onSubmitEditing}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        clearButtonMode="never"
      />

      {Boolean(value && value.length > 0) && (
        <TouchableOpacity
          onPress={handleClear}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
          activeOpacity={0.7}
          style={styles.clearButton}
        >
          <XIcon size={Math.round(13 * scaleFactor)} color="#94A3B8" />
        </TouchableOpacity>
      )}
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 12,
    paddingHorizontal: 12,
    height: 40,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.02,
    shadowRadius: 3,
    elevation: 1,
  },
  containerFocused: {
    borderColor: '#0D3B8E',
    backgroundColor: '#FFFFFF',
  },
  input: {
    flex: 1,
    marginLeft: 8,
    marginRight: 4,
    color: '#0F172A',
    fontWeight: '600',
    paddingVertical: 0,
  },
  clearButton: {
    padding: 2,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
