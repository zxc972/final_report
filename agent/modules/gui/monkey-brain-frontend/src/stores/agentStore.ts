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

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { Message, Conversation, ConversationContext, AgentUpdate } from '../types/agent';
import { agentService } from '../services/agentService';
import { getSessionId } from '../services/session';

interface AgentState {
  currentConversation: Conversation | null;
  messages: Message[];
  conversationHistory: Conversation[];
  isLoading: boolean;
  isConnected: boolean;
  searchQuery: string;
  filteredMessages: Message[];
  streamingMessageId: string | null;
  /** Text to place in the composer, e.g. from a suggested prompt. */
  draft: string | null;
  
  // Actions
  setDraft: (draft: string | null) => void;
  addMessage: (message: Omit<Message, 'id' | 'timestamp'>) => void;
  updateStreamingMessage: (messageId: string, content: string) => void;
  setStreamingMessageId: (messageId: string | null) => void;
  setLoading: (loading: boolean) => void;
  setConnected: (connected: boolean) => void;
  clearMessages: () => void;
  createNewConversation: () => void;
  saveConversation: () => void;
  loadConversation: (conversationId: string) => void;
  searchMessages: (query: string) => void;
  clearSearch: () => void;
  updateConversationContext: (context: Partial<ConversationContext>) => void;
  deleteConversation: (conversationId: string) => void;
  initializeAgentService: () => void;
}

/** The UI history ID and server conversation ID are intentionally distinct. */
export function restoreSavedConversation(conversation: Conversation | null): void {
  const fromPlan = conversation?.messages.find((message) => message.metadata?.analysis)?.metadata?.analysis?.conversationId;
  const backendId = conversation?.context.backendConversationId ?? fromPlan ?? null;
  agentService.restoreConversation(backendId, conversation?.messages ?? []);
}

