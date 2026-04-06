import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./Login.css";

type Panel = "login" | "signup";

const Login: React.FC = () => {
  const navigate = useNavigate();

  // auth
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // ui
  const [panel, setPanel] = useState<Panel>("login");
  const [animating, setAnimating] = useState(false);

  // refs
  const shellRef = useRef<HTMLDivElement>(null);
  const leftPanelRef = useRef<HTMLDivElement>(null);
  const leftContentRef = useRef<HTMLDivElement>(null);
  const rightPanelRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLDivElement>(null);
  const robotRef = useRef<HTMLDivElement>(null);
  const circuitRef = useRef<HTMLDivElement>(null);
  const meshRef = useRef<HTMLDivElement>(null);
  const rippleRef = useRef<HTMLSpanElement | null>(null);
  const roadTrailTimer = useRef<number | null>(null);

  // ripple
  useEffect(() => {
    if (!shellRef.current) return;
    const r = document.createElement("span");
    r.className = "ripple";
    shellRef.current.appendChild(r);
    rippleRef.current = r;
    return () => r.remove();
  }, []);

  // hover glow
  useEffect(() => {
    const btn = buttonRef.current;
    const circuit = circuitRef.current;
    const mesh = meshRef.current;
    if (!btn) return;

    const enter = () => { circuit?.classList.add("glow"); mesh?.classList.add("glow"); };
    const leave = () => { if (!animating) { circuit?.classList.remove("glow"); mesh?.classList.remove("glow"); } };

    btn.addEventListener("mouseenter", enter);
    btn.addEventListener("mouseleave", leave);
    return () => {
      btn.removeEventListener("mouseenter", enter);
      btn.removeEventListener("mouseleave", leave);
    };
  }, [animating]);

  // click: drive → fly → toggle
  useEffect(() => {
    const btn = buttonRef.current;
    if (!btn) return;

    const handle = () => {
      if (animating) return;
      setAnimating(true);
      circuitRef.current?.classList.add("glow");
      meshRef.current?.classList.add("glow");
      startRoadTrail();
      robotRef.current?.classList.add("drive");

      const onEnd = () => {
        robotRef.current?.classList.remove("drive");
        stopRoadTrail();
        flyToLeftAndSwap();
        robotRef.current?.removeEventListener("animationend", onEnd);
      };
      robotRef.current?.addEventListener("animationend", onEnd, { once: true });
    };

    btn.addEventListener("click", handle);
    return () => btn.removeEventListener("click", handle);
  }, [animating, panel]);

  // dummy auth
  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (email === "test@clinic.com" && password === "health123") {
      localStorage.setItem("isLoggedIn", "true");
      localStorage.setItem("user", JSON.stringify({ email }));
      navigate("/dashboard");
    } else {
      alert("Invalid email or password");
    }
  };

  // helpers
  const startRoadTrail = () => {
    stopRoadTrail();
    roadTrailTimer.current = window.setInterval(() => {
      const robot = robotRef.current, shell = shellRef.current;
      if (!robot || !shell) return;
      const rb = robot.getBoundingClientRect();
      const sh = shell.getBoundingClientRect();
      const dot = document.createElement("span");
      dot.className = "trail-dot";
      dot.style.left = `${rb.left + rb.width / 2 - sh.left}px`;
      dot.style.top = `${rb.top + rb.height / 2 - sh.top}px`;
      shell.appendChild(dot);
      setTimeout(() => dot.remove(), 800);
    }, 70);
  };
  const stopRoadTrail = () => {
    if (roadTrailTimer.current) {
      clearInterval(roadTrailTimer.current);
      roadTrailTimer.current = null;
    }
  };

  const flyToLeftAndSwap = () => {
    const button = buttonRef.current, robot = robotRef.current, shell = shellRef.current,
          leftPanel = leftPanelRef.current, ripple = rippleRef.current;
    if (!button || !robot || !shell || !leftPanel || !ripple) return;

    const roadRect = button.getBoundingClientRect();
    const shellRect = shell.getBoundingClientRect();
    const startX = roadRect.left + roadRect.width - 30;
    const startY = roadRect.top + roadRect.height / 2;

    const leftRect = leftPanel.getBoundingClientRect();
    const targetX = leftRect.left + 80;
    const targetY = leftRect.bottom - 54;

    const fly = document.createElement("div");
    fly.className = "fly-bot";
    fly.innerHTML = robot.innerHTML || "";
    fly.style.left = `${startX - shellRect.left}px`;
    fly.style.top = `${startY - shellRect.top}px`;
    shell.appendChild(fly);

    const startTime = performance.now();
    const duration = 900;
    let lastAirTrail = 0;

    const tween = (now: number) => {
      const t = Math.min(1, (now - startTime) / duration);
      const e = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      const arc = Math.sin(Math.PI * t) * 62;
      const x = startX + (targetX - startX) * e - shellRect.left;
      const y = startY + (targetY - startY) * e - arc - shellRect.top;

      fly.style.left = `${x}px`;
      fly.style.top = `${y}px`;

      if (now - lastAirTrail > 80) {
        lastAirTrail = now;
        const dot = document.createElement("span");
        dot.className = "trail-dot air";
        dot.style.left = `${x}px`;
        dot.style.top = `${y}px`;
        shell.appendChild(dot);
        setTimeout(() => dot.remove(), 1000);
      }

      if (t < 1) requestAnimationFrame(tween);
      else onArrive();
    };

    const onArrive = () => {
      ripple.style.left = `${targetX - shellRect.left}px`;
      ripple.style.bottom = `${shellRect.bottom - leftRect.bottom + 12}px`;
      ripple.classList.add("show");
      setPanel((p) => (p === "login" ? "signup" : "login"));

      setTimeout(() => {
        ripple.classList.remove("show");
        fly.remove();
        setAnimating(false);
        circuitRef.current?.classList.remove("glow");
        meshRef.current?.classList.remove("glow");
      }, 720);
    };

    requestAnimationFrame(tween);
  };

  // left card fragments
  const LoginForm = (
    <>
      <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900">Welcome Back </h2>
      <p className="mt-2 text-slate-600">
        Sign in to continue to <span className="text-blue-600 font-semibold">Agentic AI</span>
      </p>

      <form onSubmit={handleLogin} className="mt-6 space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <input
            type="email"
            placeholder="you@example.com"
            className="w-full px-4 py-3 rounded-xl border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={email}
            onChange={(e)=>setEmail(e.target.value)}
            required
            autoComplete="username"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
          <input
            type="password"
            placeholder="••••••••"
            className="w-full px-4 py-3 rounded-xl border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={password}
            onChange={(e)=>setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </div>
        <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-xl shadow-md">
          Sign In
        </button>

        <p className="text-xs text-slate-500">
          Use <b>test@clinic.com</b> / <b>health123</b>
        </p>

        <p className="text-sm text-slate-600">
          Don’t have an account?{" "}
          <button type="button" onClick={()=>setPanel("signup")} className="text-blue-600 font-medium hover:underline">
            Sign Up
          </button>
        </p>
      </form>
    </>
  );

  const SignupForm = (
    <>
      <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900">Create Account</h2>
      <p className="mt-2 text-slate-600">
        Join the <span className="text-blue-600 font-semibold">Agentic AI</span> community today.
      </p>

      <form onSubmit={(e)=>{ e.preventDefault(); setPanel("login"); }} className="mt-6 space-y-5">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
          <input
            type="text"
            placeholder="Full Name"
            className="w-full px-4 py-3 rounded-xl border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
            autoComplete="name"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
          <input
            type="email"
            placeholder="you@example.com"
            className="w-full px-4 py-3 rounded-xl border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
            autoComplete="email"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
          <input
            type="password"
            placeholder="••••••••"
            className="w-full px-4 py-3 rounded-xl border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
            autoComplete="new-password"
          />
        </div>
        <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-xl shadow-md">
          Sign Up
        </button>
      </form>
    </>
  );

  return (
    <div className="min-h-screen flex items-center justify-center bg-ai">
      {/* overlays */}
      <div ref={circuitRef} className="ai-circuit" aria-hidden="true">
        <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none">
          <path d="M2,8 C10,8 14,12 20,14 S32,18 38,18" vectorEffect="non-scaling-stroke" />
          <path d="M6,14 C14,14 22,20 30,24 S42,28 52,28" vectorEffect="non-scaling-stroke" />
          <circle cx="38" cy="18" r="1.2" />
          <circle cx="52" cy="28" r="1.2" />
          <path d="M98,10 L86,18 L86,34 L78,40" vectorEffect="non-scaling-stroke" />
          <path d="M98,40 L90,46 L90,70" vectorEffect="non-scaling-stroke" />
          <circle cx="86" cy="34" r="1.1" />
          <circle cx="90" cy="70" r="1.1" />
          <path d="M4,92 C26,84 36,84 58,92 S90,96 100,90" vectorEffect="non-scaling-stroke" />
          <circle cx="58" cy="92" r="1.2" />
        </svg>
      </div>
      <div ref={meshRef} className="ai-mesh" aria-hidden="true" />
      <span className="ai-sparkle s1" />
      <span className="ai-sparkle s2" />
      <span className="ai-sparkle s3" />
      <span className="ai-sparkle s4" />

      {/* two-card frame */}
      <div
        id="shell"
        ref={shellRef}
        className="relative w-[96%] max-w-5xl rounded-3xl shadow-2xl overflow-hidden
                   border border-slate-200/60 bg-white grid md:grid-cols-2"
      >
        {/* LEFT: white card */}
        <div id="leftPanel" ref={leftPanelRef} className="bg-white px-6 md:px-10 py-8 md:py-12">
          <div id="leftContent" ref={leftContentRef} className="w-full max-w-md">
            <div className="space-y-6">{panel === "login" ? LoginForm : SignupForm}</div>
          </div>
        </div>

        {/* RIGHT: dark card with button */}
        <div className="bg-[#0b1440] px-6 md:px-10 py-8 md:py-12 relative">
          <div className="hidden md:block absolute left-0 top-0 h-full w-px bg-white/10" />
          <div id="rightPanel" ref={rightPanelRef} className="h-full w-full flex items-center justify-center">
            <div className="flex flex-col items-center gap-6">
              <div id="agenticButton" ref={buttonRef} className="button-track">
                <div id="robot" ref={robotRef} className="robot">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" aria-label="Agentic bot">
                    <circle cx="50" cy="50" r="30" fill="#38bdf8" stroke="#93c5fd" strokeWidth="4" />
                    <circle cx="40" cy="45" r="5" fill="#0f172a" />
                    <circle cx="60" cy="45" r="5" fill="#0f172a" />
                    <rect x="43" y="60" width="14" height="8" rx="4" fill="#0ea5e9" />
                    <rect x="30" y="30" width="10" height="8" rx="3" fill="#93c5fd" transform="rotate(-20 35 34)" />
                    <rect x="60" y="30" width="10" height="8" rx="3" fill="#93c5fd" transform="rotate(20 65 34)" />
                    <rect x="45" y="75" width="10" height="15" rx="2" fill="#60a5fa" />
                    <rect x="35" y="75" width="10" height="15" rx="2" fill="#60a5fa" />
                    <rect x="55" y="75" width="10" height="15" rx="2" fill="#60a5fa" />
                  </svg>
                </div>
                <div className="button-label">AGENTIC AI</div>
              </div>

              <p className="text-sm text-white/70 text-center max-w-xs">
                Tip: Click the Agentic AI button to toggle between <b>Login</b> and <b>Create Account</b>.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Login;
