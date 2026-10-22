import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { renderMarkdown } from './markdownRenderer';
import { collapseEvents, currentStepIndex } from './processEvents';
import { messageMetadataFrom } from '../services/agentService';

afterEach(cleanup);
describe('Round 12 real-stage and model provenance', () => {
  it('uses the latest specific tool instead of the old running graph envelope', () => {
    const steps=collapseEvents([
      {seq:1,time:1,stage:'data',status:'running',title:'Planning and inspecting data',opId:'coding'},
      {seq:2,time:2,stage:'plan',status:'done',title:'Plan sealed v1'},
      {seq:3,time:3,stage:'code',status:'running',title:'Writing analysis.py',opId:'code'},
      {seq:4,time:4,stage:'code',status:'done',title:'Wrote analysis.py',opId:'code'},
    ]);
    expect(steps[currentStepIndex(steps,true)].event.title).toBe('Wrote analysis.py');
    expect(currentStepIndex(steps,false)).toBe(-1);
  });
  it('keeps the response-ledger model and does not invent one for old history', () => {
    expect(messageMetadataFrom({requestBudget:{models:['deepseek-v4.1-flash'],model_source:'provider_response'}})?.usedModels).toEqual(['deepseek-v4.1-flash']);
    expect((messageMetadataFrom({model:'current-global-model'})?.usedModels ?? [])).toEqual([]);
  });
  it('renders ATX headings, keeps tables, and does not inject raw HTML', () => {
    render(renderMarkdown('# Analysis\n\n## Results\n\n| Region | Mean |\n| --- | --- |\n| One | 1.2 |\n\n<script>bad</script>'));
    expect(screen.getByRole('heading',{level:1,name:'Analysis'})).toBeTruthy();
    expect(screen.getByRole('heading',{level:2,name:'Results'})).toBeTruthy();
    expect(screen.getByRole('table')).toBeTruthy();
    expect(document.querySelector('script')).toBeNull();
  });
});
