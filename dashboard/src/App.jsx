import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  ShieldAlert,
  Camera,
  Store,
  Clock,
  CheckCircle2,
  XCircle,
  TrendingDown,
  Bell,
  BellOff,
  Plus,
  Circle,
  Eye,
  EyeOff,
  Building2,
  LogOut,
  Loader2,
  AlertTriangle,
  Copy,
  Check,
  ArrowRight,
  ArrowLeft,
  Users,
  UserPlus,
  Trash2,
  Mail,
  Menu,
  Download,
  CreditCard,
  QrCode,
  Wifi,
  WifiOff,
  Link2,
} from "lucide-react";

// Em produção, defina VITE_API_BASE (ex: https://api.vigialoja.com.br) nas
// variáveis de ambiente do provedor de hospedagem do dashboard. Sem isso, cai
// no endereço de desenvolvimento local (mesmo host, porta 8000).
const API_BASE = import.meta.env.VITE_API_BASE || `http://${window.location.hostname}:8000`;
const TURNSTILE_SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY || "";

const COLORS = {
  bg: "#0A0F1C",
  panel: "#121A2E",
  panelAlt: "#1A2440",
  border: "#232F4E",
  borderSoft: "#1C2540",
  text: "#E7ECF7",
  textMuted: "#7C8BAD",
  textFaint: "#4C5A7D",
  amber: "#F5A623",
  teal: "#3DD68C",
  red: "#E8483C",
  // Versões "dim" — usadas em glow/borda de destaque e nas barras não
  // destacadas dos mini-gráficos (ver Stat) — tom escurecido da cor
  // correspondente, não uma cor nova sem relação.
  amberDim: "#7A5518",
  redDim: "#5A211C",
  tealDim: "#1C4A38",
  // Verde do ícone da logo (olho) — dedicado, não reaproveita `teal`
  // (que já é usado em vários outros lugares da UI, tipo status "online").
  brandGreen: "#54B833",
};

// Sombra compartilhada — dá profundidade a painéis, cartões e modais sem
// depender de bordas mais fortes (fica sutil demais em fundo escuro sozinha).
const SHADOW = "0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -8px rgba(0,0,0,0.55)";
const SHADOW_SOFT = "0 1px 2px rgba(0,0,0,0.25), 0 4px 14px -6px rgba(0,0,0,0.4)";

const globalFonts = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Manrope:wght@400;500;600;700;800&display=swap');
  * { box-sizing: border-box; }
  .lp-row { transition: background .12s ease, border-color .12s ease; }
  .lp-row:hover { background: ${COLORS.panelAlt} !important; }
  .lp-nav { transition: background .15s ease, color .15s ease; }
  .lp-btn { cursor: pointer; transition: opacity .15s ease, transform .1s ease, background .15s ease, border-color .15s ease; }
  .lp-btn:hover { opacity: 0.85; }
  .lp-btn:active { transform: scale(0.97); }
  .lp-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .lp-scroll::-webkit-scrollbar { width: 6px; }
  .lp-scroll::-webkit-scrollbar-thumb { background: ${COLORS.border}; border-radius: 3px; }
  .lp-spin { animation: lp-spin 0.8s linear infinite; }
  @keyframes lp-spin { to { transform: rotate(360deg); } }
  @keyframes lp-fade-up { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes lp-modal-in { from { opacity: 0; transform: scale(0.97) translateY(6px); } to { opacity: 1; transform: scale(1) translateY(0); } }
  @keyframes lp-overlay-in { from { opacity: 0; } to { opacity: 1; } }
  .lp-fade-up { animation: lp-fade-up .25s ease both; }
  .lp-modal-in { animation: lp-modal-in .18s cubic-bezier(0.16, 1, 0.3, 1) both; }
  .lp-overlay-in { animation: lp-overlay-in .15s ease both; }
  input:focus, textarea:focus { outline: none; border-color: ${COLORS.amber}; }
  :focus-visible { outline: 2px solid ${COLORS.amber}; outline-offset: 2px; }
  /* varredura do radar (estado vazio da lista de eventos) e pulso do
     chip "monitorando ao vivo" */
  @keyframes lp-sweep { to { transform: rotate(360deg); } }
  @keyframes lp-blip { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
  .lp-sweep { animation: lp-sweep 3.6s linear infinite; }
  .lp-blip { animation: lp-blip 1.8s ease-in-out infinite; }
  @media (prefers-reduced-motion: reduce) {
    .lp-fade-up, .lp-modal-in, .lp-overlay-in, .lp-spin, .lp-sweep, .lp-blip { animation: none; }
  }
`;

const inputStyle = {
  width: "100%",
  padding: "9px 10px",
  borderRadius: 7,
  border: `1px solid ${COLORS.border}`,
  background: COLORS.panelAlt,
  color: COLORS.text,
  fontSize: 13,
  transition: "border-color .15s ease",
};

function Field({ label, type, ...props }) {
  const [visible, setVisible] = useState(false);
  const isPassword = type === "password";

  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ fontSize: 12, color: COLORS.textMuted, display: "block", marginBottom: 5 }}>
        {label}
      </label>
      {isPassword ? (
        <div style={{ position: "relative" }}>
          <input type={visible ? "text" : "password"} style={{ ...inputStyle, paddingRight: 34 }} {...props} />
          <button
            type="button"
            tabIndex={-1}
            onClick={() => setVisible((v) => !v)}
            aria-label={visible ? "Ocultar senha" : "Mostrar senha"}
            style={{
              position: "absolute",
              right: 8,
              top: "50%",
              transform: "translateY(-50%)",
              border: "none",
              background: "transparent",
              color: COLORS.textFaint,
              display: "flex",
              padding: 2,
              cursor: "pointer",
            }}
          >
            {visible ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>
      ) : (
        <input type={type} style={inputStyle} {...props} />
      )}
    </div>
  );
}

function Logo({ size = 20, fontSize = 16 }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <img src="/eye-logo.png" alt="" width={size} height={size} style={{ display: "block", borderRadius: "50%" }} />
      <span style={{ fontWeight: 700, fontSize }}>
        vigg<span style={{ color: COLORS.brandGreen }}>IA</span>
      </span>
    </div>
  );
}

function AuthShell({ children, width = 320 }) {
  return (
    <div
      style={{
        fontFamily: "'IBM Plex Sans', sans-serif",
        background: COLORS.bg,
        color: COLORS.text,
        minHeight: "100dvh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <style>{globalFonts}</style>
      <div className="lp-fade-up" style={{ width, background: COLORS.panel, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28, boxShadow: SHADOW }}>
        <div style={{ marginBottom: 22, display: "flex", justifyContent: "center" }}>
          <Logo size={34} fontSize={26} />
        </div>
        {children}
      </div>
    </div>
  );
}

function ErrorNote({ message }) {
  if (!message) return null;
  return (
    <div style={{ marginTop: 6, marginBottom: 8, fontSize: 12.5, color: COLORS.red, display: "flex", alignItems: "center", gap: 6 }}>
      <AlertTriangle size={13} />
      {message}
    </div>
  );
}

function PrimaryButton({ children, loading, ...props }) {
  return (
    <button
      className="lp-btn"
      style={{
        width: "100%",
        padding: "10px 0",
        borderRadius: 8,
        border: "none",
        background: COLORS.amber,
        color: "#1a1200",
        fontWeight: 600,
        fontSize: 13.5,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
      }}
      {...props}
    >
      {loading && <Loader2 size={14} className="lp-spin" />}
      {children}
    </button>
  );
}

// --- LOGIN ------------------------------------------------------------

function Turnstile({ onVerify }) {
  const containerRef = useRef(null);
  const widgetIdRef = useRef(null);

  useEffect(() => {
    if (!TURNSTILE_SITE_KEY || !containerRef.current) return;

    // O script do Turnstile carrega de forma assíncrona (tag no
    // index.html) — espera ficar disponível antes de renderizar o widget.
    let cancelled = false;
    const tryRender = () => {
      if (cancelled) return;
      if (window.turnstile && containerRef.current) {
        widgetIdRef.current = window.turnstile.render(containerRef.current, {
          sitekey: TURNSTILE_SITE_KEY,
          callback: onVerify,
          theme: "dark",
        });
      } else {
        setTimeout(tryRender, 200);
      }
    };
    tryRender();

    return () => {
      cancelled = true;
      if (widgetIdRef.current != null && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!TURNSTILE_SITE_KEY) return null;
  return <div ref={containerRef} style={{ margin: "12px 0", display: "flex", justifyContent: "center" }} />;
}

function LoginScreen({ onLogin, onGoToSignup, onGoToForgot }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [turnstileToken, setTurnstileToken] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/v1/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ email, password, turnstile_token: turnstileToken }),
      });
      if (!res.ok) {
        if (res.status === 429) {
          throw new Error("Muitas tentativas seguidas — aguarde um minuto e tente de novo.");
        }
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Email ou senha inválidos");
      }
      // O token de sessão agora vem só via cookie HttpOnly (Set-Cookie na
      // resposta) — o corpo traz os dados do usuário (MeOut), não o token.
      const data = await res.json();
      onLogin(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell width={380}>
      <form onSubmit={handleSubmit}>
        <Field label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="Senha" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        <div style={{ marginTop: -6, marginBottom: 14, textAlign: "right" }}>
          <span className="lp-btn" onClick={onGoToForgot} style={{ fontSize: 12, color: COLORS.textMuted, textDecoration: "underline" }}>
            Esqueceu a senha?
          </span>
        </div>
        <Turnstile onVerify={setTurnstileToken} />
        <ErrorNote message={error} />
        <PrimaryButton type="submit" loading={loading} disabled={TURNSTILE_SITE_KEY && !turnstileToken}>Entrar</PrimaryButton>
      </form>
      <div style={{ marginTop: 16, fontSize: 12.5, color: COLORS.textMuted, textAlign: "center" }}>
        Ainda não tem conta?{" "}
        <span className="lp-btn" onClick={onGoToSignup} style={{ color: COLORS.amber, textDecoration: "underline" }}>
          Criar conta
        </span>
      </div>
    </AuthShell>
  );
}

// --- RECUPERAÇÃO DE SENHA ------------------------------------------------

function ForgotPasswordScreen({ onGoToLogin }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/v1/auth/forgot-password`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ email, app: "dashboard", turnstile_token: turnstileToken }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        // .error é o formato do slowapi pro 429 por IP (@limiter.limit);
        // .detail é o formato do FastAPI pros outros erros (Turnstile,
        // 429 por email) — sem esse fallback, o 429 por IP cairia na
        // mensagem genérica de baixo.
        throw new Error(body.detail || body.error || "Não foi possível processar o pedido");
      }
      setSent(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <AuthShell width={380}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <div style={{ width: 26, height: 26, borderRadius: "50%", background: "rgba(52,211,153,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Check size={14} color={COLORS.teal} />
          </div>
          <span style={{ fontWeight: 600, fontSize: 14 }}>Verifique seu email</span>
        </div>
        <p style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 4, marginBottom: 18, lineHeight: 1.5 }}>
          Se existir uma conta com o email <strong style={{ color: COLORS.text }}>{email}</strong>, enviamos um
          link para redefinir a senha. Ele expira em 1 hora.
        </p>
        <span className="lp-btn" onClick={onGoToLogin} style={{ color: COLORS.amber, textDecoration: "underline", fontSize: 12.5 }}>
          Voltar para o login
        </span>
      </AuthShell>
    );
  }

  return (
    <AuthShell width={380}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <button
          type="button"
          className="lp-btn"
          onClick={onGoToLogin}
          style={{ border: "none", background: "transparent", color: COLORS.textMuted, display: "flex" }}
        >
          <ArrowLeft size={15} />
        </button>
        <div style={{ fontSize: 13, fontWeight: 600 }}>Esqueceu a senha?</div>
      </div>
      <p style={{ fontSize: 12.5, color: COLORS.textMuted, marginBottom: 18, lineHeight: 1.5 }}>
        Informe o email da sua conta — vamos enviar um link para você criar uma nova senha.
      </p>
      <form onSubmit={handleSubmit}>
        <Field label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Turnstile onVerify={setTurnstileToken} />
        <ErrorNote message={error} />
        <PrimaryButton type="submit" loading={loading} disabled={TURNSTILE_SITE_KEY && !turnstileToken}>Enviar link</PrimaryButton>
      </form>
    </AuthShell>
  );
}

