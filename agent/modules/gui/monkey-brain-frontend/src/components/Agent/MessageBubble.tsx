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

import React from 'react';
import { Avatar, Button, Tag } from 'antd';
import { UserOutlined, RobotOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { Message } from '../../types/agent';
import { useAgentStore } from '../../stores/agentStore';
import { renderMarkdown } from '../../utils/markdownRenderer';
import AnalysisResultCard from './AnalysisResultCard';

interface MessageBubbleProps {
  message: Message;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.type === 'user';
  const isSystem = message.type === 'system';
  const { streamingMessageId } = useAgentStore();
  const isStreaming = streamingMessageId === message.id;
  
  const getAvatar = () => {
    if (isUser) {
      return <Avatar size="small" icon={<UserOutlined />} className="bg-blue-500" />;
    } else if (isSystem) {
      return <Avatar size="small" icon={<InfoCircleOutlined />} className="bg-orange-500" />;
    } else {
      return <Avatar size="small" icon={<RobotOutlined />} className="bg-green-500" />;
    }
  };

  const getBubbleStyle = () => {
    if (isUser) {
      return 'bg-gradient-to-r from-blue-500 to-purple-600 text-white ml-auto shadow-lg';
    } else if (isSystem) {
      return 'bg-orange-50 text-orange-800 border border-orange-200 shadow-sm';
    } else {
      return 'bg-white text-gray-800 border border-gray-200 shadow-sm';
    }
  };

  const handleActionClick = async (action: any) => {
    if (action.type === 'suggestion' && action.data?.suggestion) {
      const { addMessage, updateStreamingMessage, setStreamingMessageId } = useAgentStore.getState();
      
      try {
        // Send the suggestion as a user message
        addMessage({
          type: 'user',
          content: action.data.suggestion,
        });

        // Create a streaming message placeholder
        const streamingMessage = {
          type: 'agent' as const,
          content: 'Thinking...',
        };
        
        addMessage(streamingMessage);
        
        // Get the ID of the last message
        const messages = useAgentStore.getState().messages;
        const lastMessage = messages[messages.length - 1];
        const messageId = lastMessage.id;
        
        setStreamingMessageId(messageId);

        // Send the message with streaming output
        const { agentService } = await import('../../services/agentService');
        const response = await agentService.sendMessage(action.data.suggestion, undefined, (streamContent) => {
          // Update streaming message content in real time
          updateStreamingMessage(messageId, streamContent);
        });
        
        // Finally update the complete response
        updateStreamingMessage(messageId, response.message);
        
        // Update metadata (if any)
        if (response.metadata?.actions || response.metadata?.analysis) {
          const state = useAgentStore.getState();
          const updatedMessages = state.messages.map(msg => 
            msg.id === messageId 
              ? { ...msg, content: response.message, metadata: { actions: response.metadata?.actions || [], analysis: response.metadata?.analysis } }
              : msg
          );
          useAgentStore.setState({ messages: updatedMessages });
        }

      } catch (error) {
        console.error('Failed to send suggestion message:', error);
        addMessage({
          type: 'system',
          content: 'Sorry, the message failed to send. Please check your network connection and try again.',
        });
      } finally {
        useAgentStore.getState().setStreamingMessageId(null);
      }
    }
  };

  const renderActions = () => {
    if (!message.metadata?.actions?.length) return null;

    return (
      <div className="mt-4 space-y-2">
        <div className="text-xs text-gray-500 mb-3">💡 Suggested questions:</div>
        <div className="flex flex-wrap gap-2">
          {message.metadata.actions.map((action) => (
            <button
              key={action.id}
              onClick={() => handleActionClick(action)}
              className="px-4 py-2 bg-gradient-to-r from-gray-50 to-white border-2 border-gray-200 
                         rounded-full text-sm text-gray-700 hover:from-blue-500 hover:to-purple-600 
                         hover:text-white hover:border-transparent transition-all duration-300 
                         transform hover:scale-105 shadow-sm hover:shadow-md"
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
    );
  };

  const renderAttachments = () => {
    if (!message.metadata?.attachments?.length) return null;

    return (
      <div className="mt-3 space-y-2">
        <div className="text-xs text-gray-500 mb-2">Attachments:</div>
        <div className="space-y-1">
          {message.metadata.attachments.map((attachment) => (
            <div
              key={attachment.id}
              className="flex items-center space-x-2 p-2 bg-white rounded border text-sm"
            >
              <span className="flex-1 truncate">{attachment.name}</span>
              <Tag>{attachment.type}</Tag>
              <Button size="small" type="link">
                Download
              </Button>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} items-start space-x-3 mb-6`}>
      {!isUser && (
        <div className="flex-shrink-0 mt-1">
          {getAvatar()}
        </div>
      )}
      
      <div className={`max-w-4xl ${isUser ? 'order-1' : ''}`}>
        <div className={`rounded-2xl px-4 py-3 ${getBubbleStyle()}`}>
          {/* Message content */}
          <div className="break-words">
            {isUser || isSystem ? (
              // User and system messages are displayed as plain text
              <div className="whitespace-pre-wrap">
                {message.content}
              </div>
            ) : (
              // AI messages are rendered as Markdown
              <div className="markdown-message">
                {renderMarkdown(message.content, isStreaming)}
              </div>
            )}
          </div>
          
          {!isUser && !isSystem && message.metadata?.analysis && <AnalysisResultCard result={message.metadata.analysis} />}

          {/* Actions */}
          {renderActions()}
          
          {/* Attachments */}
          {renderAttachments()}
        </div>
      </div>
      
      {isUser && (
        <div className="flex-shrink-0 mt-1 order-2">
          {getAvatar()}
        </div>
      )}
    </div>
  );
};

export default MessageBubble;