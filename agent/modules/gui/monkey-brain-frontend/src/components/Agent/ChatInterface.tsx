/*
 * Copyright (C) 2026 Wang Zheng Lab, Peking University
 *
 * This file is part of PrimateX.
 *
 * PrimateX is free software: you can redistribute it and/or modify it under the
 * terms of the GNU Affero General Public License as published by the Free
 * Software Foundation, either version 3 of the License, or (at your option) any
 * later version.
 *
 * PrimateX is distributed in the hope that it will be useful, but WITHOUT ANY
 * WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
 * A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
 * details.
 *
 * If you use PrimateX in academic work, please cite:
 * Xiaohui Yao*, Yichun Huang*, Kailong Cui*, ..., Shan Cong#, Zheng Wang#.
 * Multi-agentic routing with PrimateX: standardized structural MRI analysis
 * for non-human primates and humans.
 *
 * * Equal contribution.
 * Correspondence (#): Shan Cong (shan.cong@hrbeu.edu.cn), Zheng Wang
 * (zheng.wang@pku.edu.cn).
 *
 * See CITATION.cff for full citation details.
 */

import React, { useEffect, useRef, useState } from 'react';
import { Button, Space } from 'antd';
import { HistoryOutlined, SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import { useAgentStore } from '../../stores/agentStore';
import { useConfigStore } from '../../stores/configStore';
import MessageBubble from './MessageBubble.tsx';
import InputArea from './InputArea.tsx';
import ConversationHistory from './ConversationHistory';
import MessageSearch from './MessageSearch';

const ChatInterface: React.FC = () => {
  const {
    messages,
    isLoading,
    isConnected,
    createNewConversation,
    currentConversation,
    initializeAgentService,
    clearMessages,
    streamingMessageId
  } = useAgentStore();
  const { config } = useConfigStore();
  const hasUserId = !!(config?.userId);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [isConfigured, setIsConfigured] = useState(false);
  const [isCheckingApiKey, setIsCheckingApiKey] = useState(true);

  // Auto-scroll to bottom when new messages arrive
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  // Track previous message count to only scroll on new messages
  const prevMessageCountRef = useRef(0);
  
  // Function to scroll to the bottom
  const scrollToBottom = () => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  };

  // Listen for message changes and auto-scroll to bottom
  useEffect(() => {
    // When new messages arrive, scroll to bottom
    if (messages.length > prevMessageCountRef.current && shouldAutoScroll) {
      setTimeout(() => {
        scrollToBottom();
      }, 100); // Delay slightly to ensure DOM updates
    }
    prevMessageCountRef.current = messages.length;
  }, [messages.length, shouldAutoScroll]);

  // Listen for streaming message updates and auto-scroll
  useEffect(() => {
    if (streamingMessageId && shouldAutoScroll) {
      // Scroll when streaming message updates
      setTimeout(() => {
        scrollToBottom();
      }, 50); // Shorter delay for smoother scrolling
    }
  }, [streamingMessageId, shouldAutoScroll]);

  // Listen for message content changes (especially streaming message content)
  useEffect(() => {
    if (streamingMessageId && shouldAutoScroll) {
      // Find streaming message and listen for its content changes
      const streamingMessage = messages.find(msg => msg.id === streamingMessageId);
      if (streamingMessage) {
        // Scroll to bottom when content updates
        setTimeout(() => {
          scrollToBottom();
        }, 10); // Very short delay for immediate scrolling
      }
    }
  }, [messages, streamingMessageId, shouldAutoScroll]);

  // Scroll to bottom on initial load
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(() => {
        scrollToBottom();
      }, 200);
    }
  }, []);

  // Check if user is scrolled to bottom to determine auto-scroll behavior
  const handleScroll = () => {
    if (messagesContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50; // 50px threshold
      setShouldAutoScroll(isAtBottom);
    }
  };

  // Initialize agent service and check API key
  useEffect(() => {
    const initializeAndCheckApiKey = async () => {
      setIsCheckingApiKey(true);
      
      try {
        // Initialize agent service
        initializeAgentService();

        // Import and check configuration
        const { agentService } = await import('../../services/agentService');
        setIsConfigured(agentService.isConfigured());
      } catch (error) {
        console.error('Failed to initialize Agent service:', error);
        setIsConfigured(false);
      } finally {
        setIsCheckingApiKey(false);
      }
    };

    initializeAndCheckApiKey();
  }, [initializeAgentService]);

  // Listen for configuration changes
  useEffect(() => {
    const checkConfig = async () => {
      try {
        const { agentService } = await import('../../services/agentService');
        setIsConfigured(agentService.isConfigured());
      } catch (error) {
        console.error('Failed to check agent configuration:', error);
        setIsConfigured(false);
      }
    };

    // Periodically check configuration status
    const interval = setInterval(checkConfig, 3000);
    return () => clearInterval(interval);
  }, []);

  // Initialize conversation when user is available
  useEffect(() => {
    if (!currentConversation) {
      createNewConversation();
    }
  }, [currentConversation, createNewConversation]);

  // Auto-save conversation periodically with proper dependency management
  useEffect(() => {
    if (currentConversation?.id && messages.length > 0) {
      const saveInterval = setInterval(() => {
        // Use the store's saveConversation method directly
        useAgentStore.getState().saveConversation();
      }, 30000); // Save every 30 seconds

      return () => clearInterval(saveInterval);
    }
  }, [currentConversation?.id, messages.length]);

  // Save conversation when component unmounts
  useEffect(() => {
    return () => {
      if (currentConversation?.id && messages.length > 0) {
        useAgentStore.getState().saveConversation();
      }
    };
  }, []);

  const handleResetChat = () => {
    clearMessages();
    createNewConversation();
    // Clear agent service chat history
    import('../../services/agentService').then(({ agentService }) => {
      agentService.clearChatHistory();
    });
  };

  return (
    <div className="h-full w-full flex flex-col bg-white relative">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b bg-gradient-to-r from-blue-600 to-purple-600 text-white">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold flex items-center">
            🧠 PrimateX Assistant
          </h2>
          <div className="flex items-center space-x-4">
            {/* Action Buttons */}
            <Space>
              <Button
                type="text"
                icon={<HistoryOutlined />}
                onClick={() => setShowHistory(true)}
                title="Conversation History"
                disabled={!isConfigured}
              />
              <Button
                type="text"
                icon={<SearchOutlined />}
                onClick={() => setShowSearch(true)}
                title="Search Messages"
                disabled={!isConfigured}
              />
              <Button
                type="text"
                icon={<ReloadOutlined />}
                onClick={handleResetChat}
                title="Reset Conversation"
                disabled={!isConfigured}
              />
            </Space>
            
            {/* Connection Status */}
            <div className="flex items-center space-x-2">
              <div 
                className={`w-2 h-2 rounded-full ${
                  isConnected && isConfigured ? 'bg-green-400' : 'bg-red-400'
                }`}
              />
              <span className="text-sm text-white">
                {isConnected && isConfigured ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Messages Area - Scrollable */}
      <div 
        ref={messagesContainerRef}
        className="flex-1 overflow-y-auto bg-white"
        onScroll={handleScroll}
        style={{ 
          minHeight: 0,
          maxHeight: 'calc(100vh - 200px)' // Ensure a clear maximum height
        }}
      >
        <div className="max-w-4xl mx-auto px-4 py-6 space-y-6 min-h-full flex flex-col">
          {isCheckingApiKey ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-gray-500">
                <div className="mb-6">
                  <div className="text-6xl mb-4">🔄</div>
                  <div className="text-2xl font-bold text-gray-700 mb-2">Initializing...</div>
                  <div className="text-lg text-gray-600">
                    Checking API key configuration
                  </div>
                </div>
              </div>
            </div>
          ) : !hasUserId ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-gray-500">
                <div className="mb-6">
                  <div className="text-6xl mb-4">👤</div>
                  <div className="text-2xl font-bold text-gray-700 mb-2">Please set a User ID first</div>
                  <div className="text-lg text-gray-600 mb-6">
                    Go to the Configuration page and set your User ID before using the Workflow Assistant.
                  </div>
                </div>
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-2xl p-6 max-w-lg mx-auto">
                  <div className="text-sm text-gray-600">
                    A User ID is required so that pipeline outputs are stored under your own directory and tasks can be tracked correctly.
                  </div>
                </div>
              </div>
            </div>
          ) : !isConfigured ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-gray-500">
                <div className="mb-6">
                  <div className="text-6xl mb-4">🔑</div>
                  <div className="text-2xl font-bold text-gray-700 mb-2">Please choose a model first</div>
                  <div className="text-lg text-gray-600 mb-6">
                    Go to the Configuration page and either pick a built-in platform model, or enter your own API key.
                  </div>
                </div>

                <div className="bg-gradient-to-r from-yellow-50 to-orange-50 rounded-2xl p-6 max-w-lg mx-auto">
                  <div className="text-sm font-semibold text-gray-700 mb-3">📝 Two ways to get started:</div>
                  <div className="text-sm text-gray-600 space-y-2">
                    <div>1. Pick a model from the built-in platform list (no key needed)</div>
                    <div>2. Or enter your own API key, base URL, and model name</div>
                  </div>
                </div>
              </div>
            </div>
          ) : messages.length === 0 ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center text-gray-500">
                <div className="mb-6">
                  <div className="text-6xl mb-4">🧠</div>
                  <div className="text-2xl font-bold text-gray-700 mb-2">Welcome to the PrimateX preprocessing and cortical reconstruction workflow</div>
                  <div className="text-lg text-gray-600 mb-6">
                    You can use natural language to interact with me to accomplish brain segmentation tasks.
                  </div>
                </div>
                
                <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-2xl p-6 max-w-2xl mx-auto">
                  <div className="text-sm font-semibold text-gray-700 mb-4">💡 You can try asking:</div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                    <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-200">
                      "How do I start brain segmentation?"
                    </div>
                    <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-200">
                      "Load my MRI data"
                    </div>
                    <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-200">
                      "Show me the segmentation results"
                    </div>
                    <div className="bg-white rounded-lg p-3 shadow-sm border border-gray-200">
                      "What features does this system provide?"
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <>
              <div className="space-y-6">
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} />
                ))}
                
                {/* Loading indicator */}
                {isLoading && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 rounded-lg px-4 py-2 max-w-xs">
                      <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }}></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                      </div>
                    </div>
                  </div>
                )}
                
                <div ref={messagesEndRef} />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Input Area - Fixed at bottom */}
      <div className="flex-shrink-0 border-t bg-white shadow-lg">
        <div className="max-w-4xl mx-auto">
          <InputArea disabled={!isConfigured || !hasUserId} />
        </div>
      </div>

      {/* Message Search Overlay */}
      <MessageSearch 
        visible={showSearch} 
        onClose={() => setShowSearch(false)} 
      />

      {/* Conversation History Drawer */}
      <ConversationHistory
        visible={showHistory}
        onClose={() => setShowHistory(false)}
      />
    </div>
  );
};

export default ChatInterface;
