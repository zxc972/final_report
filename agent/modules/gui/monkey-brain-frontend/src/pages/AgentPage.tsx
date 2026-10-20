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

import React, { useEffect } from 'react';
import { ChatInterface } from '../components/Agent';
import { useAgentStore } from '../stores/agentStore';

const AgentPage: React.FC = () => {
  const { initializeAgentService, createNewConversation, currentConversation } = useAgentStore();

  useEffect(() => {
    initializeAgentService();
    if (!currentConversation) {
      createNewConversation();
    }
  }, [initializeAgentService, currentConversation, createNewConversation]);

  return (
    <div className="h-full w-full">
      <ChatInterface />
    </div>
  );
};

export default AgentPage;
