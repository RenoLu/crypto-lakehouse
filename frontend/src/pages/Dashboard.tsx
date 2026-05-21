import MarketOverview from '../components/MarketOverview';
import AssetChart from '../components/AssetChart';
import PortfolioExposure from '../components/PortfolioExposure';
import QualityBreaks from '../components/QualityBreaks';
import AssistantPanel from '../components/AssistantPanel';

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <MarketOverview />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <AssetChart />
        </div>
        <div>
          <PortfolioExposure />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <QualityBreaks />
        <AssistantPanel />
      </div>
    </div>
  );
}
