import { useState } from 'react';
import PortfolioExposure from './PortfolioExposure';
import QualityBreaks from './QualityBreaks';

const TABS = [
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'quality', label: 'Quality' },
] as const;

type TabId = (typeof TABS)[number]['id'];

export default function TabbedPanel() {
  const [tab, setTab] = useState<TabId>('portfolio');

  return (
    <div className="rounded-sm border border-term-border bg-term-panel shadow-panel">
      <div className="flex border-b border-term-border">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-4 py-2.5 font-mono text-xs uppercase tracking-wider transition-colors ${
              tab === t.id
                ? 'border-term-accent text-term-accent'
                : 'border-transparent text-term-muted hover:text-term-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div key={tab} className="anim-fade p-4">
        {tab === 'portfolio' && <PortfolioExposure />}
        {tab === 'quality' && <QualityBreaks />}
      </div>
    </div>
  );
}
