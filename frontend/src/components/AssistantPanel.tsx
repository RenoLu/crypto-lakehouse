import React, { useState } from 'react';
import { askAssistant, AssistantResponse } from '../api/client';
import { Send, Sparkles } from 'lucide-react';

const EXAMPLE_PROMPTS = [
  "Which asset had the highest volatility?",
  "Show me stale price breaks.",
  "What changed in portfolio NAV?",
  "Which asset had the largest daily return?",
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
      const res = await askAssistant(question);
      setResponse(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 p-4">
      <div className="mb-4 flex items-center gap-2">
        <Sparkles className="h-5 w-5 text-purple-400" />
        <h3 className="text-lg font-semibold text-white">AI Assistant</h3>
      </div>

      <form onSubmit={handleSubmit} className="mb-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder="Ask about your portfolio or market data..."
            className="flex-1 rounded border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            className="rounded bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '...' : <Send className="h-4 w-4" />}
          </button>
        </div>
      </form>

      <div className="mb-4 flex flex-wrap gap-2">
        {EXAMPLE_PROMPTS.map(p => (
          <button
            key={p}
            onClick={() => { setQuestion(p); }}
            className="rounded-full border border-gray-700 bg-gray-800 px-3 py-1 text-xs text-gray-300 hover:border-purple-500 hover:text-purple-300"
          >
            {p}
          </button>
        ))}
      </div>

      {error && (
        <div className="mb-4 rounded border border-red-800 bg-red-900/30 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {response && (
        <div className="space-y-3">
          <div className="rounded border border-gray-700 bg-gray-800/50 p-3">
            <p className="text-sm text-gray-200 whitespace-pre-wrap">{response.answer}</p>
          </div>

          {response.query_used && response.query_used !== 'none' && (
            <div className="rounded border border-gray-700 bg-gray-800/30 p-3">
              <p className="text-xs text-gray-500 mb-1">Query used:</p>
              <code className="text-xs text-green-400 font-mono">{response.query_used}</code>
            </div>
          )}

          {response.rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-700">
                    {Object.keys(response.rows[0]).map(k => (
                      <th key={k} className="px-2 py-1 text-left text-gray-400 font-medium">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {response.rows.slice(0, 10).map((row, i) => (
                    <tr key={i} className="border-b border-gray-800">
                      {Object.values(row).map((v, j) => (
                        <td key={j} className="px-2 py-1 text-gray-300">
                          {typeof v === 'number' ? v.toLocaleString() : String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {response.rows.length > 10 && (
                <p className="mt-1 text-xs text-gray-500">...and {response.rows.length - 10} more rows</p>
              )}
            </div>
          )}

          {response.warnings.length > 0 && (
            <div className="rounded border border-yellow-800 bg-yellow-900/20 p-2">
              {response.warnings.map((w, i) => (
                <p key={i} className="text-xs text-yellow-400">{w}</p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
