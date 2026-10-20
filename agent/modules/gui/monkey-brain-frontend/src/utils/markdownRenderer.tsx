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
import { Button, message } from 'antd';
import { CopyOutlined, CheckOutlined } from '@ant-design/icons';

// Copy code to clipboard
export const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    // Fallback
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    textArea.style.top = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
      document.execCommand('copy');
      document.body.removeChild(textArea);
      return true;
    } catch (err) {
      document.body.removeChild(textArea);
      return false;
    }
  }
};

// Code block copy button component
interface CodeCopyButtonProps {
  code: string;
  language?: string;
}

export const CodeCopyButton: React.FC<CodeCopyButtonProps> = ({ code }) => {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    const success = await copyToClipboard(code);
    if (success) {
      setCopied(true);
      message.success('Code copied to clipboard', 1);
      setTimeout(() => setCopied(false), 2000);
    } else {
      message.error('Copy failed, please copy manually');
    }
  };

  return (
    <Button
      size="small"
      type="text"
      icon={copied ? <CheckOutlined /> : <CopyOutlined />}
      onClick={handleCopy}
      className={`
        transition-all duration-200 border-0 shadow-sm
        ${copied 
          ? 'text-green-600 bg-green-100 hover:bg-green-200' 
          : 'text-gray-400 bg-gray-700 hover:bg-gray-600 hover:text-white'
        }
      `}
      title={copied ? 'Copied!' : 'Copy code'}
    >
      {copied ? 'Copied' : 'Copy'}
    </Button>
  );
};

// Render Markdown content
export const renderMarkdown = (content: string, isStreaming?: boolean): JSX.Element => {
  if (!content) return <span></span>;

  // Split content and handle code blocks
  const parts: JSX.Element[] = [];
  let lastIndex = 0;
  let codeBlockIndex = 0;

  // Regex to match code blocks
  const codeBlockRegex = /```(\w*)\n?([\s\S]*?)```/g;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    const [fullMatch, language, code] = match;
    const matchStart = match.index;
    const matchEnd = match.index + fullMatch.length;

    // Add plain text before the code block
    if (matchStart > lastIndex) {
      const textBefore = content.slice(lastIndex, matchStart);
      parts.push(
        <span key={`text-${lastIndex}`}>
          {renderInlineMarkdown(textBefore)}
        </span>
      );
    }

    // Add code block
    const blockId = `code-block-${codeBlockIndex++}`;
    const trimmedCode = code.trim();
    
    parts.push(
      <div key={blockId} className="relative my-4 group">
        <div className="bg-gray-900 rounded-lg overflow-hidden shadow-lg border border-gray-700">
          {/* Code block header */}
          <div className="flex items-center justify-between px-4 py-3 bg-gray-800 border-b border-gray-700">
            <div className="flex items-center space-x-2">
              <div className="flex space-x-1">
                <div className="w-3 h-3 rounded-full bg-red-500"></div>
                <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
                <div className="w-3 h-3 rounded-full bg-green-500"></div>
              </div>
              <span className="font-mono text-sm text-gray-300 ml-2">
                {language || 'plaintext'}
              </span>
            </div>
            <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              <CodeCopyButton code={trimmedCode} language={language} />
            </div>
          </div>
          
          {/* Code content */}
          <div className="relative">
            <pre className="p-4 overflow-x-auto text-sm bg-gray-900">
              <code className="text-gray-100 font-mono leading-relaxed block">
                {trimmedCode}
              </code>
            </pre>
          </div>
        </div>
      </div>
    );

    lastIndex = matchEnd;
  }

  // Add remaining plain text
  if (lastIndex < content.length) {
    const textAfter = content.slice(lastIndex);
    parts.push(
      <span key={`text-${lastIndex}`}>
        {renderInlineMarkdown(textAfter)}
      </span>
    );
  }

  return (
    <div className="markdown-content">
      {parts}
      {/* Streaming cursor - ChatGPT style */}
      {isStreaming && (
        <span className="streaming-cursor-soft"></span>
      )}
    </div>
  );
};

// Render inline Markdown (bold, italic, inline code, etc.)
const renderInlineMarkdown = (text: string): JSX.Element => {
  if (!text) return <span></span>;

  // Handle inline code
  const inlineCodeRegex = /`([^`]+)`/g;
  const parts: (string | JSX.Element)[] = [];
  let lastIndex = 0;
  let inlineCodeIndex = 0;

  let match;
  while ((match = inlineCodeRegex.exec(text)) !== null) {
    const [fullMatch, code] = match;
    const matchStart = match.index;
    const matchEnd = match.index + fullMatch.length;

    // Add text before inline code
    if (matchStart > lastIndex) {
      parts.push(text.slice(lastIndex, matchStart));
    }

    // Add inline code
    parts.push(
      <code 
        key={`inline-code-${inlineCodeIndex++}`}
        className="bg-gray-100 text-gray-800 px-1.5 py-0.5 rounded text-sm font-mono"
      >
        {code}
      </code>
    );

    lastIndex = matchEnd;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  // Handle bold and italic
  return (
    <span>
      {parts.map((part, index) => {
        if (typeof part === 'string') {
          return formatTextStyles(part, index);
        }
        return part;
      })}
    </span>
  );
};

// Handle bold, italic and other text styles
const formatTextStyles = (text: string, key: number): JSX.Element => {
  // Handle bold **text**
  const parts: (string | JSX.Element)[] = [];
  let currentIndex = 0;
  
  // Handle bold
  const boldRegex = /\*\*(.*?)\*\*/g;
  let boldMatch;
  let boldIndex = 0;
  
  while ((boldMatch = boldRegex.exec(text)) !== null) {
    const [fullMatch, boldText] = boldMatch;
    const matchStart = boldMatch.index;
    
    // Add text before bold
    if (matchStart > currentIndex) {
      parts.push(text.slice(currentIndex, matchStart));
    }
    
    // Add bold text
    parts.push(
      <strong key={`bold-${key}-${boldIndex++}`} className="font-semibold text-gray-900">
        {boldText}
      </strong>
    );
    
    currentIndex = matchStart + fullMatch.length;
  }
  
  // Add remaining text
  if (currentIndex < text.length) {
    parts.push(text.slice(currentIndex));
  }
  
  // If no bold found, return original text
  if (parts.length === 0) {
    parts.push(text);
  }
  
  return (
    <span key={`text-${key}`}>
      {parts.map((part, index) => {
        if (typeof part === 'string') {
          // Handle newlines
          return part.split('\n').map((line, lineIndex, array) => (
            <React.Fragment key={`line-${index}-${lineIndex}`}>
              {line}
              {lineIndex < array.length - 1 && <br />}
            </React.Fragment>
          ));
        }
        return part;
      })}
    </span>
  );
};

// Handle newlines
export const formatNewlines = (text: string): string => {
  return text.replace(/\n/g, '\n');
};