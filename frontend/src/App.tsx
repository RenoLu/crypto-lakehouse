import DashboardLayout from './components/DashboardLayout';
import Dashboard from './pages/Dashboard';
import { RefreshProvider } from './refresh';
import { ThemeProvider } from './theme';

export default function App() {
  return (
    <ThemeProvider>
      <RefreshProvider>
        <DashboardLayout>
          <Dashboard />
        </DashboardLayout>
      </RefreshProvider>
    </ThemeProvider>
  );
}
