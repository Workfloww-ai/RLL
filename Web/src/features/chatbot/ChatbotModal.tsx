/**
 * Web Chatbot Modal Component.
 * UI container for RLL Sales AI Chatbot in Web application.
 */

import React from 'react';

interface ChatbotModalProps {
  isOpen: boolean;
  onClose: () => void;
  period?: string;
  selectedHq?: string;
}

export const ChatbotModal: React.FC<ChatbotModalProps> = ({ isOpen, onClose, period, selectedHq }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-2xl bg-[#0F172A] p-6 text-white shadow-xl">
        <h2 className="text-lg font-bold">RLL Sales AI</h2>
      </div>
    </div>
  );
};
