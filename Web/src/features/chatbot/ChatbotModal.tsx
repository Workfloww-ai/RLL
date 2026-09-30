/**
 * Web Chatbot Modal Component.
 * Enterprise SaaS Chatbot UI with Signature RLL Navy (#0D3B8E) Brand Accent.
 */

import React, { useState, useRef, useEffect } from 'react';
import { X, RefreshCw, Send, Mic, Sparkles } from 'lucide-react';
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
  isOpen: boolean;
  onClose: () => void;
  period?: string;
  selectedHq?: string;
}

export const ChatbotModal: React.FC<ChatbotModalProps> = ({
  isOpen,
  onClose,
  period = 'Daily',
  selectedHq = 'All Headquarters',
}) => {
  const [inputQuery, setInputQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome_1',
      sender: 'ai',
      text:
        'RLL Sales AI\n\n' +
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

  const chatContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        chatContainerRef.current?.scrollTo({
          top: chatContainerRef.current.scrollHeight,
          behavior: 'smooth',
        });
      }, 150);
    }
  }, [isOpen, messages]);

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
          'RLL Sales AI\n\n' +
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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0F2747]/40 backdrop-blur-xs p-4">
      <div className="w-full max-w-xl rounded-2xl bg-white text-[#0F2747] shadow-2xl border border-slate-200 overflow-hidden flex flex-col h-[88vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 bg-white">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-[#0D3B8E] border border-blue-400 flex items-center justify-center text-[#FFD700] text-lg">
              ✨
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-[#0D3B8E]">RLL Sales AI</h2>
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                  Live
                </span>
              </div>
              <p className="text-xs text-slate-500">Live sales analytics</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="w-8 h-8 rounded-lg bg-[#F0F4FA] border border-[#D0E1FD] flex items-center justify-center text-[#0D3B8E] hover:text-[#0D3B8E] font-bold transition"
              title="Reset Chat"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="w-8 h-8 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-500 hover:text-slate-700 transition"
              title="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Context Bar */}
        <div className="px-6 py-2.5 bg-slate-50 border-b border-slate-100 text-xs text-[#0D3B8E] font-semibold">
          {period} &nbsp;·&nbsp; {selectedHq}
        </div>

        {/* Chat Messages */}
        <div ref={chatContainerRef} className="flex-1 overflow-y-auto p-6 space-y-4 bg-white">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[88%] rounded-xl p-4 text-sm ${
                  msg.sender === 'user'
                    ? 'bg-[#F0F4FA] border border-[#C6D9FA] border-l-4 border-l-[#0D3B8E] text-[#0D3B8E] font-medium rounded-br-xs'
                    : 'bg-white border border-slate-200 text-[#0F2747] rounded-bl-xs'
                }`}
              >
                <div className="whitespace-pre-wrap leading-relaxed">{msg.text}</div>

                {/* KPIs rendering */}
                {msg.kpis && msg.kpis.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {msg.kpis.map((k, idx) => (
                      <div key={idx} className="p-3 rounded-lg bg-slate-50 border border-slate-200 border-l-4 border-l-[#0D3B8E]">
                        <p className="text-[11px] font-semibold text-slate-500 uppercase">{k.title}</p>
                        <p className="text-lg font-extrabold text-[#0D3B8E] my-0.5">{k.value}</p>
                        {k.subtext && <p className="text-xs text-slate-500">{k.subtext}</p>}
                      </div>
                    ))}
                  </div>
                )}

                {/* Table rendering */}
                {msg.table && (
                  <div className="mt-3 rounded-lg bg-slate-50 border border-slate-200 overflow-hidden">
                    <p className="p-2.5 text-xs font-bold text-[#0D3B8E] bg-[#F0F4FA] border-b border-[#D0E1FD]">
                      {msg.table.title}
                    </p>
                    <table className="w-full text-xs text-left">
                      <thead className="bg-slate-100 border-b border-slate-200 text-[#0D3B8E] font-bold">
                        <tr>
                          {msg.table.columns.map((col) => (
                            <th
                              key={col.key}
                              className={`p-2 ${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'}`}
                            >
                              {col.label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {msg.table.rows.map((row, rIdx) => (
                          <tr key={rIdx}>
                            {msg.table!.columns.map((col) => (
                              <td
                                key={col.key}
                                className={`p-2 ${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'}`}
                              >
                                {row[col.key]}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Chart rendering */}
                {msg.chart && msg.chart.data && (
                  <div className="mt-3 p-3 rounded-lg bg-slate-50 border border-slate-200">
                    <p className="text-xs font-bold text-[#0D3B8E] mb-2">{msg.chart.title}</p>
                    <div className="space-y-2">
                      {msg.chart.data.map((dp, dIdx) => {
                        const maxVal = Math.max(...msg.chart!.data.map((d) => d.value)) || 1;
                        const barPct = Math.min(100, Math.max(8, (dp.value / maxVal) * 100));
                        return (
                          <div key={dIdx} className="flex items-center gap-2 text-xs">
                            <span className="w-24 truncate text-slate-600">{dp.label}</span>
                            <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-[#0D3B8E] rounded-full"
                                style={{ width: `${barPct}%` }}
                              />
                            </div>
                            <span className="w-12 text-right font-bold text-[#0D3B8E]">
                              {dp.value.toLocaleString()}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                <p className={`text-[10px] mt-2 text-right ${msg.sender === 'user' ? 'text-slate-500' : 'text-slate-400'}`}>
                  {msg.time}
                </p>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-50 border border-slate-200 text-xs font-semibold text-[#0D3B8E]">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#0D3B8E]" />
                <span>Analyzing sales data...</span>
              </div>
            </div>
          )}
        </div>

        {/* Suggested Questions */}
        <div className="px-6 py-3 border-t border-slate-100 bg-white">
          <p className="text-xs font-bold text-[#0D3B8E] mb-2">Suggested questions</p>
          <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar">
            {suggestedQuestionsList.map((qText, qIdx) => (
              <button
                key={qIdx}
                onClick={() => handleSend(qText)}
                className="whitespace-nowrap px-3 py-1.5 rounded-lg border border-[#D0E1FD] bg-white hover:bg-slate-50 text-xs font-semibold text-[#0D3B8E] flex items-center gap-1.5 transition"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-[#0D3B8E]" />
                {qText}
              </button>
            ))}
          </div>
        </div>

        {/* Input Bar */}
        <div className="p-4 border-t border-slate-100 bg-white">
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl border border-[#D0E1FD] bg-white shadow-xs focus-within:border-[#0D3B8E] transition">
            <button className="text-slate-400 hover:text-[#0D3B8E] transition">
              <Mic className="w-4 h-4" />
            </button>
            <input
              type="text"
              placeholder="Ask about sales..."
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              className="flex-1 text-sm text-[#0F2747] placeholder-slate-400 bg-transparent outline-none"
            />
            <button
              onClick={() => handleSend()}
              disabled={!inputQuery.trim() || loading}
              className="w-7 h-7 rounded-full bg-[#0D3B8E] disabled:bg-slate-300 flex items-center justify-center text-white transition"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
          <p className="text-[10px] text-center text-slate-400 mt-2">Powered by Gemini</p>
        </div>
      </div>
    </div>
  );
};