function ResetPasswordScreen({ token, onReset }) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== confirmPassword) {
      setError("As senhas não coincidem");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/v1/auth/reset-password`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ token, password }),
      });
      if (!res.ok) {
        if (res.status === 429) {
          throw new Error("Muitas tentativas seguidas — aguarde um minuto e tente de novo.");
        }
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Não foi possível redefinir a senha — o link pode ter expirado");
      }
      const data = await res.json();
      onReset(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell width={380}>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Criar nova senha</div>
      <form onSubmit={handleSubmit}>
        <Field label="Nova senha" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
        <Field label="Confirme a nova senha" type="password" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
        <ErrorNote message={error} />
        <PrimaryButton type="submit" loading={loading}>Redefinir senha e entrar</PrimaryButton>
      </form>
    </AuthShell>
  );
}

// --- ONBOARDING / SIGNUP -----------------------------------------------

function OnboardingScreen({ onFinished, onGoToLogin, prepaidToken }) {
  const [step, setStep] = useState(1); // 1: empresa+loja, 2: conta do responsável, 3: sucesso
  const [form, setForm] = useState({
    company_name: "",
    store_name: "",
    store_city: "",
    owner_name: "",
    email: "",
    password: "",
  });
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // { store_id, store_edge_api_key }
  const [copied, setCopied] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState("");

  function update(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  function goNext(e) {
    e.preventDefault();
    setStep(2);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (form.password !== confirmPassword) {
      setError("As senhas não coincidem");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/v1/auth/signup`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ ...form, turnstile_token: turnstileToken, prepaid_token: prepaidToken || undefined }),
      });
      if (!res.ok) {
        if (res.status === 429) {
          throw new Error("Muitas tentativas seguidas — aguarde um minuto e tente de novo.");
        }
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Não foi possível criar a conta");
      }
      const data = await res.json();
      setResult(data);
      setStep(3);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function copyKey() {
    navigator.clipboard?.writeText(result.store_edge_api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  // --- passo 3: sucesso, mostra a API key da box de detecção -----------
  if (step === 3 && result) {
    return (
      <AuthShell width={380}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <div style={{ width: 26, height: 26, borderRadius: "50%", background: "rgba(52,211,153,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Check size={14} color={COLORS.teal} />
          </div>
          <span style={{ fontWeight: 600, fontSize: 14 }}>Conta criada</span>
        </div>
        <p style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 4, marginBottom: 18 }}>
          Sua empresa e a primeira loja já estão configuradas. Guarde a chave abaixo — ela é usada para conectar a box de detecção instalada na loja ao seu painel.
        </p>

        <div
          style={{
            fontSize: 10,
            fontFamily: "'IBM Plex Mono', monospace",
            color: COLORS.textFaint,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            marginBottom: 6,
          }}
        >
          Chave da loja (X-API-Key)
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: COLORS.panelAlt,
            border: `1px solid ${COLORS.border}`,
            borderRadius: 7,
            padding: "9px 10px",
            marginBottom: 18,
          }}
        >
          <code style={{ flex: 1, fontSize: 11.5, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {result.store_edge_api_key}
          </code>
          <button
            className="lp-btn"
            onClick={copyKey}
            style={{ border: "none", background: "transparent", color: copied ? COLORS.teal : COLORS.textMuted, display: "flex" }}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
        </div>

        <div style={{ fontSize: 11.5, color: COLORS.textFaint, marginBottom: 20, lineHeight: 1.5 }}>
          Use essa chave em <code style={{ color: COLORS.textMuted }}>config.py</code> do módulo de detecção
          (campo <code style={{ color: COLORS.textMuted }}>api_key</code> da loja) para que os alertas cheguem até este painel.
        </div>

        <PrimaryButton onClick={() => onFinished()}>
          Ir para o painel
          <ArrowRight size={14} />
        </PrimaryButton>
      </AuthShell>
    );
  }

  return (
    <AuthShell width={340}>
      <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
        {[1, 2].map((n) => (
          <div
            key={n}
            style={{
              flex: 1,
              height: 3,
              borderRadius: 2,
              background: step >= n ? COLORS.amber : COLORS.border,
            }}
          />
        ))}
      </div>

      {prepaidToken && (
        <div
          style={{
            display: "flex", alignItems: "center", gap: 8,
            background: "rgba(52,211,153,0.12)", border: `1px solid ${COLORS.teal}`,
            borderRadius: 8, padding: "9px 12px", marginBottom: 16, fontSize: 12,
          }}
        >
          <Check size={14} color={COLORS.teal} />
          <span>Pagamento confirmado! Falta só criar sua conta.</span>
        </div>
      )}

      {step === 1 && (
        <form onSubmit={goNext}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>Sobre o seu negócio</div>
          <Field label="Nome da empresa" required value={form.company_name} onChange={update("company_name")} placeholder="Ex: Mercadinho Boa Vista" />
          <Field label="Nome da primeira loja" required value={form.store_name} onChange={update("store_name")} placeholder="Ex: Loja Centro" />
          <Field label="Cidade da loja" value={form.store_city} onChange={update("store_city")} placeholder="Ex: Manaus, AM" />
          <PrimaryButton type="submit">
            Continuar
            <ArrowRight size={14} />
          </PrimaryButton>
        </form>
      )}

      {step === 2 && (
        <form onSubmit={handleSubmit}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <button
              type="button"
              className="lp-btn"
              onClick={() => setStep(1)}
              style={{ border: "none", background: "transparent", color: COLORS.textMuted, display: "flex" }}
            >
              <ArrowLeft size={15} />
            </button>
            <div style={{ fontSize: 13, fontWeight: 600 }}>Sua conta de acesso</div>
          </div>
          <Field label="Seu nome" required value={form.owner_name} onChange={update("owner_name")} placeholder="Ex: Maria Souza" />
          <Field label="Email" type="email" required value={form.email} onChange={update("email")} />
          <Field label="Senha" type="password" required minLength={8} value={form.password} onChange={update("password")} />
          <Field label="Confirme a senha" type="password" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
          <Turnstile onVerify={setTurnstileToken} />
          <ErrorNote message={error} />
          <PrimaryButton type="submit" loading={loading} disabled={TURNSTILE_SITE_KEY && !turnstileToken}>Criar conta</PrimaryButton>
        </form>
      )}

      <div style={{ marginTop: 16, fontSize: 12.5, color: COLORS.textMuted, textAlign: "center" }}>
        Já tem conta?{" "}
        <span className="lp-btn" onClick={onGoToLogin} style={{ color: COLORS.amber, textDecoration: "underline" }}>
          Entrar
        </span>
      </div>
    </AuthShell>
  );
}

// --- API client + peças do dashboard (mesmas da versão anterior) --------

function useApiClient(onUnauthorized) {
  return useCallback(
    async (path, options = {}) => {
      const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        credentials: "include",
        headers: {
          ...(options.headers || {}),
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      if (res.status === 401) {
        onUnauthorized();
        throw new Error("Sessão expirada, faça login novamente.");
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Erro ${res.status}`);
      }
      if (res.status === 204) return null;
      return res.json();
    },
    [onUnauthorized]
  );
}

function StatusBadge({ status }) {
  const map = {
    pending: { label: "Aguardando revisão", color: COLORS.amber },
    confirmed: { label: "Confirmado", color: COLORS.red },
    dismissed: { label: "Falso positivo", color: COLORS.textFaint },
  };
  const s = map[status] || map.pending;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", letterSpacing: "0.04em", textTransform: "uppercase", color: s.color }}>
      <Circle size={7} fill={s.color} stroke="none" />
      {s.label}
    </span>
  );
}

function Thumb({ status, thumbnailUrl }) {
  const isPending = status === "pending";
  return (
    <div
      style={{
        position: "relative",
        width: 108,
        height: 72,
        flexShrink: 0,
        borderRadius: 6,
        overflow: "hidden",
        background: thumbnailUrl ? `#000 url(${thumbnailUrl}) center/cover no-repeat` : "repeating-linear-gradient(0deg, #23262f 0px, #23262f 2px, #1b1e26 2px, #1b1e26 4px)",
        border: `1px solid ${COLORS.border}`,
      }}
    >
      {isPending && (
        <div style={{ position: "absolute", top: 5, left: 5, display: "flex", alignItems: "center", gap: 4 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: COLORS.red, boxShadow: `0 0 6px ${COLORS.red}` }} />
          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 9, color: "#fff" }}>REC</span>
        </div>
      )}
      {!thumbnailUrl && <Camera size={18} color="rgba(255,255,255,0.18)" style={{ position: "absolute", bottom: 6, right: 6 }} />}
    </div>
  );
}