export const useAgentStore = create<AgentState>()(
  persist(
    (set, get) => ({
      currentConversation: null,
      messages: [],
      conversationHistory: [],
      isLoading: false,
      isConnected: false,
      searchQuery: '',
      filteredMessages: [],
      streamingMessageId: null,
      draft: null,

      setDraft: (draft) => set({ draft }),

      updateStreamingMessage: (messageId, content) => {
        set((state) => {
          const updatedMessages = state.messages.map(msg => 
            msg.id === messageId ? { ...msg, content } : msg
          );
          return {
            messages: updatedMessages,
            filteredMessages: state.searchQuery 
              ? updatedMessages.filter(msg => 
                  msg.content.toLowerCase().includes(state.searchQuery.toLowerCase())
                )
              : updatedMessages,
          };
        });
      },

      setStreamingMessageId: (messageId) => set({ streamingMessageId: messageId }),

      addMessage: (message) => {
        const newMessage: Message = {
          ...message,
          id: `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          timestamp: new Date(),
        };
        
        set((state) => {
          const updatedMessages = [...state.messages, newMessage];
          const updatedConversation = state.currentConversation ? {
            ...state.currentConversation,
            messages: updatedMessages,
            updatedAt: new Date(),
          } : null;

          return {
            messages: updatedMessages,
            currentConversation: updatedConversation,
            filteredMessages: state.searchQuery 
              ? updatedMessages.filter(msg => 
                  msg.content.toLowerCase().includes(state.searchQuery.toLowerCase())
                )
              : updatedMessages,
          };
        });
      },

      setLoading: (loading) => set({ isLoading: loading }),
      
      setConnected: (connected) => set({ isConnected: connected }),
      
      clearMessages: () => set({ 
        messages: [], 
        filteredMessages: [],
        currentConversation: null 
      }),
      
      createNewConversation: () => {
        const newConversation: Conversation = {
          id: `conv_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
          userId: getSessionId(),
          messages: [],
          context: {},
          createdAt: new Date(),
          updatedAt: new Date(),
        };
        
        set({ 
          currentConversation: newConversation, 
          messages: [],
          filteredMessages: [],
          searchQuery: ''
        });
      },

      saveConversation: () => {
        const state = get();
        if (!state.currentConversation || state.messages.length === 0) return;

        const conversationToSave = {
          ...state.currentConversation,
          context: { ...state.currentConversation.context, backendConversationId: agentService.getConversationId() ?? state.currentConversation.context.backendConversationId },
          messages: [...state.messages], // Create a copy to avoid reference issues
          updatedAt: new Date(),
        };

        // Use a simple update without triggering re-renders
        const existingIndex = state.conversationHistory.findIndex(
          conv => conv.id === conversationToSave.id
        );

        const updatedHistory = existingIndex >= 0
          ? state.conversationHistory.map((conv, index) =>
              index === existingIndex ? conversationToSave : conv
            )
          : [...state.conversationHistory, conversationToSave];

        // Only update history, don't touch current conversation or messages
        set({ conversationHistory: updatedHistory, currentConversation: conversationToSave });
      },

      loadConversation: (conversationId) => {
        const state = get();
        const conversation = state.conversationHistory.find(
          conv => conv.id === conversationId
        );

        if (conversation) {
          restoreSavedConversation(conversation);
          set({
            currentConversation: conversation,
            messages: conversation.messages,
            filteredMessages: state.searchQuery 
              ? conversation.messages.filter(msg => 
                  msg.content.toLowerCase().includes(state.searchQuery.toLowerCase())
                )
              : conversation.messages,
          });
        }
      },

      searchMessages: (query) => {
        const state = get();
        const filtered = query.trim()
          ? state.messages.filter(msg => 
              msg.content.toLowerCase().includes(query.toLowerCase())
            )
          : state.messages;

        set({
          searchQuery: query,
          filteredMessages: filtered,
        });
      },

      clearSearch: () => {
        const state = get();
        set({
          searchQuery: '',
          filteredMessages: state.messages,
        });
      },

      updateConversationContext: (context) => {
        set((state) => {
          if (!state.currentConversation) return state;

          const updatedConversation = {
            ...state.currentConversation,
            context: { ...state.currentConversation.context, ...context },
            updatedAt: new Date(),
          };

          return {
            currentConversation: updatedConversation,
          };
        });
      },

      deleteConversation: (conversationId) => {
        set((state) => ({
          conversationHistory: state.conversationHistory.filter(
            conv => conv.id !== conversationId
          ),
          ...(state.currentConversation?.id === conversationId && {
            currentConversation: null,
            messages: [],
            filteredMessages: [],
          }),
        }));
      },

      initializeAgentService: () => {
        // Subscribe to agent service updates
        agentService.subscribeToUpdates((update: AgentUpdate) => {
          
          switch (update.type) {
            case 'status':
              if (update.data.connected !== undefined) {
                set({ isConnected: update.data.connected });
              }
              break;
              
            case 'progress':
              // Handle progress updates
              set((prevState) => ({
                messages: [...prevState.messages, {
                  id: `progress_${Date.now()}`,
                  type: 'system' as const,
                  content: `Job Process: ${update.data.progress || 0}%`,
                  timestamp: update.timestamp,
                  metadata: {
                    taskId: update.data.taskId,
                  },
                }],
              }));
              break;
              
            case 'error':
              // Handle error updates
              set((prevState) => ({
                messages: [...prevState.messages, {
                  id: `error_${Date.now()}`,
                  type: 'system' as const,
                  content: `Error: ${update.data.message || 'Unknown error'}`,
                  timestamp: update.timestamp,
                }],
              }));
              break;
              
            default:
              break;
          }
        });

        // Set initial connection status
        set({ isConnected: agentService.isConnected() });
      },
    }),
    {
      name: 'agent-store',
      onRehydrateStorage: () => (state) => {
        restoreSavedConversation(state?.currentConversation ?? null);
      },
      partialize: (state) => ({
        conversationHistory: state.conversationHistory,
        currentConversation: state.currentConversation,
        messages: state.messages,
      }),
    }
  )
);
