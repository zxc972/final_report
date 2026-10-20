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

import React, { useState } from 'react';
import { 
  Drawer, 
  List, 
  Button, 
  Input, 
  Space, 
  Typography, 
  Popconfirm,
  Empty,
  Tag
} from 'antd';
import { 
  HistoryOutlined, 
  SearchOutlined, 
  DeleteOutlined,
  MessageOutlined,
  CloseOutlined
} from '@ant-design/icons';
import { useAgentStore } from '../../stores/agentStore';
import { Conversation } from '../../types/agent';

const { Text } = Typography;
const { Search } = Input;

interface ConversationHistoryProps {
  visible: boolean;
  onClose: () => void;
}

const ConversationHistory: React.FC<ConversationHistoryProps> = ({
  visible,
  onClose,
}) => {
  const {
    conversationHistory,
    currentConversation,
    loadConversation,
    deleteConversation,
    saveConversation,
  } = useAgentStore();

  const [searchQuery, setSearchQuery] = useState('');

  const filteredConversations = (conversationHistory || []).filter(conv =>
    conv.messages.some(msg => 
      msg.content.toLowerCase().includes(searchQuery.toLowerCase())
    )
  );

  const formatDate = (date: Date) => {
    const now = new Date();
    const diffTime = now.getTime() - new Date(date).getTime();
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return new Date(date).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
      });
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return `${diffDays} days ago`;
    } else {
      return new Date(date).toLocaleDateString('zh-CN');
    }
  };

  const getConversationPreview = (conversation: Conversation) => {
    const lastMessage = conversation.messages[conversation.messages.length - 1];
    if (!lastMessage) return 'New conversation';
    
    const preview = lastMessage.content.length > 50 
      ? lastMessage.content.substring(0, 50) + '...'
      : lastMessage.content;
    
    return preview;
  };

  const handleLoadConversation = (conversationId: string) => {
    // Save current conversation before loading new one
    if (currentConversation) {
      saveConversation();
    }
    
    loadConversation(conversationId);
    onClose();
  };

  const handleDeleteConversation = (conversationId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    deleteConversation(conversationId);
  };

  return (
    <Drawer
      title={
        <Space>
          <HistoryOutlined />
          <span>Conversation History</span>
        </Space>
      }
      placement="left"
      onClose={onClose}
      open={visible}
      width={400}
      extra={
        <Button 
          type="text" 
          icon={<CloseOutlined />} 
          onClick={onClose}
        />
      }
    >
      <div className="space-y-4">
        {/* Search */}
        <Search
          placeholder="Search conversation content..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          prefix={<SearchOutlined />}
          allowClear
        />

        {/* Conversation List */}
        {filteredConversations.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              searchQuery ? 'No matching conversations found' : 'No conversation history yet'
            }
          />
        ) : (
          <List
            dataSource={filteredConversations}
            renderItem={(conversation) => (
              <List.Item
                className={`cursor-pointer hover:bg-gray-50 rounded-lg p-3 ${
                  currentConversation?.id === conversation.id 
                    ? 'bg-blue-50 border border-blue-200' 
                    : ''
                }`}
                onClick={() => handleLoadConversation(conversation.id)}
                actions={[
                  <Popconfirm
                    title="Are you sure you want to delete this conversation?"
                    onConfirm={(e) => handleDeleteConversation(conversation.id, e!)}
                    okText="Delete"
                    cancelText="Cancel"
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      danger
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>
                ]}
              >
                <List.Item.Meta
                  avatar={
                    <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                      <MessageOutlined className="text-blue-600" />
                    </div>
                  }
                  title={
                    <div className="flex items-center justify-between">
                      <Text strong className="text-sm">
                        {formatDate(conversation.updatedAt)}
                      </Text>
                      <Tag color="blue">
                        {conversation.messages.length} messages
                      </Tag>
                    </div>
                  }
                  description={
                    <Text type="secondary" className="text-xs">
                      {getConversationPreview(conversation)}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        )}

        {/* Statistics */}
        <div className="mt-6 p-3 bg-gray-50 rounded-lg">
          <Text type="secondary" className="text-xs">
            Total {(conversationHistory || []).length} conversations,{' '}
            {(conversationHistory || []).reduce((total, conv) => total + conv.messages.length, 0)} messages
          </Text>
        </div>
      </div>
    </Drawer>
  );
};

export default ConversationHistory;