// variant escolhe a cor semântica do card (âmbar = precisa de atenção,
// vermelho = confirmado, verde = ok) — "primary" é a única que ganha
// destaque visual maior (glow, valor maior), reservado pro que é mais
// acionável (Pendentes). bars é opcional: array de alturas 0-100 (últimos
// N dias), a última sempre em destaque (dia de hoje).
function Stat({ icon, label, value, foot, variant, bars }) {
  const isPrimary = variant === "primary";
  const valueColor =
    variant === "primary" ? COLORS.amber : variant === "danger" ? COLORS.red : variant === "ok" ? COLORS.teal : COLORS.text;
  const barColor =
    variant === "primary" ? COLORS.amber : variant === "danger" ? COLORS.red : variant === "ok" ? COLORS.teal : COLORS.textFaint;
  const barColorDim =
    variant === "primary" ? COLORS.amberDim : variant === "danger" ? COLORS.redDim : variant === "ok" ? COLORS.tealDim : COLORS.borderSoft;

  return (
    <div
      style={{
        position: "relative",
        overflow: "hidden",
        background: isPrimary ? `linear-gradient(135deg, rgba(245,166,35,0.09), ${COLORS.panel} 55%)` : COLORS.panel,
        border: `1px solid ${isPrimary ? COLORS.amberDim : COLORS.border}`,
        borderRadius: 10,
        padding: isPrimary ? "13px 16px" : "11px 14px",
      }}
    >
      {isPrimary && (
        <div
          aria-hidden="true"
          style={{
            position: "absolute", top: -32, right: -32, width: 96, height: 96, borderRadius: "50%",
            background: "radial-gradient(circle, rgba(245,166,35,0.16), transparent 70%)",
            pointerEvents: "none",
          }}
        />
      )}
      <div style={{ position: "relative", display: "flex", alignItems: "center", gap: 6, fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.08em", color: COLORS.textMuted, marginBottom: 6 }}>
        {icon}
        {label}
      </div>
      <div
        style={{
          position: "relative",
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: isPrimary ? 30 : variant === "ok" ? 20 : 24,
          fontWeight: 700,
          lineHeight: 1,
          color: valueColor,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {value}
      </div>
      {bars && bars.length > 0 && (
        <div style={{ position: "relative", display: "flex", alignItems: "flex-end", gap: 3, height: 16, marginTop: 8 }}>
          {bars.map((h, i) => (
            <i
              key={i}
              style={{
                flex: 1,
                borderRadius: "2px 2px 0 0",
                background: i === bars.length - 1 ? barColor : barColorDim,
                opacity: i === bars.length - 1 ? 1 : 0.55,
                height: `${Math.max(h, 2)}%`,
              }}
            />
          ))}
        </div>
      )}
      {foot && <div style={{ position: "relative", fontSize: 12, color: COLORS.textFaint, marginTop: 8 }}>{foot}</div>}
    </div>
  );
}

function AddStoreModal({ api, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [city, setCity] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null); // guarda a edge_api_key pra mostrar
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const store = await api("/v1/stores", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, city: city || null }),
      });
      setCreated(store);
      onCreated(store);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function copyKey() {
    navigator.clipboard?.writeText(created.edge_api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div
      onClick={onClose}
      className="lp-overlay-in"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.55)",
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="lp-modal-in"
        style={{
          width: 340,
          background: COLORS.panel,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 10,
          padding: 24,
          boxShadow: SHADOW,
        }}
      >
        {!created ? (
          <>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Adicionar loja</div>
            <form onSubmit={handleSubmit}>
              <Field label="Nome da loja" required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex: Loja Shopping Sul" />
              <Field label="Cidade" value={city} onChange={(e) => setCity(e.target.value)} placeholder="Ex: Curitiba, PR" />
              <ErrorNote message={error} />
              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <button
                  type="button"
                  className="lp-btn"
                  onClick={onClose}
                  style={{ flex: 1, padding: "9px 0", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: "transparent", color: COLORS.textMuted, fontSize: 13 }}
                >
                  Cancelar
                </button>
                <div style={{ flex: 1.4 }}>
                  <PrimaryButton type="submit" loading={loading}>Criar loja</PrimaryButton>
                </div>
              </div>
            </form>
          </>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <div style={{ width: 24, height: 24, borderRadius: "50%", background: "rgba(52,211,153,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Check size={13} color={COLORS.teal} />
              </div>
              <span style={{ fontWeight: 600, fontSize: 13.5 }}>{created.name} criada</span>
            </div>
            <p style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4, marginBottom: 14 }}>
              Use esta chave para conectar a box de detecção desta loja ao painel.
            </p>
            <div style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.textFaint, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 6 }}>
              Chave da loja (X-API-Key)
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, background: COLORS.panelAlt, border: `1px solid ${COLORS.border}`, borderRadius: 7, padding: "9px 10px", marginBottom: 18 }}>
              <code style={{ flex: 1, fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {created.edge_api_key}
              </code>
              <button className="lp-btn" onClick={copyKey} style={{ border: "none", background: "transparent", color: copied ? COLORS.teal : COLORS.textMuted, display: "flex" }}>
                {copied ? <Check size={14} /> : <Copy size={14} />}
              </button>
            </div>
            <PrimaryButton onClick={onClose}>Concluir</PrimaryButton>
          </>
        )}
      </div>
    </div>
  );
}

function InviteManagerModal({ api, stores, onClose, onInvited }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [storeIds, setStoreIds] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  function toggleStore(id) {
    setStoreIds((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (storeIds.length === 0) {
      setError("Selecione ao menos uma loja");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const invite = await api("/v1/team/invite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, store_ids: storeIds }),
      });
      setResult(invite);
      onInvited({ id: invite.id, name: invite.name, email: invite.email, role: "store_manager", store_ids: storeIds, status: "pending" });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div onClick={onClose} className="lp-overlay-in" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()} className="lp-modal-in" style={{ width: 360, background: COLORS.panel, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 24, boxShadow: SHADOW }}>
        {!result ? (
          <>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>Convidar gestor</div>
            <form onSubmit={handleSubmit}>
              <Field label="Nome" required autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex: João Pereira" />
              <Field label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />

              <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 6 }}>Lojas com acesso</div>
              <div style={{ marginBottom: 14, maxHeight: 140, overflowY: "auto" }} className="lp-scroll">
                {stores.length === 0 && (
                  <div style={{ fontSize: 12, color: COLORS.textFaint }}>Nenhuma loja cadastrada ainda.</div>
                )}
                {stores.map((store) => (
                  <label
                    key={store.id}
                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 4px", fontSize: 13, color: COLORS.text, cursor: "pointer" }}
                  >
                    <input
                      type="checkbox"
                      checked={storeIds.includes(store.id)}
                      onChange={() => toggleStore(store.id)}
                      style={{ accentColor: COLORS.amber }}
                    />
                    {store.name}
                  </label>
                ))}
              </div>

              <ErrorNote message={error} />
              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <button
                  type="button"
                  className="lp-btn"
                  onClick={onClose}
                  style={{ flex: 1, padding: "9px 0", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: "transparent", color: COLORS.textMuted, fontSize: 13 }}
                >
                  Cancelar
                </button>
                <div style={{ flex: 1.4 }}>
                  <PrimaryButton type="submit" loading={loading}>Enviar convite</PrimaryButton>
                </div>
              </div>
            </form>
          </>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <div style={{ width: 24, height: 24, borderRadius: "50%", background: "rgba(52,211,153,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <Mail size={13} color={COLORS.teal} />
              </div>
              <span style={{ fontWeight: 600, fontSize: 13.5 }}>Convite enviado</span>
            </div>
            <p style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 4, marginBottom: 18, lineHeight: 1.5 }}>
              Um email foi enviado para <strong style={{ color: COLORS.text }}>{result.email}</strong> com um link
              para {result.name} criar a própria senha e acessar o painel. O convite expira em 7 dias.
            </p>
            <PrimaryButton onClick={onClose}>Concluir</PrimaryButton>
          </>
        )}
      </div>
    </div>
  );
}

