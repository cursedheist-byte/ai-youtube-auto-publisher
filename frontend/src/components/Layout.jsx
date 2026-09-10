import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import {AchievementToast, SubscribeDeveloper} from "./DeveloperSubscribe";

const adminNav=[["/dashboard","Overview","⌂"],["/drive-sources","Drive Sources","◫"]];
export default function Layout({children}){
 const {user,logout}=useAuth(); const loc=useLocation(); const nav=user?.role==="admin"?adminNav:[["/app","Dashboard","⌂"]];
 return <div className="app-shell text-paper"><div className="fixed inset-0 grid-bg pointer-events-none opacity-50"/>
  <aside className="fixed z-30 hidden h-screen w-64 border-r border-white/10 bg-[#070707]/90 p-4 backdrop-blur-xl lg:flex lg:flex-col">
   <Link to="/" className="mb-8 flex items-center gap-3 px-3 pt-2"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-black font-bold">•</span><div><div className="font-display font-bold text-sm">AUTO PUBLISHER</div><div className="text-[9px] uppercase tracking-[.2em] text-neutral-600">control room</div></div></Link>
   <div className="eyebrow px-3 mb-3">{user?.role==="admin"?"ADMIN":"CHANNEL"}</div>
   <nav className="space-y-1">{nav.map(([to,label,icon])=><Link key={to} to={to} className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition ${loc.pathname===to?"bg-white text-black font-semibold":"text-neutral-400 hover:bg-white/[.05] hover:text-white"}`}><span className="w-5 text-center">{icon}</span>{label}</Link>)}</nav>
   <div className="mt-auto"><SubscribeDeveloper compact/><div className="mt-3 rounded-2xl border border-white/10 bg-white/[.025] p-3"><p className="truncate text-xs">{user?.email}</p><p className="mt-1 text-[10px] uppercase tracking-widest text-neutral-600">{user?.role}</p><button onClick={logout} className="mt-4 w-full rounded-xl border border-white/10 px-3 py-2 text-xs text-neutral-400 hover:text-white">Log out</button></div></div>
      </aside>
  <div className="lg:pl-64"><header className="sticky top-0 z-20 border-b border-white/8 bg-[#050505]/75 px-5 py-4 backdrop-blur-xl lg:px-8"><div className="flex items-center justify-between"><div className="lg:hidden font-display font-bold text-sm">AUTO PUBLISHER</div><div className="hidden lg:block text-xs text-neutral-600">{user?.role==="admin"?"SYSTEM / ADMIN":"WORKSPACE / CHANNEL"}</div><div className="flex items-center gap-3"><span className="hidden sm:block text-[10px] uppercase tracking-widest text-neutral-600">{user?.role}</span><span className="h-2 w-2 rounded-full bg-white pulse-dot"/></div></div></header><main className="relative">{children}</main></div>
     <AchievementToast/></div>;
   }
