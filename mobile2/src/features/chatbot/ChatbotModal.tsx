/**
 * Mobile Sales Analytics Chatbot Modal Component.
 * Premium Enterprise SaaS Redesign with RLL Signature Navy (#0D3B8E) Brand Accent.
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Modal,
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  TextInput,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { sendChatMessage } from './chatbotApi';

interface Message {
  id: string;
  sender: 'user' | 'ai';
  text: string;
  time: string;
  kpis?: Array<{ title: string; value: string; subtext?: string; change_pct?: number; change_type?: string }>;
  table?: { title: string; columns: Array<{ key: string; label: string; align?: string }>; rows: Array<any> };
  chart?: { title: string; data: Array<{ label: string; value: number }> };
  suggestedQuestions?: string[];
}

interface ChatbotModalProps {
  visible: boolean;
  onClose: () => void;
  period?: string;
  selectedHq?: string;
}

// Signature RLL AI Star Icon Badge
const AiBadgeStarIcon = () => (
  <View style={styles.aiBadgeIcon}>
    <Text style={styles.aiBadgeStarText}>✨</Text>
  </View>
);

// Refresh Icon
const RefreshOutlineIcon = () => (
  <Text style={{ fontSize: 16, color: '#0D3B8E', fontWeight: '700' }}>↺</Text>
);

// Close Icon
const CloseOutlineIcon = () => (
  <Text style={{ fontSize: 16, color: '#64748B', fontWeight: '600' }}>✕</Text>
);

// Microphone Vector Icon (Zero Emoji)
const MicOutlineIcon = ({ active }: { active?: boolean }) => {
  const color = active ? '#0D3B8E' : '#64748B';
  return (
    <View style={{ width: 16, height: 18, alignItems: 'center', justifyContent: 'center' }}>
      <View style={{ width: 8, height: 10, borderRadius: 4, borderWidth: 1.6, borderColor: color }} />
      <View style={{ width: 12, height: 5, borderBottomLeftRadius: 6, borderBottomRightRadius: 6, borderWidth: 1.6, borderColor: color, borderTopWidth: 0, marginTop: -2.5 }} />
      <View style={{ width: 1.6, height: 3.5, backgroundColor: color }} />
    </View>
  );
};

// Send Icon
const SendArrowIcon = () => (
  <Text style={{ fontSize: 14, color: '#FFFFFF', fontWeight: '800' }}>➔</Text>
);

export const ChatbotModal: React.FC<ChatbotModalProps> = ({
  visible,
  onClose,
  period = 'Daily',
  selectedHq = 'All Headquarters',
}) => {
  const [inputQuery, setInputQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [isDictating, setIsDictating] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome_1',
      sender: 'ai',
      text:
        'RLL Sales Agent\n\n' +
        'Ask questions about your sales data.\n\n' +
        'I can help you understand:\n' +
        '• Sales performance\n' +
        '• Top brands\n' +
        '• Company performance\n' +
        '• TSM performance\n' +
        '• Daily, MTD and YTD trends',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      suggestedQuestions: [
        'Top 5 brands',
        'Daily sales summary',
        'TSM performance',
        'Company performance',
      ],
    },
  ]);

  const scrollViewRef = useRef<ScrollView>(null);

  useEffect(() => {
    if (visible) {
      setTimeout(() => {
        scrollViewRef.current?.scrollToEnd({ animated: true });
      }, 200);
    }
  }, [visible, messages]);

  const handleSend = async (queryText?: string) => {
    const textToSend = (queryText || inputQuery).trim();
    if (!textToSend || loading) return;

    const userMsgId = `usr_${Date.now()}`;
    const userTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const newUserMessage: Message = {
      id: userMsgId,
      sender: 'user',
      text: textToSend,
      time: userTime,
    };

    setMessages((prev) => [...prev, newUserMessage]);
    setInputQuery('');
    setLoading(true);

    try {
      const res = await sendChatMessage(textToSend, period, selectedHq);

      const aiMsgId = `ai_${Date.now()}`;
      const aiTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      const newAiMessage: Message = {
        id: aiMsgId,
        sender: 'ai',
        text: res.text || 'Analysis complete.',
        time: aiTime,
        kpis: res.kpis,
        table: res.table,
        chart: res.chart,
        suggestedQuestions: res.suggested_questions,
      };

      setMessages((prev) => [...prev, newAiMessage]);
    } catch (err: any) {
      const errorMsg: Message = {
        id: `err_${Date.now()}`,
        sender: 'ai',
        text: `Unable to retrieve sales data: ${err.message || 'Please check network connection.'}`,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setMessages([
      {
        id: `welcome_${Date.now()}`,
        sender: 'ai',
        text:
          'RLL Sales Agent\n\n' +
          'Ask questions about your sales data.\n\n' +
          'I can help you understand:\n' +
          '• Sales performance\n' +
          '• Top brands\n' +
          '• Company performance\n' +
          '• TSM performance\n' +
          '• Daily, MTD and YTD trends',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        suggestedQuestions: [
          'Top 5 brands',
          'Daily sales summary',
          'TSM performance',
          'Company performance',
        ],
      },
    ]);
  };

  const suggestedQuestionsList = [
    'Top 5 brands',
    'Daily sales summary',
    'TSM performance',
    'Company performance',
  ];

  if (!visible) return null;

  return (
    <Modal
      visible={visible}
      animationType="slide"
      transparent={false}
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <View style={styles.modalBackground}>
        <SafeAreaView style={styles.safeAreaContainer} edges={['top', 'bottom']}>
          <KeyboardAvoidingView
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.keyboardAvoidingContainer}
            keyboardVerticalOffset={Platform.OS === 'android' ? 24 : 0}
          >
          {/* Header */}
          <View style={styles.header}>
            <View style={styles.headerLeft}>
              <AiBadgeStarIcon />
              <View>
                <View style={styles.titleRow}>
                  <Text style={styles.headerTitle}>RLL Sales Agent</Text>
                  <View style={styles.liveBadge}>
                    <View style={styles.liveDot} />
                    <Text style={styles.liveBadgeText}>Live</Text>
                  </View>
                </View>
                <Text style={styles.headerSubtitle}>Live sales analytics</Text>
              </View>
            </View>

            <View style={styles.headerActions}>
              <TouchableOpacity onPress={handleReset} style={styles.iconBtn} activeOpacity={0.7}>
                <RefreshOutlineIcon />
              </TouchableOpacity>
              <TouchableOpacity onPress={onClose} style={styles.closeBtn} activeOpacity={0.7}>
                <CloseOutlineIcon />
              </TouchableOpacity>
            </View>
          </View>

          {/* Context Bar */}
          <View style={styles.contextBar}>
            <Text style={styles.contextText}>
              {period}  ·  {selectedHq}
            </Text>
          </View>

          {/* Chat Messages */}
          <ScrollView
            ref={scrollViewRef}
            style={styles.chatArea}
            contentContainerStyle={styles.chatContent}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode={Platform.OS === 'ios' ? 'interactive' : 'on-drag'}
          >
            {messages.map((msg) => (
              <View
                key={msg.id}
                style={[
                  styles.messageRow,
                  msg.sender === 'user' ? styles.userRow : styles.aiRow,
                ]}
              >
                <View
                  style={[
                    styles.bubble,
                    msg.sender === 'user' ? styles.userBubble : styles.aiBubble,
                  ]}
                >
                  <Text
                    style={[
                      styles.bubbleText,
                      msg.sender === 'user' ? styles.userBubbleText : styles.aiBubbleText,
                    ]}
                  >
                    {msg.text}
                  </Text>

                  {/* KPIs rendering */}
                  {msg.kpis && msg.kpis.length > 0 && (
                    <View style={styles.kpiContainer}>
                      {msg.kpis.map((k, idx) => (
                        <View key={idx} style={styles.kpiCard}>
                          <Text style={styles.kpiTitle}>{k.title}</Text>
                          <Text style={styles.kpiValue}>{k.value}</Text>
                          {k.subtext ? <Text style={styles.kpiSubtext}>{k.subtext}</Text> : null}
                        </View>
                      ))}
                    </View>
                  )}

                  {/* Table rendering */}
                  {msg.table && (
                    <View style={styles.tableContainer}>
                      <Text style={styles.tableTitle}>{msg.table.title}</Text>
                      <View style={styles.tableHeaderRow}>
                        {msg.table.columns.map((col) => (
                          <Text
                            key={col.key}
                            style={[
                              styles.tableHeaderCell,
                              col.align === 'right'
                                ? { textAlign: 'right' }
                                : col.align === 'center'
                                  ? { textAlign: 'center' }
                                  : { textAlign: 'left' },
                            ]}
                          >
                            {col.label}
                          </Text>
                        ))}
                      </View>
                      {msg.table.rows.map((row, rIdx) => (
                        <View key={rIdx} style={styles.tableBodyRow}>
                          {msg.table!.columns.map((col) => (
                            <Text
                              key={col.key}
                              style={[
                                styles.tableBodyCell,
                                col.align === 'right'
                                  ? { textAlign: 'right' }
                                  : col.align === 'center'
                                    ? { textAlign: 'center' }
                                    : { textAlign: 'left' },
                              ]}
                            >
                              {row[col.key]}
                            </Text>
                          ))}
                        </View>
                      ))}
                    </View>
                  )}

                  {/* Chart rendering */}
                  {msg.chart && msg.chart.data && (
                    <View style={styles.chartContainer}>
                      <Text style={styles.chartTitle}>{msg.chart.title}</Text>
                      {msg.chart.data.map((dp, dIdx) => {
                        const maxVal = Math.max(...msg.chart!.data.map((d) => d.value)) || 1;
                        const barPct = Math.min(100, Math.max(8, (dp.value / maxVal) * 100));
                        return (
                          <View key={dIdx} style={styles.barRow}>
                            <Text style={styles.barLabel} numberOfLines={1}>
                              {dp.label}
                            </Text>
                            <View style={styles.barTrack}>
                              <View style={[styles.barFill, { width: `${barPct}%` }]} />
                            </View>
                            <Text style={styles.barValue}>{dp.value.toLocaleString()}</Text>
                          </View>
                        );
                      })}
                    </View>
                  )}

                  <Text
                    style={[
                      styles.timestamp,
                      msg.sender === 'user' ? styles.userTimestamp : styles.aiTimestamp,
                    ]}
                  >
                    {msg.time}
                  </Text>
                </View>
              </View>
            ))}

            {loading && (
              <View style={styles.loadingRow}>
                <View style={styles.loadingBubble}>
                  <ActivityIndicator size="small" color="#0D3B8E" />
                  <Text style={styles.loadingText}>Analyzing sales data...</Text>
                </View>
              </View>
            )}
          </ScrollView>

          {/* Suggested Questions Section */}
          <View style={styles.suggestedSection}>
            <Text style={styles.suggestedLabel}>Suggested questions</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.suggestedScroll}>
              {suggestedQuestionsList.map((qText, qIdx) => (
                <TouchableOpacity
                  key={qIdx}
                  style={styles.suggestedCard}
                  onPress={() => handleSend(qText)}
                  activeOpacity={0.75}
                >
                  <View style={styles.suggestedDot} />
                  <Text style={styles.suggestedText}>{qText}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          {/* Input Bar */}
          <View style={styles.inputContainer}>
            <TouchableOpacity
              style={[styles.voiceBtn, isDictating && styles.voiceBtnActive]}
              onPress={() => setIsDictating(!isDictating)}
              activeOpacity={0.7}
            >
              <MicOutlineIcon active={isDictating} />
            </TouchableOpacity>

            <TextInput
              style={styles.input}
              placeholder="Ask about sales..."
              placeholderTextColor="#94A3B8"
              value={inputQuery}
              onChangeText={setInputQuery}
              onSubmitEditing={() => handleSend()}
              returnKeyType="send"
            />

            <TouchableOpacity
              style={[styles.sendBtn, !inputQuery.trim() && styles.sendBtnDisabled]}
              onPress={() => handleSend()}
              disabled={!inputQuery.trim() || loading}
              activeOpacity={0.8}
            >
              <SendArrowIcon />
            </TouchableOpacity>
          </View>

          {/* Footer note */}
          <View style={styles.footerRow}>
            <Text style={styles.footerNote}>Powered by Workfloww.ai</Text>
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  </Modal>
  );
};

const styles = StyleSheet.create({
  modalBackground: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  safeAreaContainer: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  keyboardAvoidingContainer: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 16,
    paddingTop: Platform.OS === 'android' ? 4 : 0,
    paddingBottom: Platform.OS === 'ios' ? 4 : 4,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  aiBadgeIcon: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#090D16',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: '#2563EB',
  },
  aiBadgeStarText: {
    fontSize: 18,
    color: '#FFD700',
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    color: '#0D3B8E',
    fontSize: 16,
    fontWeight: '700',
  },
  liveBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F0FDF4',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 10,
    gap: 4,
    borderWidth: 1,
    borderColor: '#DCFCE7',
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#16A34A',
  },
  liveBadgeText: {
    color: '#15803D',
    fontSize: 11,
    fontWeight: '600',
  },
  headerSubtitle: {
    color: '#64748B',
    fontSize: 12,
    marginTop: 1,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  iconBtn: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: '#F0F4FA',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#D0E1FD',
  },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: '#F8FAFC',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  contextBar: {
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
    marginBottom: 4,
  },
  contextText: {
    fontSize: 12,
    color: '#0D3B8E',
    fontWeight: '600',
  },
  chatArea: {
    flex: 1,
  },
  chatContent: {
    paddingVertical: 12,
    gap: 12,
  },
  messageRow: {
    flexDirection: 'row',
    marginVertical: 4,
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  aiRow: {
    justifyContent: 'flex-start',
  },
  bubble: {
    maxWidth: '88%',
    borderRadius: 12,
    padding: 14,
  },
  userBubble: {
    backgroundColor: '#F0F4FA',
    borderWidth: 1,
    borderColor: '#C6D9FA',
    borderLeftWidth: 3,
    borderLeftColor: '#0D3B8E',
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderBottomLeftRadius: 4,
  },
  bubbleText: {
    fontSize: 14,
    lineHeight: 20,
  },
  userBubbleText: {
    color: '#0D3B8E',
    fontWeight: '500',
  },
  aiBubbleText: {
    color: '#0F2747',
    fontWeight: '400',
  },
  timestamp: {
    fontSize: 10,
    marginTop: 6,
    alignSelf: 'flex-end',
  },
  userTimestamp: {
    color: '#64748B',
  },
  aiTimestamp: {
    color: '#94A3B8',
  },
  kpiContainer: {
    marginTop: 10,
    gap: 8,
  },
  kpiCard: {
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderLeftWidth: 3.5,
    borderLeftColor: '#0D3B8E',
  },
  kpiTitle: {
    fontSize: 11,
    fontWeight: '600',
    color: '#64748B',
    textTransform: 'uppercase',
  },
  kpiValue: {
    fontSize: 18,
    fontWeight: '800',
    color: '#0D3B8E',
    marginVertical: 2,
  },
  kpiSubtext: {
    fontSize: 11,
    color: '#64748B',
  },
  tableContainer: {
    marginTop: 10,
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    overflow: 'hidden',
  },
  tableTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0D3B8E',
    padding: 10,
    backgroundColor: '#F0F4FA',
    borderBottomWidth: 1,
    borderBottomColor: '#D0E1FD',
  },
  tableHeaderRow: {
    flexDirection: 'row',
    backgroundColor: '#F1F5F9',
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#E2E8F0',
  },
  tableHeaderCell: {
    flex: 1,
    fontSize: 11,
    fontWeight: '700',
    color: '#0D3B8E',
  },
  tableBodyRow: {
    flexDirection: 'row',
    paddingVertical: 8,
    paddingHorizontal: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F1F5F9',
  },
  tableBodyCell: {
    flex: 1,
    fontSize: 11,
    color: '#0F2747',
  },
  chartContainer: {
    marginTop: 10,
    backgroundColor: '#F8FAFC',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  chartTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0D3B8E',
    marginBottom: 8,
  },
  barRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 4,
    gap: 8,
  },
  barLabel: {
    width: 90,
    fontSize: 11,
    color: '#475569',
  },
  barTrack: {
    flex: 1,
    height: 6,
    backgroundColor: '#E2E8F0',
    borderRadius: 3,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    backgroundColor: '#0D3B8E',
    borderRadius: 3,
  },
  barValue: {
    width: 50,
    fontSize: 11,
    fontWeight: '700',
    color: '#0D3B8E',
    textAlign: 'right',
  },
  loadingRow: {
    flexDirection: 'row',
    marginVertical: 6,
  },
  loadingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 10,
    gap: 8,
  },
  loadingText: {
    fontSize: 13,
    color: '#0D3B8E',
    fontWeight: '600',
  },
  suggestedSection: {
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: '#F1F5F9',
  },
  suggestedLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: '#0D3B8E',
    marginBottom: 8,
  },
  suggestedScroll: {
    flexDirection: 'row',
  },
  suggestedCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#D0E1FD',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    marginRight: 8,
    gap: 6,
  },
  suggestedDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: '#0D3B8E',
  },
  suggestedText: {
    fontSize: 12,
    color: '#0D3B8E',
    fontWeight: '600',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1.5,
    borderColor: '#D0E1FD',
    borderRadius: 14,
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginVertical: 6,
    gap: 8,
    shadowColor: '#0D3B8E',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  voiceBtn: {
    width: 32,
    height: 32,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  voiceBtnActive: {
    backgroundColor: '#F0F4FA',
  },
  input: {
    flex: 1,
    fontSize: 14,
    color: '#0F2747',
    paddingVertical: 4,
  },
  sendBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#0D3B8E',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: '#94A3B8',
  },
  footerRow: {
    alignItems: 'center',
    paddingTop: 2,
  },
  footerNote: {
    fontSize: 11,
    color: '#94A3B8',
  },
});