function TeamPanel({ api, stores }) {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showInvite, setShowInvite] = useState(false);

  const loadTeam = useCallback(() => {
    setLoading(true);
    api("/v1/team")
      .then((data) => {
        setMembers(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [api]);

  useEffect(() => {
    loadTeam();
  }, [loadTeam]);

  async function removeMember(id) {
    try {
      await api(`/v1/team/${id}`, { method: "DELETE" });
      setMembers((prev) => prev.filter((m) => m.id !== id));
    } catch (err) {
      setError(err.message);
    }
  }

  function storeNames(ids) {
    return ids
      .map((id) => stores.find((s) => s.id === id)?.name)
      .filter(Boolean)
      .join(", ") || "—";
  }

  return (
    <div style={{ flex: 1, padding: 22, overflowY: "auto" }} className="lp-scroll">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>Equipe</div>
          <div style={{ fontSize: 12.5, color: COLORS.textFaint, marginTop: 2 }}>
            Quem tem acesso ao painel e a quais lojas
          </div>
        </div>
        <button
          className="lp-btn"
          onClick={() => setShowInvite(true)}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", borderRadius: 8, border: "none", background: COLORS.amber, color: "#1a1200", fontSize: 13, fontWeight: 600 }}
        >
          <UserPlus size={14} />
          Convidar gestor
        </button>
      </div>

      {error && (
        <div style={{ marginBottom: 14, fontSize: 12.5, color: COLORS.red, display: "flex", alignItems: "center", gap: 6 }}>
          <AlertTriangle size={13} />
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ color: COLORS.textFaint, fontSize: 13 }}>Carregando equipe…</div>
      ) : (
        <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
          {members.map((member, i) => (
            <div
              key={member.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "12px 16px",
                borderTop: i === 0 ? "none" : `1px solid ${COLORS.borderSoft}`,
                background: COLORS.panel,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    background: COLORS.panelAlt,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 12,
                    fontWeight: 600,
                    color: COLORS.textMuted,
                    flexShrink: 0,
                  }}
                >
                  {member.name.slice(0, 1).toUpperCase()}
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{member.name}</div>
                  <div style={{ fontSize: 11.5, color: COLORS.textFaint }}>{member.email}</div>
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                {member.status === "pending" && (
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 5,
                      fontSize: 10.5,
                      fontFamily: "'IBM Plex Mono', monospace",
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      color: COLORS.amber,
                      background: "rgba(242,169,59,0.12)",
                      borderRadius: 5,
                      padding: "3px 7px",
                    }}
                  >
                    <Mail size={10} />
                    Convite pendente
                  </span>
                )}
                <div style={{ textAlign: "right" }}>
                  <div
                    style={{
                      fontSize: 10,
                      fontFamily: "'IBM Plex Mono', monospace",
                      letterSpacing: "0.05em",
                      textTransform: "uppercase",
                      color: member.role === "owner" ? COLORS.amber : COLORS.teal,
                    }}
                  >
                    {member.role === "owner" ? "Dono da conta" : "Gestor de loja"}
                  </div>
                  <div style={{ fontSize: 11.5, color: COLORS.textFaint, marginTop: 2, maxWidth: 220 }}>
                    {member.role === "owner" ? "Todas as lojas" : storeNames(member.store_ids)}
                  </div>
                </div>
                {member.role !== "owner" && (
                  <button
                    className="lp-btn"
                    onClick={() => removeMember(member.id)}
                    style={{ border: "none", background: "transparent", color: COLORS.textFaint, display: "flex" }}
                    title={member.status === "pending" ? "Cancelar convite" : "Remover acesso"}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showInvite && (
        <InviteManagerModal
          api={api}
          stores={stores}
          onClose={() => setShowInvite(false)}
          onInvited={(m) => setMembers((prev) => [...prev, m])}
        />
      )}
    </div>
  );
}

// Mesmo modelo de preço do backend (routers/billing.py) — só exibição,
// a fonte de verdade de quanto cobrar é sempre o servidor.
const CAMERAS_PER_PACKAGE = 9;
const PRICE_PER_PACKAGE = 649.9;

function BillingStatusBadge({ status }) {
  const map = {
    none: { label: "Sem plano", color: COLORS.textFaint },
    pending: { label: "Pagamento pendente", color: COLORS.amber },
    active: { label: "Ativa", color: COLORS.teal },
    overdue: { label: "Pagamento vencido", color: COLORS.red },
    canceled: { label: "Cancelada", color: COLORS.red },
  };
  const s = map[status] || map.none;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", letterSpacing: "0.04em", textTransform: "uppercase", color: s.color }}>
      <Circle size={7} fill={s.color} stroke="none" />
      {s.label}
    </span>
  );
}

function BillingPanel({ api }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showSubscribe, setShowSubscribe] = useState(false);

  const loadStatus = useCallback(() => {
    setLoading(true);
    api("/v1/billing/status")
      .then((data) => {
        setStatus(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [api]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const hasPlan = status && status.camera_limit > 0;
  const usagePct = hasPlan ? Math.min(100, Math.round((status.cameras_used / status.camera_limit) * 100)) : 0;
  const atLimit = hasPlan && status.cameras_used >= status.camera_limit;
  // Sem câmera liberada ainda (webhook não confirmou), mas já tem uma
  // assinatura em aberto — mostra "aguardando pagamento" em vez do
  // estado vazio genérico, senão parece que o pedido nem foi feito.
  const awaitingFirstPayment = status && !hasPlan && status.subscription_status === "pending";

  return (
    <div style={{ flex: 1, padding: 22, overflowY: "auto" }} className="lp-scroll">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18, flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontSize: 16, fontWeight: 600 }}>Plano</div>
          <div style={{ fontSize: 12.5, color: COLORS.textFaint, marginTop: 2 }}>
            Câmeras contratadas e cobrança via Pix
          </div>
        </div>
        <button
          className="lp-btn"
          onClick={() => setShowSubscribe(true)}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", borderRadius: 8, border: "none", background: COLORS.amber, color: "#1a1200", fontSize: 13, fontWeight: 600 }}
        >
          <Plus size={14} />
          Adicionar mais câmeras
        </button>
      </div>

      <ErrorNote message={error} />

      {loading ? (
        <div style={{ color: COLORS.textFaint, fontSize: 13 }}>Carregando plano…</div>
      ) : awaitingFirstPayment ? (
        <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28, textAlign: "center" }}>
          <QrCode size={22} color={COLORS.amber} style={{ marginBottom: 10 }} />
          <div style={{ fontSize: 13.5, color: COLORS.textMuted, marginBottom: 4 }}>Aguardando confirmação do pagamento</div>
          <div style={{ fontSize: 12, color: COLORS.textFaint, maxWidth: 320, margin: "0 auto", lineHeight: 1.5 }}>
            As câmeras ficam liberadas automaticamente assim que o Pix cair. Se perdeu o QR Code, clique em "Adicionar mais câmeras" pra gerar um novo.
          </div>
        </div>
      ) : !hasPlan ? (
        <div style={{ border: `1px dashed ${COLORS.border}`, borderRadius: 10, padding: 28, textAlign: "center" }}>
          <CreditCard size={22} color={COLORS.textFaint} style={{ marginBottom: 10 }} />
          <div style={{ fontSize: 13.5, color: COLORS.textMuted, marginBottom: 4 }}>Nenhuma câmera contratada ainda</div>
          <div style={{ fontSize: 12, color: COLORS.textFaint, maxWidth: 320, margin: "0 auto", lineHeight: 1.5 }}>
            Cada pacote libera {CAMERAS_PER_PACKAGE} câmeras por R$ {PRICE_PER_PACKAGE.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mês. Adicione câmeras pra começar a cadastrá-las.
          </div>
        </div>
      ) : (
        <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 18, background: COLORS.panel, maxWidth: 420 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, gap: 10 }}>
            <div style={{ fontSize: 13, fontWeight: 500 }}>
              {status.cameras_used} de {status.camera_limit} câmeras em uso
            </div>
            <BillingStatusBadge status={status.subscription_status} />
          </div>
          <div style={{ height: 8, borderRadius: 5, background: COLORS.panelAlt, border: `1px solid ${COLORS.borderSoft}`, overflow: "hidden", marginBottom: 8 }}>
            <div style={{ height: "100%", width: `${usagePct}%`, background: atLimit ? COLORS.red : COLORS.teal, borderRadius: 5, transition: "width .25s ease" }} />
          </div>
          <div style={{ fontSize: 11.5, color: COLORS.textFaint }}>
            {Math.floor(status.camera_limit / CAMERAS_PER_PACKAGE)} pacote(s) de {CAMERAS_PER_PACKAGE} câmeras — R$ {(Math.floor(status.camera_limit / CAMERAS_PER_PACKAGE) * PRICE_PER_PACKAGE).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mês
          </div>
          {atLimit && (
            <div style={{ marginTop: 12, fontSize: 12.5, color: COLORS.red, display: "flex", alignItems: "center", gap: 6 }}>
              <AlertTriangle size={13} />
              Limite de câmeras atingido — adicione mais câmeras pra cadastrar novas.
            </div>
          )}
        </div>
      )}

      {showSubscribe && (
        <SubscribeModal api={api} onClose={() => setShowSubscribe(false)} onSubscribed={loadStatus} />
      )}
    </div>
  );
}

function SubscribeModal({ api, onClose, onSubscribed }) {
  const [packages, setPackages] = useState(1);
  const [cpfCnpj, setCpfCnpj] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const data = await api("/v1/billing/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ camera_packages: packages, cpf_cnpj: cpfCnpj.replace(/\D/g, "") }),
      });
      setResult(data);
      onSubscribed();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function copyPix() {
    navigator.clipboard?.writeText(result.pix_copy_paste);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div onClick={onClose} className="lp-overlay-in" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", backdropFilter: "blur(2px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()} className="lp-modal-in" style={{ width: 360, background: COLORS.panel, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 24, boxShadow: SHADOW, maxHeight: "90vh", overflowY: "auto" }}>
        {!result ? (
          <>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Adicionar mais câmeras</div>
            <p style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 0, marginBottom: 16 }}>
              Cada pacote libera {CAMERAS_PER_PACKAGE} câmeras por R$ {PRICE_PER_PACKAGE.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mês.
            </p>
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, color: COLORS.textMuted, display: "block", marginBottom: 5 }}>
                  Pacotes ({CAMERAS_PER_PACKAGE} câmeras cada)
                </label>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <button
                    type="button"
                    className="lp-btn"
                    onClick={() => setPackages((p) => Math.max(1, p - 1))}
                    style={{ width: 32, height: 32, borderRadius: 7, border: `1px solid ${COLORS.border}`, background: COLORS.panelAlt, color: COLORS.text, fontSize: 16, lineHeight: 1 }}
                  >
                    −
                  </button>
                  <div style={{ flex: 1, textAlign: "center", fontFamily: "'IBM Plex Mono', monospace", fontSize: 15 }}>{packages}</div>
                  <button
                    type="button"
                    className="lp-btn"
                    onClick={() => setPackages((p) => p + 1)}
                    style={{ width: 32, height: 32, borderRadius: 7, border: `1px solid ${COLORS.border}`, background: COLORS.panelAlt, color: COLORS.text, fontSize: 16, lineHeight: 1 }}
                  >
                    +
                  </button>
                </div>
              </div>

              <Field label="CPF ou CNPJ do responsável" required value={cpfCnpj} onChange={(e) => setCpfCnpj(e.target.value)} placeholder="Só números" />

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px", background: COLORS.panelAlt, borderRadius: 7, marginBottom: 14, fontSize: 13 }}>
                <span style={{ color: COLORS.textMuted }}>{packages * CAMERAS_PER_PACKAGE} câmeras</span>
                <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontWeight: 600 }}>R$ {(packages * PRICE_PER_PACKAGE).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mês</span>
              </div>

              <ErrorNote message={error} />
              <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <button
                  type="button"
                  className="lp-btn"
                  onClick={onClose}
                  style={{ flex: 1, padding: "9px 0", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: "transparent", color: COLORS.textMuted, fontSize: 13 }}
                >
                  Cancelar
                </button>
                <div style={{ flex: 1.4 }}>
                  <PrimaryButton type="submit" loading={loading}>Gerar cobrança Pix</PrimaryButton>
                </div>
              </div>
            </form>
          </>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <div style={{ width: 24, height: 24, borderRadius: "50%", background: "rgba(52,211,153,0.15)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                <QrCode size={13} color={COLORS.teal} />
              </div>
              <span style={{ fontWeight: 600, fontSize: 13.5 }}>Pague pra ativar</span>
            </div>

            {result.pix_qr_code_image ? (
              <>
                <p style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4, marginBottom: 14 }}>
                  Escaneie o QR Code no app do seu banco, ou copie o código Pix abaixo.
                </p>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 14 }}>
                  <img
                    src={`data:image/png;base64,${result.pix_qr_code_image}`}
                    alt="QR Code Pix"
                    style={{ width: 180, height: 180, borderRadius: 8, background: "#fff", padding: 8 }}
                  />
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, background: COLORS.panelAlt, border: `1px solid ${COLORS.border}`, borderRadius: 7, padding: "9px 10px", marginBottom: 14 }}>
                  <code style={{ flex: 1, fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {result.pix_copy_paste}
                  </code>
                  <button className="lp-btn" onClick={copyPix} style={{ border: "none", background: "transparent", color: copied ? COLORS.teal : COLORS.textMuted, display: "flex" }}>
                    {copied ? <Check size={14} /> : <Copy size={14} />}
                  </button>
                </div>
              </>
            ) : (
              <p style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 4, marginBottom: 14, lineHeight: 1.5 }}>
                Assinatura criada — o QR Code ainda está sendo gerado. Feche esta janela e volte na tela de Plano em alguns instantes pra ver o código de pagamento.
              </p>
            )}

            <p style={{ fontSize: 11.5, color: COLORS.textFaint, marginBottom: 18, lineHeight: 1.5 }}>
              As {result.camera_limit_pending} câmeras ficam liberadas automaticamente assim que o pagamento for confirmado.
            </p>

            <PrimaryButton onClick={onClose}>Concluir</PrimaryButton>
          </>
        )}
      </div>
    </div>
  );
}

