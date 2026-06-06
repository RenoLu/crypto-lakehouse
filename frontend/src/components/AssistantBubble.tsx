import { useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import AssistantPanel from './AssistantPanel';

export default function AssistantBubble() {
  const [open, setOpen] = useState(false);

  return (
    <div className="fixed bottom-5 right-5 z-40 flex flex-col items-end gap-3">
      {open && (
        <div className="anim-pop w-[min(92vw,380px)] origin-bottom-right rounded-sm border border-term-border bg-term-panel shadow-panel">
          <div className="flex items-center justify-between border-b border-term-border px-3 py-2">
            <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-term-text">
              <Sparkles className="h-4 w-4 text-term-accent" /> AI Assistant
            </span>
            <button onClick={() => setOpen(false)} aria-label="Close assistant" className="text-term-muted hover:text-term-text">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="max-h-[70vh] overflow-y-auto p-4">
            <AssistantPanel />
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen(o => !o)}
        aria-label="Toggle assistant"
        className="flex items-center gap-2 rounded-full bg-term-accent px-4 py-3 font-mono text-sm font-semibold text-term-bg shadow-lg ring-1 ring-term-accent/40 transition-transform hover:scale-105"
      >
        <Sparkles className="h-5 w-5" />
        {!open && <span className="hidden sm:inline">Ask</span>}
      </button>
    </div>
  );
}
