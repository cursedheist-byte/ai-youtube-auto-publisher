import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { gsap, reducedMotion, useTilt3D, useCountUp, useScrollReveal } from "../lib/motion";

function Mark() {
  return <div className="flex items-center gap-2 font-display font-bold tracking-tight">
    <span className="relative flex h-8 w-8 items-center justify-center rounded-xl bg-white shadow-[0_0_35px_rgba(255,0,51,.22)]">
      <span className="h-2 w-2 rounded-[2px] bg-[#FF003]"/>
    </span>
    AUTO<span className="text-neutral-500">PUBLISHER</span>
 </div>;
}

/** 3D-tilting pipeline chip used in the hero orbit visual. */
function TiltChip({ label, sub, icon, className }) {
  const tilt = useTilt3D(14);
  return <div ref={tilt.ref} onMouseMove={tilt.onMove} onMouseLeave={tilt.onLeave}
    className={`absolute ${className} glass cursor-pointer rounded-2xl px-4 py-3 w-44 will-change-transform`}>
    <div className="flex items-center justify-between"><span className="text-[10px] font-bold tracking-[.15em] text-neutral-400">{label}</span><span>{icon}</span></div>
    <p className="mt-1 text-xs text-white">{sub}</p>
 </div>;
}

function MagneticButton({ to, className, children }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    const xTo = gsap.quickTo(el, "x", { duration: 0.3, ease: "power2.out" });
    const yTo = gsap.quickTo(el, "y", { duration: 0.3, ease: "power2.out" });
    const move = (e) => {
      const r = el.getBoundingClientRect();
      xTo((e.clientX - r.left - r.width / 2) * 0.18);
      yTo((e.clientY - r.top - r.height / 2) * 0.28);
    };
    const leave = () => { xTo(0); yTo(0); };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => { el.removeEventListener("pointermove", move); el.removeEventListener("pointerleave", leave); };
  }, []);
  return <Link ref={ref} to={to} className={`inline-block will-change-transform ${className}`}>{children}</Link>;
}

function HeroHeadline() {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    const words = el.querySelectorAll("[data-word]");
    const tween = gsap.from(words, {
      opacity: 0, y: 44, rotateX: -55,
      transformPerspective: 800, transformOrigin: "50% 100%",
      duration: 0.85, stagger: 0.09, ease: "expo.out", delay: 0.1,
    });
    return () => tween.kill();
  }, []);
  return <h1 ref={ref} className="max-w-3xl font-display text-6xl font-bold leading-[.94] tracking-[-.05em] sm:text-7xl lg:text-[92px] [perspective:800px]">
    <span data-word className="inline-block">Your</span> <span data-word className="inline-block">YouTube.</span><br/>
    <span data-word className="inline-block text-neutral-500">On</span> <span data-word className="inline-block text-neutral-500">autopilot.</span>
 </h1>;
}

function HeroVisual() {
  const wrap = useRef(null);
  // Mouse-tracked scene parallax (motion.csv #13 — decorative layers only)
  useEffect(() => {
    const el = wrap.current;
    if (!el || reducedMotion()) return;
    const xTo = gsap.quickTo(el, "rotationY", { duration: 0.6, ease: "power2.out" });
    const yTo = gsap.quickTo(el, "rotationX", { duration: 0.6, ease: "power2.out" });
    const move = (e) => {
      const px = e.clientX / window.innerWidth - 0.5;
      const py = e.clientY / window.innerHeight - 0.5;
      xTo(px * 10); yTo(-py * 8);
    };
    window.addEventListener("pointermove", move);
    return () => window.removeEventListener("pointermove", move);
  }, []);
  return <div className="relative mx-auto h-[390px] w-full max-w-[560px] [perspective:1200px]">
    <div ref={wrap} className="absolute inset-0 will-change-transform [transform-style:preserve-3d]">
      <div className="absolute inset-10 rounded-full border-white/10 orbit"/>
      <div className="absolute inset-20 rounded-full border-white/10 orbit" style={{animationDirection:"reverse",animationDuration:"24s"}}/>
      <div className="absolute left-1/2 top-1/2 z-10 h-28 w-28 -translate-x-1/2 -translate-y-1/2 rounded-[32px] bg-white text-black shadow-[0_30px_100px_rgba(255,0,51,.20)] flex items-center justify-center float">
        <div className="text-center"><div className="text-3xl font-display font-bold">AI</div><div className="text-[9px] uppercase tracking-[.25em] mt-1 opacity-60">engine</div></div>
      </div>
      <TiltChip label="DRIVE" sub="Content source" icon="→" className="left-2 top-20" />
      <TiltChip label="METADATA" sub="AI optimized" icon="→" className="right-0 top-12" />
      <TiltChip label="YOUTUBE" sub="Auto publish" icon="✓" className="right-8 bottom-16" />
      <TiltChip label="MIX / CATEGORIES" sub="Smart selection" icon="→" className="left-0 bottom-12" />
    </div>
 </div>;
}

function Stat({ value, label }) {
  const countRef = useCountUp(value);
  return <div className="text-center">
    <div ref={countRef} className="font-display text-3xl font-bold sm:text-4xl">{value}</div>
    <div className="eyebrow mt-2">{label}</div>
 </div>;
}

function FlowCard({ n, t, d }) {
  const tilt = useTilt3D(6);
  const reveal = useScrollReveal();
  return <div ref={reveal}>
    <div ref={tilt.ref} onMouseMove={tilt.onMove} onMouseLeave={tilt.onLeave}
      className="panel dashboard-card h-full p-6 will-change-transform">
      <span className="text-xs text-[#FF003]">{n}</span>
      <h3 className="mt-10 font-display text-xl font-semibold">{t}</h3>
      <p className="mt-2 text-sm leading-6 text-neutral-500">{d}</p>
    </div>
 </div>;
}