// Bipe de dois tons pra novo alerta pendente — gerado na hora via Web Audio,
// sem depender de um arquivo de áudio.
function playAlertSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const now = ctx.currentTime;
    [880, 660].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      const start = now + i * 0.18;
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(0.3, start + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(start);
      osc.stop(start + 0.2);
    });
  } catch (e) {
    // Web Audio bloqueado ou indisponível — segue sem som, não quebra o painel.
  }
}

async function downloadClip(url, filename) {
  try {
    // Baixa como blob em vez de usar só <a download> direto na URL —
    // o clipe vem de outro domínio (R2), e o atributo download do link
    // é ignorado pelo navegador pra recursos de origem diferente.
    const res = await fetch(url);
    const blob = await res.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(blobUrl);
  } catch (e) {
    window.open(url, "_blank");
  }
}

const ALERTS_POLL_INTERVAL_MS = 15000;

const MOBILE_BREAKPOINT_PX = 860;

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(
    () => window.innerWidth <= MOBILE_BREAKPOINT_PX
  );
  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= MOBILE_BREAKPOINT_PX);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return isMobile;
}

// --- STATUS (onboarding + conexão das câmeras) --------------------------

const ONBOARDING_STATUS_MAP = {
  pending: { label: "Pendente", color: COLORS.amber },
  in_progress: { label: "Em configuração", color: COLORS.teal },
  completed: { label: "Concluído", color: COLORS.teal },
};

