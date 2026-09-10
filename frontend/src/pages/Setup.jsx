import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getCredentialSettings, saveCredentialSettings, redeemAccessCode, isAccessConfigured } from "../api/access";
import { useAuth } from "../context/AuthContext";
import CredentialGuide from "../components/CredentialGuide";

export default function Setup(){
  const nav=useNavigate(); const {user}=useAuth();
  const [choice,setChoice]=useState("own"); const [form,setForm]=useState({google_client_id:"",google_client_secret:"",openrouter_api_key:""});
  const [code,setCode]=useState(""); const [mode,setMode]=useState(null); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  const [showGuide,setShowGuide]=useState(false);
  useEffect(()=>{
    getCredentialSettings().then(d=>{
      if(user?.role === "admin" || isAccessConfigured(d)){ nav("/dashboard", {replace:true}); return; }
      setMode(d);
    }).catch(()=>setError("We couldn't verify your setup status. Please try again."));
  },[nav,user?.role]);
  async function submit(){
    setError("");setBusy(true);
    try {
      if(choice==="own"){ await saveCredentialSettings(form); nav("/app"); }
      else { await redeemAccessCode(code); nav("/app"); }
    } catch(e){setError(e.response?.data?.detail||"We couldn't complete setup.");} finally{setBusy(false);}
  }
  if(!mode) return <div className="min-h-screen bg-[#050505] text-white flex items-center justify-center px-5 noise"><span className="text-sm text-neutral-500">Checking setup status…</span></div>;

  return <div className="min-h-screen bg-[#050505] text-white px-5 py-8 noise">
    <div className="fixed inset-0 grid-bg pointer-events-none"/>
    <div className="relative mx-auto max-w-5xl">
      <header className="flex items-center justify-between"><div className="font-display font-bold tracking-tight">AUTO<span className="text-neutral-500">PUBLISHER</span></div><span className="eyebrow">SETUP / 01</span></header>
      <div className="mx-auto max-w-3xl py-14 sm:py-20"><div className="eyebrow">WELCOME TO YOUR CONTROL ROOM</div><h1 className="mt-4 font-display text-5xl font-bold tracking-[-.04em] sm:text-7xl">Let's connect<br/><span className="text-neutral-500">your workspace.</span></h1><p className="mt-6 max-w-2xl text-neutral-400">Choose how this account will power YouTube automation. You can use your own credentials or a one-time access code from an administrator.</p>
        <div className="mt-10 grid gap-4 md:grid-cols-2">
          {[["own","Use my own credentials","Your Google OAuth credentials + OpenRouter API key. No application-level upload limit.","UNLIMITED"],["admin","Redeem admin code","Use server-managed credentials with one channel and up to 2 successful uploads/day.","2 / DAY"]].map(([id,title,desc,badge])=><button key={id} onClick={()=>setChoice(id)} className={`text-left rounded-3xl border p-6 transition-all duration-300 ${choice===id?"border-white bg-white text-black shadow-[0_20px_80px_rgba(255,255,255,.10)]":"border-white/10 bg-white/[.035] hover:bg-white/[.06]"}`}><div className="flex items-center justify-between"><span className={`h-8 w-8 rounded-xl flex items-center justify-center border ${choice===id?"border-black/15":"border-white/10"}`}>{choice===id?"✓":id==="own"?"01":"02"}</span><span className={`text-[10px] font-bold tracking-widest ${choice===id?"text-black/50":"text-neutral-500"}`}>{badge}</span></div><h2 className="mt-12 font-display text-2xl font-bold">{title}</h2><p className={`mt-3 text-sm leading-6 ${choice===id?"text-black/60":"text-neutral-500"}`}>{desc}</p></button>)}
        </div>
        <div className="panel mt-5 p-6 sm:p-8">
          {choice==="own"?<div className="space-y-5"><div><h3 className="font-display text-xl font-semibold">Your credentials</h3><p className="mt-1 text-sm text-neutral-500">They are sent to the backend; secrets are never shown back in plaintext.</p></div>
            {[["google_client_id","Google OAuth Client ID","From Google Cloud Console → OAuth clients."],["google_client_secret","Google OAuth Client Secret","The secret belonging to your web OAuth client."],["openrouter_api_key","OpenRouter API Key","Create an API key in your OpenRouter account."]].map(([k,l,h])=><label key={k} className="block"><span className="mb-2 block text-sm font-medium">{l}</span><input className="field" type={k.includes("secret")||k.includes("key")?"password":"text"} value={form[k]} onChange={e=>setForm({...form,[k]:e.target.value})} placeholder={h}/></label>)}
            <div className="rounded-2xl border border-amber-300/20 bg-amber-300/5 p-4 text-xs leading-5 text-amber-100"><strong>Reminder:</strong> Don't forget to enable <strong>YouTube Data API v3</strong> and <strong>Google Drive API</strong> in your Google Cloud Console. Otherwise our services may not work.</div><div className="rounded-2xl border-white/8 bg-white/[.025] p-4 text-xs leading-5 text-neutral-500">Tip: use the exact OAuth redirect URI shown by your deployment when configuring Google.</div><button type="button" onClick={()=>setShowGuide(!showGuide)} className="btn-ghost w-full py-3 text-sm">{showGuide?"Hide credential guide":"How to get these keys?"}</button>{showGuide&&<CredentialGuide/>}
          </div>:<div><h3 className="font-display text-xl font-semibold">One-time access code</h3><p className="mt-1 text-sm text-neutral-500">Enter the code provided by your administrator. The code can only be redeemed once.</p><input className="field mt-6 text-center font-display tracking-[.2em]" value={code} onChange={e=>setCode(e.target.value)} placeholder="ENTER ACCESS CODE" autoComplete="off"/><div className="mt-4 grid grid-cols-2 gap-3"><div className="panel-soft p-4"><div className="text-xs text-neutral-500">CHANNELS</div><div className="mt-2 font-display text-xl font-semibold">1 maximum</div></div><div className="panel-soft p-4"><div className="text-xs text-neutral-500">UPLOADS</div><div className="mt-2 font-display text-xl font-semibold">2 / day</div></div></div></div>}
          {error&&<div className="mt-5 rounded-xl border border-red-400/20 bg-red-400/5 p-3 text-sm text-red-200">{error}</div>}
          <button disabled={busy} onClick={submit} className="btn-primary mt-7 w-full py-3.5 disabled:opacity-50">{busy?"Saving…":choice==="own"?"Save & enter dashboard":"Redeem & enter dashboard"} <span className="ml-2">→</span></button>
        </div>
      </div>
    </div>
  </div>;
}
