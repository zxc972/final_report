import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { agentService } from './agentService';
import { useAgentStore } from '../stores/agentStore';
import { renderMarkdown, splitTableRow } from '../utils/markdownRenderer';

const conversation = (id: string, backendId: string) => ({ id, userId: 'fixture', messages: [{ id: 'u1', type: 'user' as const, content: 'View inputs', timestamp: new Date() }], context: { backendConversationId: backendId }, createdAt: new Date(), updatedAt: new Date() });

beforeEach(() => {
  const storage = new Map<string, string>();
  vi.mocked(localStorage.getItem).mockImplementation((key: string) => storage.get(key) ?? null);
  vi.mocked(localStorage.setItem).mockImplementation((key: string, value: string) => { storage.set(key, value); });
  vi.mocked(localStorage.clear).mockImplementation(() => { storage.clear(); });
  localStorage.clear();
  agentService.restoreConversation(null);
});

describe('saved server conversation binding', () => {
  it('switches to each actual backend ID without confusing UI IDs', () => {
    const one = conversation('ui-one', 'server_one');
    const two = conversation('ui-two', 'server_two');
    useAgentStore.setState({ conversationHistory: [one, two], currentConversation: null, messages: [] });
    useAgentStore.getState().loadConversation('ui-one');
    expect(agentService.getConversationId()).toBe('server_one');
    useAgentStore.getState().loadConversation('ui-two');
    expect(agentService.getConversationId()).toBe('server_two');
  });
  it('restores the server ID after persistence rehydration', async () => {
    const saved = conversation('ui-refresh', 'server_refresh');
    localStorage.setItem('agent-store', JSON.stringify({ state: { currentConversation: saved, conversationHistory: [saved], messages: saved.messages }, version: 0 }));
    agentService.restoreConversation(null);
    await useAgentStore.persist.rehydrate();
    expect(agentService.getConversationId()).toBe('server_refresh');
  });
  it('stores the real service ID with history', () => {
    const saved = conversation('ui-save', 'old_server');
    agentService.restoreConversation('new_server', saved.messages);
    useAgentStore.setState({ currentConversation: saved, conversationHistory: [], messages: saved.messages });
    useAgentStore.getState().saveConversation();
    expect(useAgentStore.getState().conversationHistory[0].context.backendConversationId).toBe('new_server');
  });
});

it('renders Markdown tables, inline formatting and literal HTML safely', () => {
  render(renderMarkdown('| Region | **Mean** |\n|---|---|\n| one | 2.5 |\n| <script> | `3.0` |'));
  expect(screen.getByRole('table')).toBeTruthy();
  expect(screen.getAllByRole('row')).toHaveLength(3);
  expect(screen.getByRole('columnheader', { name: 'Mean' })).toBeTruthy();
  expect(document.querySelector('script')).toBeNull();
  expect(splitTableRow('| a\\|b | `x|y` |')).toEqual(['a|b', '`x|y`']);
});
