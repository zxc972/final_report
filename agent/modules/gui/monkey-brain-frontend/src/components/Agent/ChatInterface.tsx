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
import { Button, Tooltip } from 'antd';
import {
  HistoryOutlined,
  SearchOutlined,
  PlusOutlined,
  ProfileOutlined,
  SettingOutlined,
  UserOutlined,
  KeyOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAgentStore } from '../../stores/agentStore';
import { useConfigStore } from '../../stores/configStore';
import { agentService } from '../../services/agentService';
import { buildPathWithToken } from '../../services/accessToken';
import MessageBubble from './MessageBubble.tsx';
import InputArea from './InputArea.tsx';
import ConversationHistory from './ConversationHistory';
import MessageSearch from './MessageSearch';
import ProcessPanel from './ProcessPanel';

/** Generic starting points; the assistant decides whether each needs preprocessing or analysis. */
const PROMPTS: string[] = [
  'Show me the sample subjects available on this server',
  'Preprocess and reconstruct the cortical surface for the T1 I just uploaded',
  'Summarise regional cortical thickness for each subject in my workspace',
  'Compare left and right hemisphere surface area across subjects',
  'Check whether a local gyrification index can be computed for my data',
  'Check the status of my running tasks',
];

const ChatInterface: React.FC = () => {
  const navigate = useNavigate();
  const { setDraft } = useAgentStore();
  const [showPanel, setShowPanel] = useState(true);
  const [backendConversationId, setBackendConversationId] = useState<string | null>(() => agentService.getConversationId());

  // agentService owns the backend conversation ID (created on first send,
  // cleared on reset or mode switch); mirror it for the process panel.
  useEffect(() => {
    const id = setInterval(() => {
      const current = agentService.getConversationId();
      setBackendConversationId((previous) => (previous === current ? previous : current));
    }, 1000);
    return () => clearInterval(id);
  }, []);

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

  const requestActive = isLoading || streamingMessageId !== null;
  const firstUserMessage = messages.find((m) => m.type === 'user')?.content ?? '';
  const subtitle = firstUserMessage.length > 60 ? firstUserMessage.slice(0, 60) + '…' : firstUserMessage;
  const ready = isConfigured && hasUserId;

  const applyPrompt = (prompt: string) => setDraft(prompt);

  const renderBlocker = (icon: React.ReactNode, title: string, text: string, showButton = true) => (
    <div className="px-blocker">
      <span className="px-blocker-icon">{icon}</span>
      <h2>{title}</h2>
      <p>{text}</p>
      {showButton && (
        <Button type="primary" icon={<SettingOutlined />} onClick={() => navigate(buildPathWithToken('/config'))}>
          Open Settings
        </Button>
      )}
    </div>
  );

  const renderBody = () => {
    if (isCheckingApiKey) {
      return (
        <div className="px-blocker">
          <span className="px-spin" style={{ width: 20, height: 20 }} />
          <h2>Connecting…</h2>
          <p>Checking the assistant configuration.</p>
        </div>
      );
    }
    if (!hasUserId) {
      return renderBlocker(<UserOutlined />, 'Set your User ID first',
        'Outputs are stored under your own workspace directory, so the assistant needs a verified User ID.');
    }
    if (!isConfigured) {
      return renderBlocker(<KeyOutlined />, 'Choose a model first',
        'Pick a built-in platform model, or enter your own API key, base URL and model name in Settings.');
    }
    if (messages.length === 0) {
      return (
        <div className="px-empty">
          <h2>What would you like to do?</h2>
          <p>Ask in plain language. The assistant decides whether a request needs PrimateX preprocessing or new analysis code, and shows every step it takes in Run details.</p>
          <div className="px-empty-groups">
            {PROMPTS.map((item) => (
              <button key={item} type="button" className="px-empty-prompt" onClick={() => applyPrompt(item)}>
                {item}
              </button>
            ))}
          </div>
        </div>
      );
    }
    return (
      <div className="px-thread">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={messagesEndRef} />
      </div>
    );
  };

  return (
    <div className="px-main" style={{ height: '100%' }}>
      <div className="px-topbar">
        <h1>Assistant</h1>
        {subtitle && <span className="px-topbar-sub" title={firstUserMessage}>{subtitle}</span>}
        <div className="px-spacer" />
        <Tooltip title="Conversation history">
          <Button type="text" icon={<HistoryOutlined />} aria-label="Conversation history" onClick={() => setShowHistory(true)} disabled={!isConfigured} />
        </Tooltip>
        <Tooltip title="Search messages">
          <Button type="text" icon={<SearchOutlined />} aria-label="Search messages" onClick={() => setShowSearch(true)} disabled={!isConfigured} />
        </Tooltip>
        <Tooltip title="New conversation">
          <Button type="text" icon={<PlusOutlined />} aria-label="New conversation" onClick={handleResetChat} disabled={!isConfigured || requestActive} />
        </Tooltip>
        <Tooltip title={showPanel ? 'Hide run details' : 'Show run details'}>
          <Button
            type={showPanel ? 'default' : 'text'}
            icon={<ProfileOutlined />}
            aria-label={showPanel ? 'Hide run details' : 'Show run details'}
            aria-pressed={showPanel}
            onClick={() => setShowPanel((v) => !v)}
          />
        </Tooltip>
        <span className="px-chip" title={isConnected && isConfigured ? 'Connected' : 'Disconnected'}>
          <span className={`px-dot ${isConnected && isConfigured ? 'is-ok' : 'is-err'}`} />
          {isConnected && isConfigured ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      <div className={`px-workarea${showPanel ? '' : ' is-panel-hidden'}`}>
        <section className="px-chat" aria-label="Conversation">
          <div ref={messagesContainerRef} className="px-messages" onScroll={handleScroll}>
            {renderBody()}
          </div>
          <div className="px-composer">
            <InputArea disabled={!ready} />
          </div>
        </section>
        {showPanel && (
          <ProcessPanel
            conversationId={backendConversationId}
            active={requestActive}
            messages={messages}
            onClose={() => setShowPanel(false)}
          />
        )}
      </div>

      <MessageSearch visible={showSearch} onClose={() => setShowSearch(false)} />
      <ConversationHistory visible={showHistory} onClose={() => setShowHistory(false)} />
    </div>
  );
};

export default ChatInterface;
