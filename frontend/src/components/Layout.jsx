import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { AchievementToast, SubscribeDeveloper } from "./DeveloperSubscribe";

const adminNav = [
  ["/dashboard", "Overview", "⌂"],
  ["/drive-sources", "Drive Sources", "◫"],
];
const userNav = [["/app", "Dashboard", "⌂"]];

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-3 px-3 pt-2">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-white font-bold">
        <span className="h-2 w-2 rounded-full bg-[#FF0033]" />
      </span>
      <div>
        <div className="font-display text-sm font-bold tracking-tight">AUTO<span className="text-neutral-500">PUBLISHER</span></div>
        <div className="text-[9px] uppercase tracking-[.2em] text-neutral-600">control room</div>
      </div>
    </Link>
  );
}

function NavLinks({ nav, onNavigate }) {
  const loc = useLocation();
  return (
    <nav className="space-y-1">
      {nav.map(([to, label, icon]) => {
        const active = loc.pathname === to;
        return (
          <Link
            key={to}
            to={to}
            onClick={onNavigate}
            className={`flex items-center gap-3 rounded-[14px] px-3 py-3 text-sm transition ${
              active
                ? "bg-white font-semibold text-black"
                : "text-neutral-400 hover:bg-white/[.05] hover:text-white"
            }`}
          >
            <span className="w-5 text-center">{icon}</span>
            {label}
            {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#FF0033]" />}
          </Link>
        );
      })}
    </nav>
  );
}

function UserCard({ user, logout }) {
  return (
    <div className="mt-3 rounded-[20px] border-white/10 bg-white/[.025] p-3">
      <p className="truncate text-xs">{user?.email}</p>
      <p className="mt-1 text-[10px] uppercase tracking-widest text-neutral-600">{user?.role}</p>
      <button onClick={logout} className="mt-4 w-full rounded-[14px] border-white/10 px-3 py-2 text-xs text-neutral-400 transition hover:border-white/20 hover:text-white">
        Log out
      </button>
    </div>
  );
}

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const nav = user?.role === "admin" ? adminNav : userNav;

  const drawer = (
    <div className="flex h-full flex-col p-4">
      <Logo />
      <div className="eyebrow mb-3 mt-8 px-3">{user?.role === "admin" ? "ADMIN" : "CHANNEL"}</div>
      <NavLinks nav={nav} onNavigate={() => setOpen(false)} />
      <div className="mt-auto">
        <SubscribeDeveloper compact />
        <UserCard user={user} logout={logout} />
      </div>
    </div>
  );

  return (
    <div className="app-shell text-paper">
      <div className="grid-bg pointer-events-none fixed inset-0 opacity-50" />

      {/* Desktop sidebar */}
      <aside className="fixed z-30 hidden h-screen w-64 border-r border-white/10 bg-[#070707]/90 p-4 backdrop-blur-xl lg:flex lg:flex-col">
        {drawer}
      </aside>

      {/* Mobile drawer */}
      <div
        className={`nav-scrim fixed inset-0 z-40 bg-black/60 backdrop-blur-sm lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={() => setOpen(false)}
      />
      <aside className={`nav-drawer fixed inset-y-0 left-0 z-50 w-72 border-r border-white/10 bg-[#070707] lg:hidden ${open ? "open" : ""}`}>
        {drawer}
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-white/[.08] bg-[#050505]/80 px-5 py-4 backdrop-blur-xl lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => setOpen(true)} aria-label="Open menu" className="flex h-9 w-9 items-center justify-center rounded-[14px] border-white/10 text-neutral-300 transition hover:bg-white/5 lg:hidden">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
              </button>
              <div className="hidden text-xs text-neutral-600 lg:block">{user?.role === "admin" ? "SYSTEM / ADMIN" : "WORKSPACE / CHANNEL"}</div>
              <div className="font-display text-sm font-bold lg:hidden">AUTO<span className="text-neutral-500">PUBLISHER</span></div>
            </div>
            <div className="flex items-center gap-3">
              <span className="hidden text-[10px] uppercase tracking-widest text-neutral-600 sm:block">{user?.role}</span>
              <span className="accent-dot pulse-dot h-2 w-2 rounded-full" />
            </div>
          </div>
        </header>
        <main className="relative">{children}</main>
      </div>
      <AchievementToast />
    </div>
  );
}
