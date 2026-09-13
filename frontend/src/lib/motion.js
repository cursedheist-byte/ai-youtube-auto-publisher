import { useEffect, useRef } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

export const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Staggered reveal of direct children on mount (motion.csv #5/#8). */
export function useStaggerIn(selector = ":scope > *", opts = {}) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || reducedMotion()) return;
    const ctx = gsap.context(() => {
      gsap.from(selector, {
        opacity: 0,
        y: 24,
        scale: 0.97,
        duration: 0.5,
        stagger: 0.07,
        ease: "power2.out",
        ...opts,
      });
    }, ref);
    return () => ctx.revert();
  }, []);
  return ref;
}

/** Fade-up reveal when element scrolls into view (motion.csv #4). */
export function useScrollReveal() {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current || reducedMotion()) return;
    const ctx = gsap.context(() => {
      gsap.from(ref.current, {
        opacity: 0,
        y: 20,
        duration: 0.55,
        ease: "power2.out",
        scrollTrigger: { trigger: ref.current, start: "top 88%", toggleActions: "play none reverse" },
      });
    });
    return () => ctx.revert();
  }, []);
  return ref;
}

/**
 * 3D tilt + magnetic glow that tracks the pointer (motion.csv #3).
 * Returns { ref, onMove, onLeave } to spread on the card element.
 */
export function useTilt3D(maxDeg = 10) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    el.style.transformStyle = "preserve-3d";
    el.style.willChange = "transform";
    return () => {
      el.style.transform = "";
      el.style.willChange = "";
    };
  }, []);
  const onMove = (e) => {
    const el = ref.current;
    if (!el || reducedMotion()) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    gsap.to(el, {
      rotateY: px * maxDeg * 2,
      rotateX: -py * maxDeg * 2,
      y: -4,
      duration: 0.35,
      ease: "power2.out",
      transformPerspective: 900,
    });
  };
  const onLeave = () => {
    const el = ref.current;
    if (!el) return;
    gsap.to(el, { rotateX: 0, rotateY: 0, y: 0, duration: 0.6, ease: "elastic.out(1,0.5)" });
  };
  return { ref, onMove, onLeave };
}

/** Animated number counter that fires on scroll into view. */
export function useCountUp(target, { duration = 1.4 } = {}) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const end = Number(target);
    if (!Number.isFinite(end) || reducedMotion()) {
      el.textContent = String(target);
      return;
    }
    const obj = { v: 0 };
    const tween = gsap.to(obj, {
      v: end,
      duration,
      ease: "power2.out",
      onUpdate: () => { el.textContent = String(Math.round(obj.v)); },
      scrollTrigger: { trigger: el, start: "top 92%", once: true },
    });
    return () => tween.kill();
  }, [target, duration]);
  return ref;
}

export { gsap, ScrollTrigger };
