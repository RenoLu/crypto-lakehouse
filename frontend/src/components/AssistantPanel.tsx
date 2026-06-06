import React, { useState } from 'react';
import { askAssistant, AssistantResponse } from '../api/client';
import { Send, Sparkles } from 'lucide-react';

const EXAMPLE_PROMPTS = [
  'Which asset had the highest volatility?',
  'Show me stale price breaks.',
  'What changed in portfolio NAV?',
  'Which asset had the largest daily return?',
];

export default function AssistantPanel() {
  const [question, setQuestion] = useState('');
  const [response, setResponse] = useState<AssistantResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResponse(await askAssistant(question));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="mb-3 flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-term-muted">
        <Sparkles className="h-4 w-4 text-term-accent" />
        Natural-language query
      </div>

      <form onSubmit={handleSubmit} className="mb-3 flex gap-2">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder="Ask about your portfolio or market data…"
          className="flex-1 rounded-sm border border-term-border bg-term-bg px-3 py-2 font-mono text-sm text-term-text placeholder-term-muted focus:border-term-accent focus:outline-none"
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="rounded-sm bg-term-accent px-3 py-2 text-sm font-medium text-term-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? '…' : <Send className="h-4 w-4" />}
        </button>
      </form>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {EXAMPLE_PROMPTS.map(p => (
          <button
            key={p}
            onClick={() => setQuestion(p)}
            className="rounded-sm border border-term-border bg-term-bg/50 px-2 py-1 font-mono text-[11px] text-term-muted transition-colors hover:border-term-accent/50 hover:text-term-accent"
          >
            {p}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-3 rounded-sm border border-term-down/40 bg-term-down/10 p-2.5 font-mono text-sm text-term-down">{error}</div>
      )}

      {response && (
        <div className="space-y-2.5">
          <div className="rounded-sm border border-term-border bg-term-bg/40 p-3">
            <p className="whitespace-pre-wrap text-sm text-term-text">{response.answer}</p>
          </div>

          {response.query_used && response.query_used !== 'none' && (
            <div className="rounded-sm border border-term-border bg-term-bg/30 p-3">
              <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-term-muted">SQL</p>
              <code className="font-mono text-xs text-term-up">{response.query_used}</code>
            </div>
          )}

          {response.rows.length > 0 && (
            <div className="overflow-x-auto rounded-sm border border-term-border">
              <table className="w-full font-mono text-xs">
                <thead>
                  <tr className="border-b border-term-border bg-term-bg/40">
                    {Object.keys(response.rows[0]).map(k => (
                      <th key={k} className="px-2 py-1.5 text-left font-medium text-term-muted">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {response.rows.slice(0, 10).map((row, i) => (
                    <tr key={i} className="border-b border-term-border/50">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="px-2 py-1 text-term-text">
                          {typeof v === 'number' ? v.toLocaleString() : String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {response.rows.length > 10 && (
                <p className="px-2 py-1 font-mono text-[10px] text-term-muted">…and {response.rows.length - 10} more rows</p>
              )}
            </div>
          )}

          {response.warnings.length > 0 && (
            <div className="rounded-sm border border-term-accent/40 bg-term-accent/10 p-2">
              {response.warnings.map((w, i) => (
                <p key={i} className="font-mono text-xs text-term-accent">{w}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
