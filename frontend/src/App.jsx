import { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import Scheduler from './pages/Scheduler';
import Callback from './pages/Callback';

function App() {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('brandora_user');
    return saved ? JSON.parse(saved) : null;
  });

  const handleAuth = (userData) => {
    setUser(userData);
  };

  const handleLogout = () => {
    localStorage.removeItem('brandora_token');
    localStorage.removeItem('brandora_user');
    setUser(null);
  };

  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: { background: '#1a1a2e', color: '#e0e0e0', border: '1px solid #2a2a3e' },
        }}
      />
      <div className="app">
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/" /> : <Login onAuth={handleAuth} />} />
          <Route path="/register" element={user ? <Navigate to="/" /> : <Register onAuth={handleAuth} />} />
          <Route path="/auth/callback/:platform" element={<Callback />} />
          <Route path="/scheduler" element={user ? <Scheduler user={user} onLogout={handleLogout} /> : <Navigate to="/login" />} />
          <Route path="/*" element={user ? <Dashboard user={user} onLogout={handleLogout} /> : <Navigate to="/login" />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
