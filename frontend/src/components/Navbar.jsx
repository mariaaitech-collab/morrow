import { Link } from 'react-router-dom';

function Navbar({ user, onLogout, active }) {
  return (
    <nav className="navbar">
      <div className="navbar-brand">Brandora<span>Social</span></div>
      <div className="nav-links">
        <Link to="/" className={`nav-link ${active === 'dashboard' ? 'active' : ''}`}>
          Dashboard
        </Link>
        <Link to="/scheduler" className={`nav-link ${active === 'scheduler' ? 'active' : ''}`}>
          Auto Scheduler
        </Link>
      </div>
      <div className="navbar-user">
        <span>{user.username}</span>
        <button className="btn btn-outline btn-sm" onClick={onLogout}>Logout</button>
      </div>
    </nav>
  );
}

export default Navbar;