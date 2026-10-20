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

import React, { useState, useEffect } from 'react';
import { Input, List, Typography, Empty, Button, Space } from 'antd';
import { SearchOutlined, CloseOutlined, MessageOutlined } from '@ant-design/icons';
import { useAgentStore } from '../../stores/agentStore';
import { Message } from '../../types/agent';

const { Search } = Input;
const { Text } = Typography;

interface MessageSearchProps {
  visible: boolean;
  onClose: () => void;
}

const MessageSearch: React.FC<MessageSearchProps> = ({ visible, onClose }) => {
  const { 
    messages, 
    searchQuery, 
    filteredMessages, 
    searchMessages, 
    clearSearch 
  } = useAgentStore();

  const [localQuery, setLocalQuery] = useState(searchQuery);

  useEffect(() => {
    if (!visible) {
      setLocalQuery('');
      clearSearch();
    }
  }, [visible, clearSearch]);

  const handleSearch = (value: string) => {
    setLocalQuery(value);
    searchMessages(value);
  };

  const handleClear = () => {
    setLocalQuery('');
    clearSearch();
  };

  const highlightText = (text: string, query: string) => {
    if (!query.trim()) return text;

    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    const parts = text.split(regex);

    return parts.map((part, index) =>
      regex.test(part) ? (
        <mark key={index} className="bg-yellow-200 px-1 rounded">
          {part}
        </mark>
      ) : (
        part
      )
    );
  };

  const formatTime = (timestamp: Date) => {
    return new Date(timestamp).toLocaleString('zh-CN', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getMessageTypeColor = (type: Message['type']) => {
    switch (type) {
      case 'user':
        return 'text-blue-600';
      case 'agent':
        return 'text-green-600';
      case 'system':
        return 'text-orange-600';
      default:
        return 'text-gray-600';
    }
  };

  const getMessageTypeLabel = (type: Message['type']) => {
    switch (type) {
      case 'user':
        return 'User';
      case 'agent':
        return 'AI';
      case 'system':
        return 'System';
      default:
        return 'Unknown';
    }
  };

  if (!visible) return null;

  return (
    <div className="absolute inset-0 bg-white z-10 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b">
        <Space>
          <SearchOutlined />
          <span className="font-medium">Search Messages</span>
        </Space>
        <Button type="text" icon={<CloseOutlined />} onClick={onClose} />
      </div>

      {/* Search Input */}
      <div className="p-4 border-b">
        <Search
          placeholder="Enter keyword to search messages..."
          value={localQuery}
          onChange={(e) => handleSearch(e.target.value)}
          onSearch={handleSearch}
          allowClear
          onClear={handleClear}
          size="large"
        />
      </div>

      {/* Search Results */}
      <div className="flex-1 overflow-y-auto p-4">
        {!localQuery.trim() ? (
          <div className="text-center text-gray-500 mt-8">
            <SearchOutlined className="text-4xl mb-4" />
            <div>Enter a keyword to start searching messages</div>
          </div>
        ) : filteredMessages.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="No matching messages found"
          />
        ) : (
          <div className="space-y-4">
            <div className="text-sm text-gray-500 mb-4">
              Found {filteredMessages.length} matching messages
            </div>
            
            <List
              dataSource={filteredMessages}
              renderItem={(message) => (
                <List.Item className="border rounded-lg p-4 hover:bg-gray-50">
                  <div className="w-full">
                    {/* Message Header */}
                    <div className="flex items-center justify-between mb-2">
                      <Space>
                        <MessageOutlined className={getMessageTypeColor(message.type)} />
                        <Text strong className={getMessageTypeColor(message.type)}>
                          {getMessageTypeLabel(message.type)}
                        </Text>
                        {message.metadata?.taskId && (
                          <Text type="secondary" className="text-xs">
                            Task: {message.metadata.taskId}
                          </Text>
                        )}
                      </Space>
                      <Text type="secondary" className="text-xs">
                        {formatTime(message.timestamp)}
                      </Text>
                    </div>

                    {/* Message Content */}
                    <div className="text-sm leading-relaxed">
                      {highlightText(message.content, localQuery)}
                    </div>

                    {/* Actions */}
                    {message.metadata?.actions && message.metadata.actions.length > 0 && (
                      <div className="mt-2 pt-2 border-t">
                        <Text type="secondary" className="text-xs">
                          Contains {message.metadata.actions.length} action suggestions
                        </Text>
                      </div>
                    )}
                  </div>
                </List.Item>
              )}
            />
          </div>
        )}
      </div>

      {/* Footer Stats */}
      <div className="p-4 border-t bg-gray-50">
        <Text type="secondary" className="text-xs">
          A total of {messages.length} messages available for search
        </Text>
      </div>
    </div>
  );
};

export default MessageSearch;