function timeAgo(isoString) {
  if (!isoString) return "nunca conectou";
  const minutes = Math.floor((Date.now() - new Date(isoString).getTime()) / 60000);
  if (minutes < 1) return "agora mesmo";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours}h`;
  return `há ${Math.floor(hours / 24)}d`;
}

// Janelas de dia (meia-noite a meia-noite, fuso local) dos últimos `days`
// dias, do mais antigo pro mais recente (hoje é sempre o último).
function recentDayWindows(days) {
  return Array.from({ length: days }, (_, i) => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    start.setDate(start.getDate() - (days - 1 - i));
    const end = new Date(start);
    end.setDate(end.getDate() + 1);
    return [start, end];
  });
}

// Mini-gráfico de tendência dos cards de estatística (últimos `days`
// dias). Conta alertas por dia de CRIAÇÃO com o status atual passado em
// `status` — leitura aproximada (não é "quando o status mudou", é
// "quando o alerta nasceu"), mas é o que dá pra calcular sem endpoint
// novo, e é suficiente pra uma tendência decorativa. Alturas normalizadas
// 0-100 pelo maior dia do período (dia mais recente sempre em destaque
// visual, ver Stat).
function dailyTrendBars(alerts, status, days = 10) {
  const counts = recentDayWindows(days).map(([start, end]) =>
    alerts.filter((a) => a.status === status && new Date(a.created_at) >= start && new Date(a.created_at) < end).length
  );
  const max = Math.max(...counts, 1);
  return counts.map((c) => Math.round((c / max) * 100));
}

// Igual acima, mas pro card de Falso positivo — o valor do card já é uma
// porcentagem (dismissed / total do período inteiro), então a barra
// também é uma porcentagem (dismissed / total DAQUELE dia), não uma
// contagem normalizada.
function falsePositiveTrendBars(alerts, days = 10) {
  return recentDayWindows(days).map(([start, end]) => {
    const dayAlerts = alerts.filter((a) => new Date(a.created_at) >= start && new Date(a.created_at) < end);
    if (dayAlerts.length === 0) return 0;
    const dismissed = dayAlerts.filter((a) => a.status === "dismissed").length;
    return Math.round((dismissed / dayAlerts.length) * 100);
  });
}

function StatusPanel({ stores }) {
  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 22 }}>
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Status das lojas</div>
      <p style={{ fontSize: 12.5, color: COLORS.textMuted, marginBottom: 20 }}>
        Acompanhe a conexão das câmeras e o andamento da configuração de cada loja.
      </p>

      {stores.length === 0 ? (
        <div style={{ color: COLORS.textFaint, fontSize: 13 }}>Nenhuma loja cadastrada ainda.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {stores.map((store) => {
            const statusMeta = ONBOARDING_STATUS_MAP[store.onboarding_status] || ONBOARDING_STATUS_MAP.pending;
            return (
              <div
                key={store.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: 10,
                  padding: "14px 16px",
                  background: COLORS.panel,
                  border: `1px solid ${COLORS.border}`,
                  borderRadius: 10,
                }}
              >
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 600 }}>{store.name}</div>
                  <div style={{ fontSize: 11.5, color: COLORS.textFaint, marginTop: 3 }}>
                    {store.online ? "Conectado" : "Sem conexão"} — {timeAgo(store.last_seen_at)}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: store.online ? COLORS.teal : COLORS.textFaint }}>
                    {store.online ? <Wifi size={14} /> : <WifiOff size={14} />}
                    {store.online ? "Online" : "Offline"}
                  </span>
                  <span
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      padding: "4px 10px",
                      borderRadius: 20,
                      border: `1px solid ${statusMeta.color}`,
                      color: statusMeta.color,
                    }}
                  >
                    {statusMeta.label}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CamerasPanel({ api, stores }) {
  const [selectedStoreId, setSelectedStoreId] = useState(stores[0]?.id || null);
  const [cameras, setCameras] = useState([]);
  const [neighbors, setNeighbors] = useState([]);
  const [suppressedEvents, setSuppressedEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newLabel, setNewLabel] = useState("");
  const [adding, setAdding] = useState(false);
  const [copiedId, setCopiedId] = useState(null);

  useEffect(() => {
    if (!selectedStoreId && stores.length > 0) setSelectedStoreId(stores[0].id);
  }, [stores, selectedStoreId]);

  const loadData = useCallback(() => {
    if (!selectedStoreId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      api(`/v1/stores/${selectedStoreId}/cameras`),
      api(`/v1/stores/${selectedStoreId}/cameras/neighbors`),
      api(`/v1/stores/${selectedStoreId}/suppressed-events`),
    ])
      .then(([camerasData, neighborsData, suppressedData]) => {
        setCameras(camerasData);
        setNeighbors(neighborsData);
        setSuppressedEvents(suppressedData);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [api, selectedStoreId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  async function addCamera(e) {
    e.preventDefault();
    if (!newLabel.trim()) return;
    setAdding(true);
    setError(null);
    try {
      const camera = await api(`/v1/stores/${selectedStoreId}/cameras`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: newLabel.trim() }),
      });
      setCameras((prev) => [...prev, camera]);
      setNewLabel("");
    } catch (err) {
      setError(err.message);
    } finally {
      setAdding(false);
    }
  }

  async function removeCamera(id) {
    try {
      await api(`/v1/stores/${selectedStoreId}/cameras/${id}`, { method: "DELETE" });
      setCameras((prev) => prev.filter((c) => c.id !== id));
      setNeighbors((prev) => prev.filter((n) => n.camera_id_a !== id && n.camera_id_b !== id));
    } catch (err) {
      setError(err.message);
    }
  }

  function copyId(id) {
    navigator.clipboard?.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 1500);
  }

  function findNeighborPair(idA, idB) {
    return neighbors.find(
      (n) => (n.camera_id_a === idA && n.camera_id_b === idB) || (n.camera_id_a === idB && n.camera_id_b === idA)
    );
  }

  async function toggleNeighbor(idA, idB) {
    const existing = findNeighborPair(idA, idB);
    try {
      if (existing) {
        await api(`/v1/stores/${selectedStoreId}/cameras/neighbors/${existing.id}`, { method: "DELETE" });
        setNeighbors((prev) => prev.filter((n) => n.id !== existing.id));
      } else {
        const created = await api(`/v1/stores/${selectedStoreId}/cameras/neighbors`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ camera_id_a: idA, camera_id_b: idB }),
        });
        setNeighbors((prev) => [...prev, created]);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  if (stores.length === 0) {
    return (
      <div style={{ flex: 1, overflowY: "auto", padding: 22 }}>
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Câmeras</div>
        <div style={{ color: COLORS.textFaint, fontSize: 13 }}>Nenhuma loja cadastrada ainda.</div>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: 22 }} className="lp-scroll">
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Câmeras</div>
      <p style={{ fontSize: 12.5, color: COLORS.textMuted, marginBottom: 16, maxWidth: 560 }}>
        Cadastre as câmeras de cada loja e use o ID pra configurar a box de detecção (variável CAMERA_ID).
        Marque quais câmeras cobrem áreas vizinhas — isso alimenta a correlação de eventos entre câmeras.
      </p>

      {stores.length > 1 && (
        <select
          value={selectedStoreId || ""}
          onChange={(e) => setSelectedStoreId(e.target.value)}
          style={{ ...inputStyle, width: "auto", marginBottom: 18 }}
        >
          {stores.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
      )}

      <ErrorNote message={error} />

      {loading ? (
        <div style={{ color: COLORS.textFaint, fontSize: 13 }}>Carregando câmeras…</div>
      ) : (
        <>
          <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden", marginBottom: 20 }}>
            {cameras.length === 0 && (
              <div style={{ padding: "14px 16px", fontSize: 12.5, color: COLORS.textFaint }}>
                Nenhuma câmera cadastrada nesta loja ainda.
              </div>
            )}
            {cameras.map((camera, i) => (
              <div
                key={camera.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 10,
                  padding: "12px 16px",
                  borderTop: i === 0 ? "none" : `1px solid ${COLORS.borderSoft}`,
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                  <Camera size={15} color={COLORS.textFaint} />
                  <span style={{ fontSize: 13, fontWeight: 500 }}>{camera.label}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <code style={{ fontSize: 10.5, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.textFaint, background: COLORS.panelAlt, borderRadius: 5, padding: "3px 7px" }}>
                    {camera.id.slice(0, 8)}…
                  </code>
                  <button
                    className="lp-btn"
                    onClick={() => copyId(camera.id)}
                    title="Copiar ID completo (usar como CAMERA_ID na box)"
                    style={{ border: "none", background: "transparent", color: copiedId === camera.id ? COLORS.teal : COLORS.textFaint, display: "flex" }}
                  >
                    {copiedId === camera.id ? <Check size={13} /> : <Copy size={13} />}
                  </button>
                  <button
                    className="lp-btn"
                    onClick={() => removeCamera(camera.id)}
                    title="Remover câmera"
                    style={{ border: "none", background: "transparent", color: COLORS.textFaint, display: "flex" }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>

          <form onSubmit={addCamera} style={{ display: "flex", gap: 8, marginBottom: 28 }}>
            <input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="Ex: Câmera 03 — Corredor 2"
              style={{ ...inputStyle, flex: 1 }}
            />
            <button
              type="submit"
              disabled={adding}
              className="lp-btn"
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "0 14px", borderRadius: 8, border: "none", background: COLORS.amber, color: "#1a1200", fontSize: 13, fontWeight: 600 }}
            >
              {adding ? <Loader2 size={14} className="lp-spin" /> : <Plus size={14} />}
              Adicionar câmera
            </button>
          </form>

          {cameras.length >= 2 && (
            <>
              <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 4, display: "flex", alignItems: "center", gap: 6 }}>
                <Link2 size={14} color={COLORS.textFaint} />
                Câmeras vizinhas
              </div>
              <p style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 14, maxWidth: 560 }}>
                Marque pares de câmeras que cobrem áreas fisicamente próximas na loja (ex: duas câmeras que enxergam o mesmo corredor por ângulos diferentes).
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {cameras.map((camera) => {
                  const others = cameras.filter((c) => c.id !== camera.id);
                  if (others.length === 0) return null;
                  return (
                    <div key={camera.id} style={{ padding: "10px 14px", background: COLORS.panel, border: `1px solid ${COLORS.border}`, borderRadius: 9 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 8 }}>{camera.label}</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                        {others.map((other) => (
                          <label key={other.id} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: COLORS.textMuted, cursor: "pointer" }}>
                            <input
                              type="checkbox"
                              checked={!!findNeighborPair(camera.id, other.id)}
                              onChange={() => toggleNeighbor(camera.id, other.id)}
                              style={{ accentColor: COLORS.amber }}
                            />
                            {other.label}
                          </label>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {suppressedEvents.length > 0 && (
            <>
              <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 4, marginTop: 28, display: "flex", alignItems: "center", gap: 6 }}>
                <EyeOff size={14} color={COLORS.textFaint} />
                Alertas suprimidos por correlação
              </div>
              <p style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 14, maxWidth: 560 }}>
                Eventos que uma câmera não reenviou por considerar continuação de um alerta recente numa câmera vizinha. Revise de vez em quando — se duas pessoas diferentes estiverem sendo tratadas como uma só, desmarque a vizinhança entre essas câmeras.
              </p>
              <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
                {suppressedEvents.map((ev, i) => (
                  <div
                    key={ev.id}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                      gap: 8,
                      padding: "10px 16px",
                      borderTop: i === 0 ? "none" : `1px solid ${COLORS.borderSoft}`,
                    }}
                  >
                    <div style={{ fontSize: 12.5 }}>
                      <strong>{ev.camera_label}</strong> não reenviou (confiança {(ev.confidence * 100).toFixed(0)}%) — tratado como continuação de <strong>{ev.matched_camera_label}</strong>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 11, color: COLORS.textFaint, fontFamily: "'IBM Plex Mono', monospace" }}>
                      <span>distância {ev.appearance_distance.toFixed(2)}</span>
                      <span>{timeAgo(ev.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function Dashboard({ onLogout, accessPaused }) {
  const api = useApiClient(onLogout);

  const [stores, setStores] = useState([]);
  const [selectedStore, setSelectedStore] = useState("all");
  const [alerts, setAlerts] = useState([]);
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [loadingStores, setLoadingStores] = useState(true);
  const [loadingAlerts, setLoadingAlerts] = useState(false);
  const [error, setError] = useState(null);
  const [showAddStore, setShowAddStore] = useState(false);
  const [activeView, setActiveView] = useState("alerts"); // "alerts" | "team" | "billing" | "status" | "cameras"
  const [soundEnabled, setSoundEnabled] = useState(() => localStorage.getItem("vigia_sound_enabled") !== "false");
  const [showMobileNav, setShowMobileNav] = useState(false);
  const [mobileShowDetail, setMobileShowDetail] = useState(false);
  const isMobile = useIsMobile();
  const knownAlertIdsRef = useRef(null); // null = ainda não fez a primeira carga

  useEffect(() => {
    localStorage.setItem("vigia_sound_enabled", soundEnabled ? "true" : "false");
  }, [soundEnabled]);

  useEffect(() => {
    api("/v1/stores")
      .then((data) => {
        setStores(data);
        setLoadingStores(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoadingStores(false);
      });
  }, [api]);

  const loadAlerts = useCallback(async () => {
    if (stores.length === 0) return;
    setLoadingAlerts(true);
    setError(null);
    try {
      const targetStores = selectedStore === "all" ? stores.map((s) => s.id) : [selectedStore];
      const results = await Promise.all(targetStores.map((id) => api(`/v1/stores/${id}/alerts`)));
      const merged = results.flat().sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

      if (knownAlertIdsRef.current) {
        const hasNewPending = merged.some(
          (a) => a.status === "pending" && !knownAlertIdsRef.current.has(a.id)
        );
        if (hasNewPending && soundEnabled) playAlertSound();
      }
      knownAlertIdsRef.current = new Set(merged.map((a) => a.id));

      setAlerts(merged);
      if (merged.length > 0) setSelectedAlertId((prev) => prev ?? merged[0].id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingAlerts(false);
    }
  }, [api, stores, selectedStore, soundEnabled]);

  useEffect(() => {
    // Troca de loja não deve soar como "alerta novo" — reseta a base de
    // comparação antes da próxima carga.
    knownAlertIdsRef.current = null;
  }, [selectedStore]);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  useEffect(() => {
    const interval = setInterval(loadAlerts, ALERTS_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [loadAlerts]);

  async function reviewAlert(id, status) {
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, status } : a)));
    try {
      await api(`/v1/alerts/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
    } catch (err) {
      setError(err.message);
      loadAlerts();
    }
  }

  const selectedAlert = alerts.find((a) => a.id === selectedAlertId) || alerts[0];
  const pendingCount = alerts.filter((a) => a.status === "pending").length;
  const confirmedCount = alerts.filter((a) => a.status === "confirmed").length;
  const falsePositiveRate = alerts.length ? Math.round((alerts.filter((a) => a.status === "dismissed").length / alerts.length) * 100) : 0;
  const pendingBars = dailyTrendBars(alerts, "pending");
  const confirmedBars = dailyTrendBars(alerts, "confirmed");
  const falsePositiveBars = falsePositiveTrendBars(alerts);
  const storeName = selectedStore === "all" ? "Todas as lojas" : stores.find((s) => s.id === selectedStore)?.name;

  const showEmptyState = !loadingStores && stores.length === 0;

  // Atualização mais recente entre todas as lojas — usado no bloco
  // "Frota" da sidebar, representa o pulso mais atual da frota como um todo.
  const latestSeenAt = stores.reduce((latest, s) => {
    if (!s.last_seen_at) return latest;
    if (!latest || new Date(s.last_seen_at) > new Date(latest)) return s.last_seen_at;
    return latest;
  }, null);
  const onlineStoreCount = stores.filter((s) => s.online).length;

  return (
    <div
      style={{
        fontFamily: "'Manrope', sans-serif",
        background: COLORS.bg,
        // Grade sutil lembrando tela de monitor — só nesse wrapper (área
        // logada); a tela de login (AuthShell) não usa isso.
        backgroundImage:
          "linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px)",
        backgroundSize: "28px 28px",
        color: COLORS.text,
        minHeight: "100dvh",
        display: "flex",
        overflow: "hidden",
      }}
    >
      <style>{globalFonts}</style>

      {isMobile && showMobileNav && (
        <div
          className="lp-overlay-in"
          onClick={() => setShowMobileNav(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 40 }}
        />
      )}

      <div
        style={
          isMobile
            ? { width: 232, flexShrink: 0, background: COLORS.panel, borderRight: `1px solid ${COLORS.border}`, padding: "20px 14px", display: "flex", flexDirection: "column", boxShadow: SHADOW_SOFT, zIndex: 50, position: "fixed", top: 0, bottom: 0, left: 0, transform: showMobileNav ? "translateX(0)" : "translateX(-100%)", transition: "transform 0.2s ease" }
            : { width: 208, flexShrink: 0, background: COLORS.panel, borderRight: `1px solid ${COLORS.border}`, padding: "20px 14px", display: "flex", flexDirection: "column", boxShadow: SHADOW_SOFT, zIndex: 1 }
        }
      >
        <div style={{ padding: "0 6px", marginBottom: 28, display: "flex", justifyContent: "center" }}>
          <Logo size={38} fontSize={27} />
        </div>

        {stores.length > 0 && (
          <div style={{ background: COLORS.panelAlt, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "12px 14px", marginBottom: 26 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
              <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.09em", color: COLORS.textMuted }}>Frota</span>
              <span style={{ fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.textFaint }}>{timeAgo(latestSeenAt)}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {stores.map((store) => {
                const pendingForStore = alerts.filter((a) => a.store_id === store.id && a.status === "pending").length;
                const dotColor = pendingForStore > 0 ? COLORS.amber : store.online ? COLORS.teal : COLORS.textFaint;
                const statusText = pendingForStore > 0
                  ? `${pendingForStore} pendente${pendingForStore > 1 ? "s" : ""}`
                  : store.online ? "ok" : "offline";
                return (
                  <div key={store.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: COLORS.textMuted, minWidth: 0 }}>
                    <span
                      style={{
                        width: 6, height: 6, borderRadius: "50%", flexShrink: 0, background: dotColor,
                        boxShadow: pendingForStore > 0 || store.online ? `0 0 6px 0 ${dotColor}99` : "none",
                      }}
                    />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{store.name}</span>
                    <span style={{ marginLeft: "auto", flexShrink: 0, color: COLORS.text, fontWeight: 600 }}>{statusText}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.textFaint, letterSpacing: "0.08em", textTransform: "uppercase", padding: "0 6px", marginBottom: 8 }}>
          Lojas
        </div>

        <button className="lp-btn lp-nav" onClick={() => { setSelectedStore("all"); setActiveView("alerts"); setShowMobileNav(false); setMobileShowDetail(false); }} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: selectedStore === "all" && activeView === "alerts" ? COLORS.panelAlt : "transparent", color: selectedStore === "all" && activeView === "alerts" ? COLORS.text : COLORS.textMuted, fontSize: 13, textAlign: "left", marginBottom: 2 }}>
          <Building2 size={14} />
          Todas as lojas
        </button>

        {loadingStores && (
          <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: COLORS.textFaint, padding: "8px" }}>
            <Loader2 size={13} className="lp-spin" />
            Carregando lojas…
          </div>
        )}

        {stores.map((store) => {
          const count = alerts.filter((a) => a.store_id === store.id && a.status === "pending").length;
          const active = selectedStore === store.id;
          return (
            <button key={store.id} className="lp-btn lp-nav" onClick={() => { setSelectedStore(store.id); setActiveView("alerts"); setShowMobileNav(false); setMobileShowDetail(false); }} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: active && activeView === "alerts" ? COLORS.panelAlt : "transparent", color: active && activeView === "alerts" ? COLORS.text : COLORS.textMuted, fontSize: 13, textAlign: "left", marginBottom: 2 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Store size={14} />
                {store.name}
              </span>
              {count > 0 && (
                <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 10, background: COLORS.amber, color: "#1a1200", borderRadius: 10, padding: "1px 6px", fontWeight: 600 }}>
                  {count}
                </span>
              )}
            </button>
          );
        })}

        <button
          className="lp-btn"
          onClick={() => { setShowAddStore(true); setShowMobileNav(false); }}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: `1px dashed ${COLORS.border}`, background: "transparent", color: COLORS.textFaint, fontSize: 12.5, textAlign: "left", marginTop: 6 }}
        >
          <Plus size={13} />
          Adicionar loja
        </button>

        <button
          className="lp-btn lp-nav"
          onClick={() => { setActiveView("team"); setShowMobileNav(false); }}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: activeView === "team" ? COLORS.panelAlt : "transparent", color: activeView === "team" ? COLORS.text : COLORS.textFaint, fontSize: 12.5, textAlign: "left", marginTop: 12 }}
        >
          <Users size={13} />
          Equipe
        </button>

        <button
          className="lp-btn lp-nav"
          onClick={() => { setActiveView("billing"); setShowMobileNav(false); }}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: activeView === "billing" ? COLORS.panelAlt : "transparent", color: activeView === "billing" ? COLORS.text : COLORS.textFaint, fontSize: 12.5, textAlign: "left", marginTop: 2 }}
        >
          <CreditCard size={13} />
          Plano
        </button>

        <button
          className="lp-btn lp-nav"
          onClick={() => { setActiveView("status"); setShowMobileNav(false); }}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: activeView === "status" ? COLORS.panelAlt : "transparent", color: activeView === "status" ? COLORS.text : COLORS.textFaint, fontSize: 12.5, textAlign: "left", marginTop: 2 }}
        >
          <Wifi size={13} />
          Status
        </button>

        <button
          className="lp-btn lp-nav"
          onClick={() => { setActiveView("cameras"); setShowMobileNav(false); }}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: activeView === "cameras" ? COLORS.panelAlt : "transparent", color: activeView === "cameras" ? COLORS.text : COLORS.textFaint, fontSize: 12.5, textAlign: "left", marginTop: 2 }}
        >
          <Camera size={13} />
          Câmeras
        </button>

        <button
          className="lp-btn"
          onClick={() => setSoundEnabled((prev) => !prev)}
          style={{ marginTop: "auto", display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: "transparent", color: COLORS.textFaint, fontSize: 12.5, textAlign: "left" }}
        >
          {soundEnabled ? <Bell size={13} /> : <BellOff size={13} />}
          {soundEnabled ? "Som de alerta ligado" : "Som de alerta desligado"}
        </button>

        <button className="lp-btn" onClick={onLogout} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: "transparent", color: COLORS.textFaint, fontSize: 12.5, textAlign: "left" }}>
          <LogOut size={13} />
          Sair
        </button>
      </div>

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, width: isMobile ? "100%" : "auto" }}>
        {accessPaused && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 22px", background: COLORS.amberDim, borderBottom: `1px solid ${COLORS.amber}`, color: COLORS.amber, fontSize: 12.5 }}>
            <AlertTriangle size={14} />
            Serviço de detecção pausado — as câmeras não estão gerando novos alertas. Entre em contato com o suporte pra reativar.
          </div>
        )}

        {isMobile && (
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", borderBottom: `1px solid ${COLORS.border}`, background: COLORS.panel }}>
            <button
              onClick={() => setShowMobileNav(true)}
              aria-label="Abrir menu"
              style={{ background: "transparent", border: "none", color: COLORS.text, padding: 4, display: "flex", cursor: "pointer" }}
            >
              <Menu size={20} />
            </button>
            <Logo size={24} fontSize={18} />
          </div>
        )}

        {activeView === "alerts" && (
          <>
            <div style={{ padding: isMobile ? "14px 16px 0" : "20px 22px 0" }}>
              <div style={{ marginBottom: 18 }}>
                <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.01em", marginBottom: 4 }}>{storeName}</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 13, color: COLORS.textMuted }}>
                  <span
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: COLORS.teal,
                      background: "rgba(61,214,140,0.08)", border: `1px solid ${COLORS.tealDim}`, padding: "3px 9px", borderRadius: 999,
                    }}
                  >
                    <span className="lp-blip" style={{ width: 6, height: 6, borderRadius: "50%", background: COLORS.teal, display: "inline-block" }} />
                    monitorando ao vivo
                  </span>
                  <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>
                    · {loadingAlerts ? "Atualizando…" : `${alerts.length} evento(s)`} · {onlineStoreCount} loja{onlineStoreCount === 1 ? "" : "s"} online
                  </span>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1.4fr 1fr 1fr", gap: 14, marginBottom: 22 }}>
                <Stat icon={<Bell size={14} color={COLORS.amber} />} label="Pendentes" value={pendingCount} variant="primary" bars={pendingBars} foot="aguardando sua confirmação" />
                <Stat icon={<ShieldAlert size={14} color={COLORS.red} />} label="Confirmados" value={confirmedCount} variant="danger" bars={confirmedBars} foot="no total" />
                {!isMobile && (
                  <Stat icon={<TrendingDown size={14} color={COLORS.teal} />} label="Taxa de falso positivo" value={`${falsePositiveRate}%`} variant="ok" bars={falsePositiveBars} foot="no total" />
                )}
              </div>
            </div>

            {error && (
              <div style={{ padding: "10px 22px", background: "rgba(232,72,60,0.1)", color: COLORS.red, fontSize: 12.5, display: "flex", alignItems: "center", gap: 8 }}>
                <AlertTriangle size={14} />
                {error}
              </div>
            )}
          </>
        )}

        {activeView === "team" ? (
          <TeamPanel api={api} stores={stores} />
        ) : activeView === "billing" ? (
          <BillingPanel api={api} />
        ) : activeView === "status" ? (
          <StatusPanel stores={stores} />
        ) : activeView === "cameras" ? (
          <CamerasPanel api={api} stores={stores} />
        ) : showEmptyState ? (
          <div className="lp-fade-up" style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, color: COLORS.textFaint }}>
            <Building2 size={28} color={COLORS.textFaint} style={{ opacity: 0.6 }} />
            <div style={{ fontSize: 13.5, color: COLORS.textMuted }}>Nenhuma loja cadastrada ainda</div>
            <div style={{ fontSize: 12, maxWidth: 240, textAlign: "center", lineHeight: 1.5 }}>Adicione sua primeira loja pra começar a receber alertas.</div>
          </div>
        ) : (
          <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
            <div
              className="lp-scroll"
              style={
                isMobile
                  ? { width: "100%", display: mobileShowDetail ? "none" : "block", overflowY: "auto", padding: "10px 0" }
                  : { width: 340, flexShrink: 0, borderRight: `1px solid ${COLORS.border}`, overflowY: "auto", padding: "10px 0" }
              }
            >
              {!loadingAlerts && alerts.length === 0 && (
                <div className="lp-fade-up" style={{ padding: "40px 24px", display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
                  <div
                    style={{
                      width: 168, height: 168, borderRadius: "50%", position: "relative", overflow: "hidden",
                      background:
                        "repeating-radial-gradient(circle, transparent 0, transparent 26px, rgba(61,214,140,0.09) 27px), radial-gradient(circle, rgba(61,214,140,0.06), transparent 70%)",
                      border: `1px solid ${COLORS.tealDim}`,
                      marginBottom: 18,
                    }}
                  >
                    <div
                      aria-hidden="true"
                      className="lp-sweep"
                      style={{ position: "absolute", inset: 0, background: "conic-gradient(from 0deg, rgba(61,214,140,0.55), transparent 45deg)" }}
                    />
                  </div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: COLORS.text, marginBottom: 6 }}>Tudo tranquilo</div>
                  <p style={{ fontSize: 13, color: COLORS.textMuted, margin: "0 0 14px", maxWidth: 220, lineHeight: 1.5 }}>
                    Nenhum alerta por aqui. Suas câmeras seguem ativas e observando.
                  </p>
                  {/* Decorativo — não é uma métrica real (não há dado de atividade
                      por hora exposto pela API hoje), só reforça a sensação de
                      "sistema vivo" enquanto não há eventos pra mostrar. */}
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 28, marginBottom: 6 }}>
                    {[6, 10, 4, 14, 8, 5, 9, 3, 11, 6, 4, 7].map((h, i) => (
                      <i key={i} style={{ width: 4, background: COLORS.tealDim, borderRadius: "2px 2px 0 0", height: h }} />
                    ))}
                  </div>
                  <span style={{ fontSize: 11, color: COLORS.textFaint }}>sinal de monitoramento</span>
                </div>
              )}
              {alerts.map((alert) => {
                const store = stores.find((s) => s.id === alert.store_id);
                const active = selectedAlertId === alert.id;
                return (
                  <div key={alert.id} className="lp-row" onClick={() => { setSelectedAlertId(alert.id); if (isMobile) setMobileShowDetail(true); }} style={{ display: "flex", gap: 10, padding: "10px 16px", cursor: "pointer", background: active ? COLORS.panelAlt : "transparent", borderLeft: active ? `2px solid ${COLORS.amber}` : "2px solid transparent" }}>
                    <Thumb status={alert.status} thumbnailUrl={alert.thumbnail_url} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{alert.camera_label}</div>
                      <div style={{ fontSize: 11, color: COLORS.textFaint, marginTop: 2 }}>
                        {selectedStore === "all" && store ? `${store.name} · ` : ""}
                        {new Date(alert.created_at).toLocaleString("pt-BR")}
                      </div>
                      <div style={{ marginTop: 6 }}>
                        <StatusBadge status={alert.status} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div
              style={
                isMobile
                  ? { width: "100%", display: mobileShowDetail ? "block" : "none", padding: 16, overflowY: "auto" }
                  : { flex: 1, padding: 22, overflowY: "auto" }
              }
              className="lp-scroll"
            >
              {isMobile && selectedAlert && (
                <button
                  onClick={() => setMobileShowDetail(false)}
                  style={{ display: "flex", alignItems: "center", gap: 6, background: "transparent", border: "none", color: COLORS.textMuted, fontSize: 13, padding: "6px 0 16px", cursor: "pointer" }}
                >
                  <ArrowLeft size={15} />
                  Voltar pra lista
                </button>
              )}
              {selectedAlert ? (
                <div key={selectedAlert.id} className="lp-fade-up">
                  <div style={{ position: "relative", width: "100%", aspectRatio: "16/9", borderRadius: 10, background: "#000", border: `1px solid ${COLORS.border}`, overflow: "hidden", marginBottom: 18, boxShadow: SHADOW }}>
                    {selectedAlert.clip_url ? (
                      <video key={selectedAlert.id} src={selectedAlert.clip_url} controls style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }} />
                    ) : (
                      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <Eye size={30} color="rgba(255,255,255,0.15)" />
                      </div>
                    )}
                    <div style={{ position: "absolute", top: 10, left: 12, fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: "rgba(255,255,255,0.7)", pointerEvents: "none" }}>
                      {selectedAlert.camera_label}
                    </div>
                    <div style={{ position: "absolute", top: 10, right: 12, fontFamily: "'IBM Plex Mono', monospace", fontSize: 11, color: COLORS.amber, pointerEvents: "none" }}>
                      confiança: {Math.round(selectedAlert.confidence * 100)}%
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 600 }}>{selectedAlert.reason}</div>
                      <div style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 4 }}>{stores.find((s) => s.id === selectedAlert.store_id)?.name}</div>
                    </div>
                    <StatusBadge status={selectedAlert.status} />
                  </div>

                  <div style={{ display: "flex", gap: 10, marginBottom: 24 }}>
                    <button className="lp-btn" onClick={() => reviewAlert(selectedAlert.id, "confirmed")} style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", borderRadius: 8, border: "none", background: COLORS.red, color: "#fff", fontSize: 13, fontWeight: 600 }}>
                      <ShieldAlert size={14} />
                      Confirmar ocorrência
                    </button>
                    <button className="lp-btn" onClick={() => reviewAlert(selectedAlert.id, "dismissed")} style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: "transparent", color: COLORS.textMuted, fontSize: 13, fontWeight: 500 }}>
                      <XCircle size={14} />
                      Marcar como falso positivo
                    </button>
                    {selectedAlert.clip_url && (
                      <button
                        className="lp-btn"
                        onClick={() => downloadClip(selectedAlert.clip_url, `vigia-${selectedAlert.camera_label}-${selectedAlert.id}.mp4`)}
                        title="Baixar clipe"
                        style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: "transparent", color: COLORS.textMuted, fontSize: 13, fontWeight: 500, marginLeft: "auto" }}
                      >
                        <Download size={14} />
                        Baixar clipe
                      </button>
                    )}
                  </div>

                  <div style={{ borderTop: `1px solid ${COLORS.borderSoft}`, paddingTop: 16 }}>
                    <div style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.textFaint, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 10 }}>
                      Registro de auditoria
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: COLORS.textMuted, padding: "5px 0" }}>
                      <Clock size={13} color={COLORS.textFaint} />
                      Evento criado em {new Date(selectedAlert.created_at).toLocaleString("pt-BR")}
                    </div>
                    {selectedAlert.status !== "pending" && (
                      <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5, color: COLORS.textMuted, padding: "5px 0" }}>
                        {selectedAlert.status === "confirmed" ? <CheckCircle2 size={13} color={COLORS.red} /> : <XCircle size={13} color={COLORS.textFaint} />}
                        {selectedAlert.status === "confirmed" ? "Ocorrência confirmada pelo gestor" : "Marcado como falso positivo pelo gestor"}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: 8, color: COLORS.textFaint, fontSize: 13 }}>
                  {loadingAlerts && <Loader2 size={14} className="lp-spin" />}
                  {loadingAlerts ? "Carregando alertas…" : "Nenhum alerta selecionado."}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {showAddStore && (
        <AddStoreModal
          api={api}
          onClose={() => setShowAddStore(false)}
          onCreated={(store) => {
            // Mesmos defaults que o backend dá pra uma loja recém-criada
            // (ver models.py) — evita "undefined" na tela de Status antes
            // do próximo carregamento da lista via GET /v1/stores.
            setStores((prev) => [
              ...prev,
              { id: store.id, name: store.name, city: store.city, onboarding_status: "pending", last_seen_at: null, online: false },
            ]);
            setSelectedStore(store.id);
          }}
        />
      )}
    </div>
  );
}