export default function Landing(){
  const features=["Automated publishing","Google Drive sources","Smart categories + Mix","AI-powered metadata","Duplicate protection","Scheduled uploads","Multi-channel support","One-time admin access"];
  return <div className="noise min-h-screen overflow-hidden bg-[#0505] text-white">
    <div className="fixed inset-0 grid-bg pointer-events-none"/>
    <nav className="relative z-20 mx-auto flex max-w-7xl items-center justify-between px-6 py-6 lg:px-10">
      <Mark/><div className="hidden md:flex items-center gap-8 text-sm text-neutral-400"><a href="#features" className="transition hover:text-white">Features</a><a href="#flow" className="transition hover:text-white">How it works</a></div>
      <div className="flex gap-2"><Link to="/login" className="btn-ghost px-4 py-2.5 text-sm">Sign in</Link><Link to="/register" className="btn-primary px-4 py-2.5 text-sm">Get started</Link></div>
    </nav>
    <main className="relative z-10">
      <section className="mx-auto grid max-w-7xl items-center gap-10 px-6 pb-20 pt-12 lg:grid-cols-[1fr_1fr] lg:px-10 lg:pb-32 lg:pt-20">
        <div>
          <div className="eyebrow mb-5 flex items-center gap-2"><span className="pulse-dot h-1.5 w-1.5 rounded-full bg-white"/> AI VIDEO OPERATIONS</div>
          <HeroHeadline/>
          <p className="mt-7 max-w-xl text-base leading-7 text-neutral-400 sm:text-lg">Turn Google Drive into an automated publishing pipeline. Pick a category, let AI prepare the metadata, and publish without the repetitive work.</p>
          <div className="mt-8 flex-wrap gap-3">
            <MagneticButton to="/register" className="btn-primary px-6 py-3.5">Build your pipeline <span className="ml-2">↗</span></MagneticButton>
            <a href="#flow" className="btn-ghost inline-block px-6 py-3.5">See how it works</a>
          </div>
          <div className="mt-9 flex gap-6 text-xs text-neutral-500"><span className="flex items-center gap-2"><span className="accent-dot h-1.5 w-1.5 rounded-full"/>01 / SOURCE</span><span>02 / AI</span><span>03 / PUBLISH</span></div>
        </div>
        <div><HeroVisual/></div>
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-16 lg:px-10">
        <div className="panel-soft grid-cols-2 gap-6 p-8 sm:grid-cols-4">
          <Stat value={79} label="UI STYLES"/><Stat value={192} label="PALETTES"/><Stat value={24} label="AUTOMATION"/><Stat value={1} label="CLICK PUBLISH"/>
        </div>
      </section>

      <section id="flow" className="border-y border-white/10 bg-white/[.018]">
        <div className="mx-auto max-w-7xl px-6 py-20 lg:px-10 lg:py-28">
          <div className="grid gap-12 lg:grid-cols-[.7fr_1.3fr]"><div><div className="eyebrow">THE PIPELINE</div><h2 className="mt-4 font-display text-4xl font-bold tracking-tight sm:text-5xl">From folder<br/>to published.</h2></div>
          <div className="grid gap-3 sm:grid-cols-2">{[["01","Connect","Bring in one or more Drive folders."],["02","Organize","Assign folders to categories or use Mix."],["03","Generate","AI creates titles, descriptions and tags."],["04","Publish","Manual or scheduled YouTube uploads."]].map(([n,t,d])=><FlowCard key={n} n={n} t={t} d={d}/>)}</div></div>
        </div>
      </section>

      <section id="features" className="mx-auto max-w-7xl px-6 py-20 lg:px-10 lg:py-28">
        <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end"><div><div className="eyebrow">BUILT FOR CONTROL</div><h2 className="mt-4 font-display text-4xl font-bold tracking-tight sm:text-5xl">Everything in one place.</h2></div><p className="max-w-md text-sm leading-6 text-neutral-500">A focused control center for content sources, channel automation and publishing history.</p></div>
        <div className="mt-12 grid gap-px overflow-hidden rounded-3xl border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-4">{features.map((x,i)=><div key={x} className="dashboard-card group bg-[#0b0b0b] p-6 min-h-36"><span className="text-xs text-neutral-600 transition group-hover:text-[#FF003]">0{i+1}</span><h3 className="mt-8 text-sm font-semibold">{x}</h3></div>)}</div>
      </section>

      <section className="mx-auto max-w-5xl px-6 pb-28 pt-8 text-center"><div className="panel relative overflow-hidden px-6 py-16 sm:px-12"><div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(255,0,51,.08),transparent_55%)]"/><div className="relative"><div className="eyebrow">READY WHEN YOU ARE</div><h2 className="mx-auto mt-4 max-w-2xl font-display text-4xl font-bold tracking-tight sm:text-6xl">Stop publishing manually.</h2><p className="mx-auto mt-5 max-w-xl text-neutral-400">Set up your pipeline once. Let the system handle the repetitive part.</p><MagneticButton to="/register" className="btn-primary mt-8 px-7 py-3.5">Get started ↗</MagneticButton></div></div></section>
    </main>
    <footer className="border-t border-white/10 px-6 py-8 text-center text-xs text-neutral-600">AUTO PUBLISHER · AI VIDEO OPERATIONS</footer>
 </div>;
}
