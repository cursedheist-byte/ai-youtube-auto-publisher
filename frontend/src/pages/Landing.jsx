import { Link } from "react-router-dom";

function Mark() {
  return <div className="flex items-center gap-2 font-display font-bold tracking-tight">
    <span className="relative flex h-8 w-8 items-center justify-center rounded-xl bg-white text-black shadow-[0_0_35px_rgba(255,255,255,.12)]">
      <span className="h-2 w-2 rounded-full bg-black"/>
    </span>
    AUTO<span className="text-neutral-500">PUBLISHER</span>
  </div>;
}
function HeroVisual() {
  return <div className="relative mx-auto h-[390px] w-full max-w-[560px] [perspective:1200px]">
    <div className="absolute inset-10 rounded-full border border-white/10 orbit"/>
    <div className="absolute inset-20 rounded-full border border-white/10 orbit" style={{animationDirection:"reverse",animationDuration:"24s"}}/>
    <div className="absolute left-1/2 top-1/2 z-10 h-28 w-28 -translate-x-1/2 -translate-y-1/2 rounded-[32px] bg-white text-black shadow-[0_30px_100px_rgba(255,255,255,.18)] flex items-center justify-center float">
      <div className="text-center"><div className="text-3xl font-display font-bold">AI</div><div className="text-[9px] uppercase tracking-[.25em] mt-1 opacity-60">engine</div></div>
    </div>
    {[
      ["DRIVE","Content source","left-2 top-20","→"],
      ["METADATA","AI optimized","right-0 top-12","→"],
      ["YOUTUBE","Auto publish","right-8 bottom-16","✓"],
      ["MIX / CATEGORIES","Smart selection","left-0 bottom-12","→"],
    ].map(([a,b,pos,icon])=><div key={a} className={`absolute ${pos} glass rounded-2xl px-4 py-3 w-44 float`} style={{animationDelay:`${Math.random()*-2}s`}}>
      <div className="flex items-center justify-between"><span className="text-[10px] font-bold tracking-[.15em] text-neutral-400">{a}</span><span>{icon}</span></div><p className="mt-1 text-xs text-white">{b}</p>
    </div>)}
  </div>;
}
export default function Landing(){
  const features=["Automated publishing","Google Drive sources","Smart categories + Mix","AI-powered metadata","Duplicate protection","Scheduled uploads","Multi-channel support","One-time admin access"];
  return <div className="noise min-h-screen overflow-hidden bg-[#050505] text-white">
    <div className="fixed inset-0 grid-bg pointer-events-none"/>
    <nav className="relative z-20 mx-auto flex max-w-7xl items-center justify-between px-6 py-6 lg:px-10">
      <Mark/><div className="hidden md:flex items-center gap-8 text-sm text-neutral-400"><a href="#features" className="hover:text-white transition">Features</a><a href="#flow" className="hover:text-white transition">How it works</a></div>
      <div className="flex gap-2"><Link to="/login" className="btn-ghost px-4 py-2.5 text-sm">Sign in</Link><Link to="/register" className="btn-primary px-4 py-2.5 text-sm">Get started</Link></div>
    </nav>
    <main className="relative z-10">
      <section className="mx-auto grid max-w-7xl items-center gap-10 px-6 pb-20 pt-12 lg:grid-cols-[1fr_1fr] lg:px-10 lg:pb-32 lg:pt-20">
        <div className="reveal">
          <div className="eyebrow mb-5 flex items-center gap-2"><span className="pulse-dot h-1.5 w-1.5 rounded-full bg-white"/> AI VIDEO OPERATIONS</div>
          <h1 className="max-w-3xl font-display text-6xl font-bold leading-[.94] tracking-[-.05em] sm:text-7xl lg:text-[92px]">Your YouTube.<br/><span className="text-neutral-500">On autopilot.</span></h1>
          <p className="mt-7 max-w-xl text-base leading-7 text-neutral-400 sm:text-lg">Turn Google Drive into an automated publishing pipeline. Pick a category, let AI prepare the metadata, and publish without the repetitive work.</p>
          <div className="mt-8 flex flex-wrap gap-3"><Link to="/register" className="btn-primary px-6 py-3.5">Build your pipeline <span className="ml-2">↗</span></Link><a href="#flow" className="btn-ghost px-6 py-3.5">See how it works</a></div>
          <div className="mt-9 flex gap-6 text-xs text-neutral-500"><span>01 / SOURCE</span><span>02 / AI</span><span>03 / PUBLISH</span></div>
        </div>
        <div className="reveal" style={{animationDelay:".12s"}}><HeroVisual/></div>
      </section>

      <section id="flow" className="border-y border-white/10 bg-white/[.018]">
        <div className="mx-auto max-w-7xl px-6 py-20 lg:px-10 lg:py-28">
          <div className="grid gap-12 lg:grid-cols-[.7fr_1.3fr]"><div><div className="eyebrow">THE PIPELINE</div><h2 className="mt-4 font-display text-4xl font-bold tracking-tight sm:text-5xl">From folder<br/>to published.</h2></div>
          <div className="grid gap-3 sm:grid-cols-2">{[["01","Connect","Bring in one or more Drive folders."],["02","Organize","Assign folders to categories or use Mix."],["03","Generate","AI creates titles, descriptions and tags."],["04","Publish","Manual or scheduled YouTube uploads."]].map(([n,t,d])=><div className="panel dashboard-card p-6" key={n}><span className="text-xs text-neutral-600">{n}</span><h3 className="mt-10 font-display text-xl font-semibold">{t}</h3><p className="mt-2 text-sm leading-6 text-neutral-500">{d}</p></div>)}</div></div>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-7xl px-6 py-20 lg:px-10 lg:py-28">
        <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end"><div><div className="eyebrow">BUILT FOR CONTROL</div><h2 className="mt-4 font-display text-4xl font-bold tracking-tight sm:text-5xl">Everything in one place.</h2></div><p className="max-w-md text-sm leading-6 text-neutral-500">A focused control center for content sources, channel automation and publishing history.</p></div>
        <div className="mt-12 grid gap-px overflow-hidden rounded-3xl border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-4">{features.map((x,i)=><div key={x} className="dashboard-card bg-[#0b0b0b] p-6 min-h-36"><span className="text-xs text-neutral-600">0{i+1}</span><h3 className="mt-8 text-sm font-semibold">{x}</h3></div>)}</div>
      </section>

      <section className="mx-auto max-w-5xl px-6 pb-28 pt-8 text-center"><div className="panel relative overflow-hidden px-6 py-16 sm:px-12"><div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(255,255,255,.10),transparent_55%)]"/><div className="relative"><div className="eyebrow">READY WHEN YOU ARE</div><h2 className="mx-auto mt-4 max-w-2xl font-display text-4xl font-bold tracking-tight sm:text-6xl">Stop publishing manually.</h2><p className="mx-auto mt-5 max-w-xl text-neutral-400">Set up your pipeline once. Let the system handle the repetitive part.</p><Link to="/register" className="btn-primary mt-8 inline-flex px-7 py-3.5">Get started ↗</Link></div></div></section>
    </main>
    <footer className="border-t border-white/10 px-6 py-8 text-center text-xs text-neutral-600">AUTO PUBLISHER · AI VIDEO OPERATIONS</footer>
  </div>;
}
