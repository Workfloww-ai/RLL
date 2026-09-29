/**
 * Mobile Sales Analytics Chatbot Modal Component.
 * Implements the RLL Sales AI interface matching enterprise design specs.
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
        '👋 Welcome to RLL Sales AI!\n\n' +
        'I can analyze and summarize real-time sales across Rajasthan Liquors Limited.\n\n' +
        '• "Summarise total sales for Daily"\n' +
        '• "What are the top 5 selling brands?"\n' +
        '• "Who is the leading TSM in Rajasthan?"\n' +
        '• "How is Pernod Ricard performing?"',
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      suggestedQuestions: [
        'Full Sales Summary',
        'Top 5 Brands',
        'Top Depots',
        'Company Market Share',
        'Top Gainers & Losers',
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
        text: `⚠️ **Unable to retrieve sales data**: ${err.message || 'Please check network connection.'}`,
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
          '👋Welcome back to RLL Sales AI!\n\n' +
          'How can I help with your sales analysis today?',
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        suggestedQuestions: [
          'Full Sales Summary',
          'Top 5 Brands',
          'Top Depots',
          'Company Market Share',
        ],
      },
    ]);
  };

  const promptPills = [
    '📊 Full Sales Summary',
    '🍾 Top 5 Brands',
    '🏢 Top Depots',
    '💼 Company Market Share',
    '🚀 Top Gainers & Losers',
  ];

  if (!visible) return null;

  return (
    <Modal visible={visible} animationType="slide" transparent={true} onRequestClose={onClose}>
      <View style={styles.overlay}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.modalCard}
        >
          {/* Header */}
          <View style={styles.header}>
            <View style={styles.headerLeft}>
              <View style={styles.aiBadgeIcon}>
                <Text style={styles.aiBadgeStar}>✨</Text>
              </View>
              <View>
                <View style={styles.titleRow}>
                  <Text style={styles.headerTitle}>RLL Sales AI</Text>
                  <View style={styles.liveBadge}>
                    <View style={styles.liveDot} />
                    <Text style={styles.liveBadgeText}>Live Data</Text>
                  </View>
                </View>
                <Text style={styles.headerSubtitle}>
                  Context: <Text style={styles.boldSubtitle}>{period}</Text> •{' '}
                  <Text style={styles.boldSubtitle}>{selectedHq}</Text>
                </Text>
              </View>
            </View>

            <View style={styles.headerActions}>
              <TouchableOpacity onPress={handleReset} style={styles.iconBtn}>
                <Text style={styles.iconBtnText}>🔄</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                <Text style={styles.closeBtnText}>✕</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Chat Messages */}
          <ScrollView
            ref={scrollViewRef}
            style={styles.chatArea}
            contentContainerStyle={styles.chatContent}
            showsVerticalScrollIndicator={false}
          >
            {messages.map((msg) => (
              <View
                key={msg.id}
                style={[
                  styles.messageRow,
                  msg.sender === 'user' ? styles.userRow : styles.aiRow,
                ]}
              >
                {msg.sender === 'ai' && (
                  <View style={styles.avatar}>
                    <Text style={styles.avatarIcon}>🤖</Text>
                  </View>
                )}

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

                  <Text style={styles.timestamp}>{msg.time}</Text>
                </View>
              </View>
            ))}

            {loading && (
              <View style={styles.loadingRow}>
                <View style={styles.avatar}>
                  <Text style={styles.avatarIcon}>🤖</Text>
                </View>
                <View style={styles.loadingBubble}>
                  <ActivityIndicator size="small" color="#38BDF8" />
                  <Text style={styles.loadingText}>Analyzing sales data...</Text>
                </View>
              </View>
            )}
          </ScrollView>

          {/* Quick Prompt Pills */}
          <View style={styles.promptsSection}>
            <Text style={styles.promptsLabel}>PROMPTS:</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.pillsScroll}>
              {promptPills.map((pill, pIdx) => {
                const cleanText = pill.replace(/^[^\s]+\s+/, '');
                return (
                  <TouchableOpacity
                    key={pIdx}
                    style={styles.pillBtn}
                    onPress={() => handleSend(cleanText)}
                  >
                    <Text style={styles.pillText}>{pill}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>

          {/* Input Bar */}
          <View style={styles.inputContainer}>
            <TouchableOpacity
              style={[styles.voiceBtn, isDictating && styles.voiceBtnActive]}
              onPress={() => setIsDictating(!isDictating)}
            >
              <Text style={styles.voiceIcon}>🎤</Text>
            </TouchableOpacity>

            <TextInput
              style={styles.input}
              placeholder='Ask a sales question or type "summarise"...'
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
            >
              <Text style={styles.sendIcon}>➔</Text>
            </TouchableOpacity>
          </View>

          {/* Footer note */}
          <View style={styles.footerRow}>
            <Text style={styles.footerNote}>Supports voice dictation & text questions</Text>
            <Text style={styles.footerModel}>Model: Gemini 3.8 Flash</Text>
          </View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.65)',
    justifyContent: 'flex-end',
  },
  modalCard: {
    height: '92%',
    backgroundColor: '#0B132B',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingTop: 16,
    paddingHorizontal: 16,
    paddingBottom: 10,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1E293B',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  aiBadgeIcon: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: '#1E293B',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#38BDF8',
  },
  aiBadgeStar: {
    fontSize: 20,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitle: {
    color: '#FFFFFF',
    fontSize: 17,
    fontWeight: '800',
  },
  liveBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(16, 185, 129, 0.15)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 12,
    gap: 4,
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#10B981',
  },
  liveBadgeText: {
    color: '#10B981',
    fontSize: 11,
    fontWeight: '700',
  },
  headerSubtitle: {
    color: '#94A3B8',
    fontSize: 12,
  },
  boldSubtitle: {
    color: '#F59E0B',
    fontWeight: '700',
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  iconBtn: {
    padding: 8,
    backgroundColor: '#1E293B',
    borderRadius: 10,
  },
  iconBtnText: {
    fontSize: 14,
  },
  closeBtn: {
    padding: 8,
    backgroundColor: '#1E293B',
    borderRadius: 10,
  },
  closeBtnText: {
    color: '#94A3B8',
    fontSize: 16,
    fontWeight: 'bold',
  },
  chatArea: {
    flex: 1,
    marginVertical: 10,
  },
  chatContent: {
    paddingBottom: 16,
  },
  messageRow: {
    flexDirection: 'row',
    marginVertical: 8,
    alignItems: 'flex-end',
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  aiRow: {
    justifyContent: 'flex-start',
    gap: 8,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: '#1E293B',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarIcon: {
    fontSize: 16,
  },
  bubble: {
    maxWidth: '85%',
    borderRadius: 18,
    padding: 14,
  },
  userBubble: {
    backgroundColor: '#2563EB',
    borderBottomRightRadius: 4,
  },
  aiBubble: {
    backgroundColor: '#1E293B',
    borderBottomLeftRadius: 4,
  },
  bubbleText: {
    fontSize: 14,
    lineHeight: 20,
  },
  userBubbleText: {
    color: '#FFFFFF',
  },
  aiBubbleText: {
    color: '#F8FAFC',
  },
  timestamp: {
    fontSize: 10,
    color: '#64748B',
    marginTop: 6,
    alignSelf: 'flex-end',
  },
  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 8,
    gap: 8,
  },
  loadingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1E293B',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
    gap: 8,
  },
  loadingText: {
    color: '#94A3B8',
    fontSize: 13,
  },
  kpiContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 10,
  },
  kpiCard: {
    flex: 1,
    minWidth: 100,
    backgroundColor: '#0F172A',
    borderRadius: 12,
    padding: 10,
    borderWidth: 1,
    borderColor: '#334155',
  },
  kpiTitle: {
    color: '#94A3B8',
    fontSize: 10,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  kpiValue: {
    color: '#38BDF8',
    fontSize: 16,
    fontWeight: '900',
    marginTop: 2,
  },
  kpiSubtext: {
    color: '#64748B',
    fontSize: 10,
  },
  tableContainer: {
    marginTop: 10,
    backgroundColor: '#d7dbe2ff',
    borderRadius: 12,
    padding: 10,
    borderWidth: 1,
    borderColor: '#334155',
  },
  tableTitle: {
    color: '#F59E0B',
    fontSize: 12,
    fontWeight: '800',
    marginBottom: 8,
  },
  tableHeaderRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderBottomColor: '#334155',
    paddingBottom: 6,
  },
  tableHeaderCell: {
    flex: 1,
    color: '#94A3B8',
    fontSize: 10,
    fontWeight: '700',
  },
  tableBodyRow: {
    flexDirection: 'row',
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: '#1E293B',
  },
  tableBodyCell: {
    flex: 1,
    color: '#F1F5F9',
    fontSize: 11,
  },
  chartContainer: {
    marginTop: 10,
    backgroundColor: '#0F172A',
    borderRadius: 12,
    padding: 10,
    borderWidth: 1,
    borderColor: '#334155',
  },
  chartTitle: {
    color: '#38BDF8',
    fontSize: 12,
    fontWeight: '800',
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
    color: '#CBD5E1',
    fontSize: 10,
  },
  barTrack: {
    flex: 1,
    height: 8,
    backgroundColor: '#1E293B',
    borderRadius: 4,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    backgroundColor: '#38BDF8',
    borderRadius: 4,
  },
  barValue: {
    width: 50,
    color: '#38BDF8',
    fontSize: 10,
    fontWeight: '700',
    textAlign: 'right',
  },
  promptsSection: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 8,
    gap: 8,
  },
  promptsLabel: {
    color: '#64748B',
    fontSize: 11,
    fontWeight: '800',
  },
  pillsScroll: {
    flex: 1,
  },
  pillBtn: {
    backgroundColor: '#1E293B',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    marginRight: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  pillText: {
    color: '#F1F5F9',
    fontSize: 12,
    fontWeight: '600',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1E293B',
    borderRadius: 20,
    paddingHorizontal: 10,
    height: 48,
    gap: 8,
  },
  voiceBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: '#0F172A',
    justifyContent: 'center',
    alignItems: 'center',
  },
  voiceBtnActive: {
    backgroundColor: '#EF4444',
  },
  voiceIcon: {
    fontSize: 16,
  },
  input: {
    flex: 1,
    color: '#FFFFFF',
    fontSize: 13,
    paddingVertical: 0,
  },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#2563EB',
    justifyContent: 'center',
    alignItems: 'center',
  },
  sendBtnDisabled: {
    backgroundColor: '#334155',
  },
  sendIcon: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: 'bold',
  },
  footerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: 6,
    paddingHorizontal: 4,
  },
  footerNote: {
    color: '#64748B',
    fontSize: 10,
  },
  footerModel: {
    color: '#64748B',
    fontSize: 10,
    fontWeight: '600',
  },
});
