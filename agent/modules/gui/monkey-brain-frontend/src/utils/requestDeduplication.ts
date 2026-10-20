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

/**
 * Request deduplication utility to prevent duplicate API calls
 */

interface PendingRequest {
  promise: Promise<any>;
  timestamp: number;
}

class RequestDeduplicator {
  private pendingRequests: Map<string, PendingRequest> = new Map();
  private readonly maxAge: number = 5000; // 5 seconds

  /**
   * Generate a unique key for the request
   */
  private generateKey(url: string, method: string, body?: any): string {
    const bodyStr = body ? JSON.stringify(body) : '';
    return `${method}:${url}:${bodyStr}`;
  }

  /**
   * Clean up expired requests
   */
  private cleanup(): void {
    const now = Date.now();
    for (const [key, request] of this.pendingRequests.entries()) {
      if (now - request.timestamp > this.maxAge) {
        this.pendingRequests.delete(key);
      }
    }
  }

  /**
   * Execute a request with deduplication
   */
  async execute<T>(
    url: string,
    options: RequestInit,
    requestFn: () => Promise<T>
  ): Promise<T> {
    this.cleanup();

    const key = this.generateKey(
      url,
      options.method || 'GET',
      options.body
    );

    // Check if there's already a pending request
    const existing = this.pendingRequests.get(key);
    if (existing) {
      console.log('Deduplicating request:', key);
      return existing.promise;
    }

    // Create new request
    const promise = requestFn().finally(() => {
      // Remove from pending requests when completed
      this.pendingRequests.delete(key);
    });

    // Store the pending request
    this.pendingRequests.set(key, {
      promise,
      timestamp: Date.now(),
    });

    return promise;
  }

  /**
   * Check if a request is currently pending
   */
  isPending(url: string, method: string = 'GET', body?: any): boolean {
    const key = this.generateKey(url, method, body);
    return this.pendingRequests.has(key);
  }

  /**
   * Cancel all pending requests
   */
  cancelAll(): void {
    this.pendingRequests.clear();
  }

  /**
   * Get the number of pending requests
   */
  getPendingCount(): number {
    this.cleanup();
    return this.pendingRequests.size;
  }
}

// Export singleton instance
export const requestDeduplicator = new RequestDeduplicator();

/**
 * Higher-order function to wrap fetch with deduplication
 */
export function createDedupedFetch() {
  return async function dedupedFetch(
    url: string,
    options: RequestInit = {}
  ): Promise<Response> {
    return requestDeduplicator.execute(url, options, () => fetch(url, options));
  };
}

/**
 * Hook for React components to track request status
 */
export function useRequestStatus() {
  const [pendingCount, setPendingCount] = React.useState(0);

  React.useEffect(() => {
    const interval = setInterval(() => {
      setPendingCount(requestDeduplicator.getPendingCount());
    }, 100);

    return () => clearInterval(interval);
  }, []);

  return {
    pendingCount,
    hasPendingRequests: pendingCount > 0,
  };
}

// Import React for the hook
import React from 'react';