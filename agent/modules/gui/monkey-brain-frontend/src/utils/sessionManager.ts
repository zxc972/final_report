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
 * Session management utility for maintaining active sessions
 */

interface SessionConfig {
  heartbeatInterval: number; // milliseconds
  sessionTimeout: number; // milliseconds
  maxRetries: number;
}

interface SessionState {
  isActive: boolean;
  lastActivity: number;
  heartbeatCount: number;
  retryCount: number;
}

class SessionManager {
  private config: SessionConfig;
  private state: SessionState;
  private heartbeatTimer: number | null = null;
  private sessionTimer: number | null = null;
  private callbacks: {
    onHeartbeat?: () => Promise<void>;
    onSessionExpired?: () => void;
    onSessionRestored?: () => void;
    onError?: (error: Error) => void;
  } = {};

  constructor(config: Partial<SessionConfig> = {}) {
    this.config = {
      heartbeatInterval: 30000, // 30 seconds
      sessionTimeout: 1800000, // 30 minutes
      maxRetries: 3,
      ...config,
    };

    this.state = {
      isActive: false,
      lastActivity: Date.now(),
      heartbeatCount: 0,
      retryCount: 0,
    };

    // Listen for user activity
    this.setupActivityListeners();
  }

  /**
   * Start session management
   */
  start(): void {
    if (this.state.isActive) {
      return;
    }

    this.state.isActive = true;
    this.state.lastActivity = Date.now();
    this.state.retryCount = 0;

    this.startHeartbeat();
    this.startSessionTimer();

    console.log('Session management started');
  }

  /**
   * Stop session management
   */
  stop(): void {
    this.state.isActive = false;
    this.clearTimers();
    console.log('Session management stopped');
  }

  /**
   * Update last activity timestamp
   */
  updateActivity(): void {
    this.state.lastActivity = Date.now();
    
    // Reset session timer
    if (this.sessionTimer) {
      window.clearTimeout(this.sessionTimer);
      this.startSessionTimer();
    }
  }

  /**
   * Check if session is active
   */
  isSessionActive(): boolean {
    return this.state.isActive;
  }

  /**
   * Get session statistics
   */
  getSessionStats(): {
    isActive: boolean;
    lastActivity: Date;
    heartbeatCount: number;
    timeSinceLastActivity: number;
  } {
    return {
      isActive: this.state.isActive,
      lastActivity: new Date(this.state.lastActivity),
      heartbeatCount: this.state.heartbeatCount,
      timeSinceLastActivity: Date.now() - this.state.lastActivity,
    };
  }

  /**
   * Set callback functions
   */
  setCallbacks(callbacks: {
    onHeartbeat?: () => Promise<void>;
    onSessionExpired?: () => void;
    onSessionRestored?: () => void;
    onError?: (error: Error) => void;
  }): void {
    this.callbacks = { ...this.callbacks, ...callbacks };
  }

  /**
   * Force session refresh
   */
  async refreshSession(): Promise<void> {
    if (!this.state.isActive) {
      return;
    }

    try {
      if (this.callbacks.onHeartbeat) {
        await this.callbacks.onHeartbeat();
      }
      
      this.state.retryCount = 0;
      this.updateActivity();
      
      if (this.callbacks.onSessionRestored) {
        this.callbacks.onSessionRestored();
      }
    } catch (error: any) {
      this.handleHeartbeatError(error);
    }
  }

  // Private methods

  private setupActivityListeners(): void {
    // Listen for various user activity events
    const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'];
    
    const activityHandler = () => {
      this.updateActivity();
    };

    events.forEach(event => {
      document.addEventListener(event, activityHandler, { passive: true });
    });

    // Listen for visibility changes
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        this.updateActivity();
      }
    });

    // Listen for focus events
    window.addEventListener('focus', () => {
      this.updateActivity();
    });
  }

  private startHeartbeat(): void {
    if (this.heartbeatTimer) {
      window.clearInterval(this.heartbeatTimer);
    }

    this.heartbeatTimer = window.setInterval(async () => {
      if (!this.state.isActive) {
        return;
      }

      try {
        if (this.callbacks.onHeartbeat) {
          await this.callbacks.onHeartbeat();
        }
        
        this.state.heartbeatCount++;
        this.state.retryCount = 0;
      } catch (error: any) {
        this.handleHeartbeatError(error);
      }
    }, this.config.heartbeatInterval);
  }

  private startSessionTimer(): void {
    if (this.sessionTimer) {
      window.clearTimeout(this.sessionTimer);
    }

    this.sessionTimer = window.setTimeout(() => {
      this.handleSessionTimeout();
    }, this.config.sessionTimeout);
  }

  private handleHeartbeatError(error: Error): void {
    this.state.retryCount++;
    
    if (this.callbacks.onError) {
      this.callbacks.onError(error);
    }

    if (this.state.retryCount >= this.config.maxRetries) {
      console.error('Heartbeat failed after max retries, session expired');
      this.handleSessionTimeout();
    } else {
      console.warn(`Heartbeat failed, retry ${this.state.retryCount}/${this.config.maxRetries}`);
    }
  }

  private handleSessionTimeout(): void {
    console.log('Session timeout detected');
    
    this.state.isActive = false;
    this.clearTimers();
    
    if (this.callbacks.onSessionExpired) {
      this.callbacks.onSessionExpired();
    }
  }

  private clearTimers(): void {
    if (this.heartbeatTimer) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }

    if (this.sessionTimer) {
      window.clearTimeout(this.sessionTimer);
      this.sessionTimer = null;
    }
  }
}

// Export singleton instance
export const sessionManager = new SessionManager();

/**
 * React hook for session management
 */
export function useSessionManager() {
  const [sessionStats, setSessionStats] = React.useState(sessionManager.getSessionStats());

  React.useEffect(() => {
    const interval = setInterval(() => {
      setSessionStats(sessionManager.getSessionStats());
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  return {
    ...sessionStats,
    refreshSession: () => sessionManager.refreshSession(),
    isSessionActive: sessionManager.isSessionActive(),
  };
}

// Import React for the hook
import React from 'react';