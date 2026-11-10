import React, { useEffect } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  TouchableWithoutFeedback,
} from 'react-native';
import { CalendarIcon, RefreshIcon } from './Icons';
import { trackMobileActivity } from '../lib/posthog';

interface NoDataModalProps {
  visible: boolean;
  onReset: () => void;
  onClose: () => void;
  selectedDate?: string;
}

export const NoDataModal: React.FC<NoDataModalProps> = ({
  visible,
  onReset,
  onClose,
  selectedDate,
}) => {
  useEffect(() => {
    if (visible) {
      trackMobileActivity('modal_opened', {
        modal_name: 'NoDataModal',
        selected_date: selectedDate,
      });
    }
  }, [visible, selectedDate]);

  const handleReset = () => {
    trackMobileActivity('modal_action_clicked', {
      modal_name: 'NoDataModal',
      action: 'reset_to_latest_date',
      selected_date: selectedDate,
    });
    onReset();
  };

  const handleClose = () => {
    trackMobileActivity('modal_closed', {
      modal_name: 'NoDataModal',
      selected_date: selectedDate,
    });
    onClose();
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={handleClose}
    >
      <TouchableWithoutFeedback onPress={handleClose}>
        <View style={styles.overlay}>
          <TouchableWithoutFeedback>
            <View style={styles.modalCard}>
              {/* Icon Badge */}
              <View style={styles.iconContainer}>
                <CalendarIcon size={28} color="#0284C7" />
              </View>

              {/* Title */}
              <Text style={styles.title}>No Data Found</Text>

              {/* Subtitle / Description */}
              <Text style={styles.description}>
                {selectedDate
                  ? `No sales records were found for ${selectedDate}.`
                  : 'No sales records were found for the selected date.'}{' '}
                Tap below to view the latest active sales data.
              </Text>

              {/* Action Buttons */}
              <TouchableOpacity
                style={styles.resetBtn}
                onPress={handleReset}
                activeOpacity={0.8}
              >
                <RefreshIcon size={16} color="#FFFFFF" />
                <Text style={styles.resetBtnText}>Reset to Latest Date</Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={styles.dismissBtn}
                onPress={handleClose}
                activeOpacity={0.7}
              >
                <Text style={styles.dismissBtnText}>Dismiss</Text>
              </TouchableOpacity>
            </View>
          </TouchableWithoutFeedback>
        </View>
      </TouchableWithoutFeedback>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.65)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  modalCard: {
    width: '100%',
    maxWidth: 340,
    backgroundColor: '#FFFFFF',
    borderRadius: 20,
    padding: 24,
    alignItems: 'center',
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.25,
    shadowRadius: 20,
    elevation: 10,
  },
  iconContainer: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#EFF6FF',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: '#0F172A',
    marginBottom: 8,
    textAlign: 'center',
  },
  description: {
    fontSize: 14,
    color: '#64748B',
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 24,
  },
  resetBtn: {
    width: '100%',
    height: 46,
    backgroundColor: '#0284C7',
    borderRadius: 12,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
  },
  resetBtnText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
  },
  dismissBtn: {
    paddingVertical: 8,
    paddingHorizontal: 16,
  },
  dismissBtnText: {
    color: '#64748B',
    fontSize: 14,
    fontWeight: '500',
  },
});
