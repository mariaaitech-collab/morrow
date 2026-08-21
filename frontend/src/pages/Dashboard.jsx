import { useState, useEffect } from 'react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import Navbar from '../components/Navbar';
import ContentGenerator from '../components/ContentGenerator';

const PLATFORM_ICONS = {
  facebook: 'f',
  linkedin: 'in',
  instagram: 'ig',
};

function Dashboard({ user, onLogout }) {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchAccounts = async () => {
    try {
      const { data } = await api.get('/social/accounts');
      setAccounts(data);
    } catch (err) {
      const detail = err.response?.data?.detail || err.message || 'Failed to load social accounts';
      toast.error(detail);
      console.error('Fetch accounts error:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  const handleConnect = async (platform) => {
    console.log(`[DEBUG] Connect button clicked for: ${platform}`);
    try {
      console.log(`[DEBUG] Calling api.get(/social/connect/${platform})`);
      const { data } = await api.get(`/social/connect/${platform}`);
      console.log(`[DEBUG] API response:`, data);
      if (data.auth_url) {
        console.log(`[DEBUG] Redirecting to: ${data.auth_url}`);
        window.location.href = data.auth_url;
      } else {
        console.error(`[DEBUG] No auth_url in response:`, data);
        toast.error(`No auth URL returned for ${platform}`);
      }
    } catch (err) {
      console.error(`[DEBUG] Connect failed for ${platform}:`, err);
      console.error(`[DEBUG] Response status:`, err.response?.status);
      console.error(`[DEBUG] Response data:`, err.response?.data);
      const detail = err.response?.data?.detail || err.message || `Failed to connect ${platform}`;
      toast.error(detail);
    }
  };

  const handleDisconnect = async (platform) => {
    try {
      await api.delete(`/social/disconnect/${platform}`);
      toast.success(`${platform} disconnected`);
      fetchAccounts();
    } catch (err) {
      toast.error(err.response?.data?.detail || `Failed to disconnect ${platform}`);
    }
  };

  const connectedCount = accounts.filter((a) => a.connected).length;

  return (
    <>
      <Navbar user={user} onLogout={onLogout} active="dashboard" />
      <div className="dashboard">
        <h2>Dashboard</h2>
        <div className="stats-grid">
          <div className="stat-card">
            <div className="label">Connected Platforms</div>
            <div className="value green">{connectedCount}</div>
          </div>
          <div className="stat-card">
            <div className="label">Available Platforms</div>
            <div className="value purple">{accounts.length}</div>
          </div>
          <div className="stat-card">
            <div className="label">Pending</div>
            <div className="value yellow">{accounts.length - connectedCount}</div>
          </div>
        </div>
        <div className="social-section">
          <h3>Social Accounts</h3>
          {loading ? (
            <p style={{ color: 'var(--text-muted)' }}>Loading...</p>
          ) : (
            <div className="social-grid">
              {accounts.map((account) => (
                <div className="social-card" key={account.platform}>
                  <div className={`social-icon ${account.platform}`}>
                    {PLATFORM_ICONS[account.platform]}
                  </div>
                  <div className="social-info">
                    <h4>{account.platform.charAt(0).toUpperCase() + account.platform.slice(1)}</h4>
                    <div className={`status ${account.connected ? 'connected' : 'disconnected'}`}>
                      {account.connected ? `Connected: ${account.account_name}` : 'Not connected'}
                    </div>
                  </div>
                  {account.connected ? (
                    <button className="btn btn-danger btn-sm" onClick={() => handleDisconnect(account.platform)}>
                      Disconnect
                    </button>
                  ) : (
                    <button className="btn btn-primary btn-sm" onClick={() => handleConnect(account.platform)}>
                      Connect
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
        <ContentGenerator accounts={accounts} />
      </div>
    </>
  );
}

export default Dashboard;
