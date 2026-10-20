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
import { Card, Divider } from 'antd';
import { ParameterForm } from '../components/Config';
import ApiKeyConfig from '../components/Agent/ApiKeyConfig';

const ConfigPage: React.FC = () => {
  return (
    <div className="h-full overflow-y-auto">
      <div className="p-6 space-y-6 min-h-full">
        {/* API Key Configuration */}
        <Card title="🔑 AI Assistant Configuration" className="shadow-sm">
          <ApiKeyConfig />
        </Card>
        
        <Divider />
        
        {/* System Parameters */}
        <Card title="⚙️ System Parameter Configuration" className="shadow-sm">
          <ParameterForm />
        </Card>
      </div>
    </div>
  );
};

export default ConfigPage;