// --- tela que a pessoa convidada abre ao clicar no link do email --------

function AcceptInviteScreen({ token, onAccepted }) {
  const [details, setDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(true);
  const [detailsError, setDetailsError] = useState(null);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  useEffect(() => {
    fetch(`${API_BASE}/v1/invites/${token}`)
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || "Convite inválido");
        }
        return res.json();
      })
      .then((data) => {
        setDetails(data);
        setLoadingDetails(false);
      })
      .catch((err) => {
        setDetailsError(err.message);
        setLoadingDetails(false);
      });
  }, [token]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (password !== confirmPassword) {
      setSubmitError("As senhas não coincidem");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await fetch(`${API_BASE}/v1/invites/${token}/accept`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Não foi possível aceitar o convite");
      }
      const data = await res.json();
      onAccepted(data);
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  if (loadingDetails) {
    return (
      <AuthShell>
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: COLORS.textMuted, fontSize: 13 }}>
          <Loader2 size={14} className="lp-spin" />
          Carregando convite…
        </div>
      </AuthShell>
    );
  }

  if (detailsError) {
    return (
      <AuthShell>
        <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 8 }}>Convite indisponível</div>
        <ErrorNote message={detailsError} />
        <p style={{ fontSize: 12.5, color: COLORS.textFaint, marginTop: 10 }}>
          Peça ao dono da conta para reenviar o convite.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell width={340}>
      <p style={{ fontSize: 12.5, color: COLORS.textMuted, marginBottom: 18, lineHeight: 1.5 }}>
        Olá, <strong style={{ color: COLORS.text }}>{details.name}</strong>. Você foi convidado(a) para acessar
        o painel da <strong style={{ color: COLORS.text }}>{details.company_name}</strong>
        {details.store_names.length > 0 && (
          <> — lojas: {details.store_names.join(", ")}</>
        )}
        . Crie sua senha para continuar.
      </p>
      <form onSubmit={handleSubmit}>
        <Field label="Email" value={details.email} disabled style={{ ...inputStyle, opacity: 0.6 }} />
        <Field label="Crie uma senha" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} />
        <Field label="Confirme a senha" type="password" required minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
        <ErrorNote message={submitError} />
        <PrimaryButton type="submit" loading={submitting}>Criar senha e entrar</PrimaryButton>
      </form>
    </AuthShell>
  );
}

