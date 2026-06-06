import AssetChart from '../components/AssetChart';
import TickerBar from '../components/TickerBar';
import TabbedPanel from '../components/TabbedPanel';

export default function Dashboard() {
  return (
    <div className="space-y-3">
      <div className="anim-fade-up" style={{ animationDelay: '0ms' }}>
        <TickerBar />
      </div>
      <div className="anim-fade-up" style={{ animationDelay: '90ms' }}>
        <AssetChart />
      </div>
      <div className="anim-fade-up" style={{ animationDelay: '180ms' }}>
        <TabbedPanel />
      </div>
    </div>
  );
}
