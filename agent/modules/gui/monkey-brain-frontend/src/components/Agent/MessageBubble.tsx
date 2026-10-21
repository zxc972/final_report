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
import { errorSummary } from '../../utils/errorSummary';
import { Button, Tag } from 'antd';
import { Message } from '../../types/agent';
import { useAgentStore } from '../../stores/agentStore';
import { renderMarkdown } from '../../utils/markdownRenderer';
import AnalysisResultCard from './AnalysisResultCard';
import { agentService, messageMetadataFrom } from '../../services/agentService';

interface MessageBubbleProps {
  message: Message;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.type === 'user';
  const isSystem = message.type === 'system';
  const { streamingMessageId } = useAgentStore();
  const isStreaming = streamingMessageId === message.id;
  
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
        useAgentStore.getState().updateConversationContext({ backendConversationId: agentService.ensureConversationId() });
        const response = await agentService.sendMessage(action.data.suggestion, undefined, (streamContent) => {
          // Update streaming message content in real time
          updateStreamingMessage(messageId, streamContent);
        });
        
        // Finally update the complete response
        updateStreamingMessage(messageId, response.message);
        
        // Update metadata (if any)
        const keptMetadata = messageMetadataFrom(response.metadata);
        if (keptMetadata) {
          const state = useAgentStore.getState();
          const updatedMessages = state.messages.map(msg =>
            msg.id === messageId ? { ...msg, content: response.message, metadata: keptMetadata } : msg
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
      <div className="px-suggestions" aria-label="Suggested follow-ups">
        {message.metadata.actions.map((action) => (
          <button
            key={action.id}
            type="button"
            onClick={() => handleActionClick(action)}
            className="px-suggestion"
          >
            {action.label}
          </button>
        ))}
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

  const failureSummary = errorSummary(message.content, message.metadata?.analysis?.status);
  const fullContent = <div className="markdown-message">{renderMarkdown(message.content, isStreaming)}</div>;
  const displayContent = failureSummary
    ? <details className="px-error-details"><summary>{failureSummary}</summary>{fullContent}</details>
    : fullContent;

  if (isUser) {
    return <div className="px-msg-user">{message.content}</div>;
  }

  if (isSystem) {
    return <div className="px-msg-system">{failureSummary ? displayContent : message.content}</div>;
  }

  const isThinking = isStreaming && (message.content === 'Thinking...' || !message.content.trim());

  return (
    <div className="px-msg-agent">
      <div className="px-msg-avatar" aria-hidden="true">PX</div>
      <div className="px-msg-body">
        {message.metadata?.route && (
          <span className="px-route" title={message.metadata.routeReason || undefined}>
            {message.metadata.route === 'analysis' ? 'Analysis' : 'Preprocessing'}
          </span>
        )}
        {isThinking ? (
          <span className="px-working"><span className="px-spin" />Working… progress is shown in Run details</span>
        ) : (
          displayContent
        )}
        {message.metadata?.analysis && <AnalysisResultCard result={message.metadata.analysis} />}
        {renderActions()}
        {renderAttachments()}
      </div>
    </div>
  );
};

export default MessageBubble;