// --- raiz: login / signup / convite / dashboard -----------------------------

export default function App() {
  const [view, setView] = useState("login"); // "login" | "signup" | "forgot"
  const [authenticated, setAuthenticated] = useState(false);
  const [accessPaused, setAccessPaused] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);

  // Chamado por login/reset de senha/aceite de convite — todos devolvem
  // o mesmo formato (MeOut, com access_paused) na própria resposta, sem
  // precisar de uma segunda chamada a /me.
  function handleAuthenticated(data) {
    setAuthenticated(true);
    setAccessPaused(Boolean(data?.access_paused));
  }

  // A sessão agora vive num cookie HttpOnly (não mais em localStorage) —
  // o front não consegue ler o token, então descobre se já está
  // autenticado perguntando pro backend. Roda uma vez ao carregar a
  // página (é assim que a sessão sobrevive a um F5).
  const refreshAuth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/auth/me`, {
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      setAuthenticated(res.ok);
      if (res.ok) {
        const data = await res.json().catch(() => null);
        setAccessPaused(Boolean(data?.access_paused));
      }
    } catch {
      setAuthenticated(false);
    } finally {
      setCheckingAuth(false);
    }
  }, []);

  useEffect(() => {
    refreshAuth();
  }, [refreshAuth]);

  async function handleLogout() {
    try {
      await fetch(`${API_BASE}/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
    } catch {
      // mesmo se a chamada falhar, ainda derruba a sessão localmente
    }
    setAuthenticated(false);
  }

  const inviteToken =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("token") : null;
  // Parâmetro diferente de "token" (usado pelo convite de equipe acima) —
  // evita que os dois fluxos se confundam quando o usuário abre o link
  // recebido por email.
  const resetToken =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("reset_token") : null;
  // Volta do Checkout do Asaas no fluxo de aquisição por link — pagou
  // antes de ter conta (ver GET /v1/billing/prepaid-checkout no backend).
  // Força a tela de cadastro mesmo que "view" esteja em outra coisa.
  const prepaidToken =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("prepaid_token") : null;

  if (checkingAuth) {
    return (
      <AuthShell width={280}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: COLORS.textMuted, fontSize: 13 }}>
          <Loader2 size={14} className="lp-spin" />
          Verificando sessão…
        </div>
      </AuthShell>
    );
  }

  if (!authenticated && resetToken) {
    return <ResetPasswordScreen token={resetToken} onReset={handleAuthenticated} />;
  }

  if (!authenticated && inviteToken) {
    return <AcceptInviteScreen token={inviteToken} onAccepted={handleAuthenticated} />;
  }

  if (!authenticated && prepaidToken) {
    return (
      <OnboardingScreen
        prepaidToken={prepaidToken}
        onFinished={() => setAuthenticated(true)}
        onGoToLogin={() => setView("login")}
      />
    );
  }

  if (authenticated) {
    return <Dashboard onLogout={handleLogout} accessPaused={accessPaused} />;
  }

  if (view === "signup") {
    return <OnboardingScreen onFinished={() => setAuthenticated(true)} onGoToLogin={() => setView("login")} />;
  }

  if (view === "forgot") {
    return <ForgotPasswordScreen onGoToLogin={() => setView("login")} />;
  }

  return (
    <LoginScreen
      onLogin={handleAuthenticated}
      onGoToSignup={() => setView("signup")}
      onGoToForgot={() => setView("forgot")}
    />
  );
}
