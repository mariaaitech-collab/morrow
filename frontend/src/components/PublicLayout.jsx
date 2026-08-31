import { useState } from 'react';
import Navbar from './Navbar';
import Footer from './Footer';

export default function PublicLayout({ children, active }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('brandora_user');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const handleLogout = () => {
    localStorage.removeItem('brandora_token');
    localStorage.removeItem('brandora_user');
    setUser(null);
    window.location.href = '/login';
  };

  return (
    <>
      <Navbar user={user} onLogout={handleLogout} active={active} />
      <main>{children}</main>
      <Footer />
    </>
  );
}
