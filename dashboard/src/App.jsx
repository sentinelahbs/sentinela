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
} from "lucide-react";

// Em produção, defina VITE_API_BASE (ex: https://api.vigialoja.com.br) nas
// variáveis de ambiente do provedor de hospedagem do dashboard. Sem isso, cai
// no endereço de desenvolvimento local (mesmo host, porta 8000).
const API_BASE = import.meta.env.VITE_API_BASE || `http://${window.location.hostname}:8000`;
const TURNSTILE_SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY || "";

const COLORS = {
  bg: "#12141A",
  panel: "#191C24",
  panelAlt: "#20242E",
  border: "#2A2E38",
  borderSoft: "#22262F",
  text: "#ECEDEF",
  textMuted: "#888EA0",
  textFaint: "#5B6070",
  amber: "#F2A93B",
  teal: "#34D399",
  red: "#F2555A",
};

// Sombra compartilhada — dá profundidade a painéis, cartões e modais sem
// depender de bordas mais fortes (fica sutil demais em fundo escuro sozinha).
const SHADOW = "0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -8px rgba(0,0,0,0.55)";
const SHADOW_SOFT = "0 1px 2px rgba(0,0,0,0.25), 0 4px 14px -6px rgba(0,0,0,0.4)";

const globalFonts = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
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
  @media (prefers-reduced-motion: reduce) {
    .lp-fade-up, .lp-modal-in, .lp-overlay-in, .lp-spin { animation: none; }
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
      <ShieldAlert size={size} color={COLORS.amber} />
      <span style={{ fontWeight: 700, fontSize }}>
        vig<span style={{ color: COLORS.teal }}>IA</span>
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
        <div style={{ marginBottom: 22 }}>
          <Logo size={26} fontSize={20} />
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

function LoginScreen({ onLogin, onGoToSignup }) {
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, turnstile_token: turnstileToken }),
      });
      if (!res.ok) {
        if (res.status === 429) {
          throw new Error("Muitas tentativas seguidas — aguarde um minuto e tente de novo.");
        }
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Email ou senha inválidos");
      }
      const data = await res.json();
      onLogin(data.access_token);
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

// --- ONBOARDING / SIGNUP -----------------------------------------------

function OnboardingScreen({ onFinished, onGoToLogin }) {
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
  const [result, setResult] = useState(null); // { access_token, store_id, store_edge_api_key }
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, turnstile_token: turnstileToken }),
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

        <PrimaryButton onClick={() => onFinished(result.access_token)}>
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

function useApiClient(token, onUnauthorized) {
  return useCallback(
    async (path, options = {}) => {
      const res = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
          ...(options.headers || {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
    [token, onUnauthorized]
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

function Stat({ icon, label, value, color }) {
  return (
    <div style={{ textAlign: "right", padding: "8px 14px", borderRadius: 9, background: COLORS.panelAlt, border: `1px solid ${COLORS.borderSoft}`, minWidth: 96 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6, fontSize: 10.5, color: COLORS.textFaint, marginBottom: 4, letterSpacing: "0.02em" }}>
        {icon}
        {label}
      </div>
      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 18, fontWeight: 600, color, fontVariantNumeric: "tabular-nums" }}>{value}</div>
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

function Dashboard({ token, onLogout }) {
  const api = useApiClient(token, onLogout);

  const [stores, setStores] = useState([]);
  const [selectedStore, setSelectedStore] = useState("all");
  const [alerts, setAlerts] = useState([]);
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [loadingStores, setLoadingStores] = useState(true);
  const [loadingAlerts, setLoadingAlerts] = useState(false);
  const [error, setError] = useState(null);
  const [showAddStore, setShowAddStore] = useState(false);
  const [activeView, setActiveView] = useState("alerts"); // "alerts" | "team"
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
  const storeName = selectedStore === "all" ? "Todas as lojas" : stores.find((s) => s.id === selectedStore)?.name;

  const showEmptyState = !loadingStores && stores.length === 0;

  return (
    <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", background: COLORS.bg, color: COLORS.text, minHeight: "100dvh", display: "flex", overflow: "hidden" }}>
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
        <div style={{ padding: "0 6px", marginBottom: 28 }}>
          <Logo size={26} fontSize={19} />
        </div>

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
            <div style={{ display: "flex", alignItems: isMobile ? "flex-start" : "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, padding: isMobile ? "14px 16px" : "16px 22px", borderBottom: `1px solid ${COLORS.border}` }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{storeName}</div>
                <div style={{ fontSize: 12, color: COLORS.textFaint, fontFamily: "'IBM Plex Mono', monospace", marginTop: 2 }}>
                  {loadingAlerts ? "Atualizando…" : `${alerts.length} evento(s)`}
                </div>
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <Stat icon={<Bell size={14} color={COLORS.amber} />} label="Pendentes" value={pendingCount} color={COLORS.amber} />
                <Stat icon={<ShieldAlert size={14} color={COLORS.red} />} label="Confirmados" value={confirmedCount} color={COLORS.red} />
                {!isMobile && (
                  <Stat icon={<TrendingDown size={14} color={COLORS.teal} />} label="Taxa de falso positivo" value={`${falsePositiveRate}%`} color={COLORS.teal} />
                )}
              </div>
            </div>

            {error && (
              <div style={{ padding: "10px 22px", background: "rgba(242,85,90,0.1)", color: COLORS.red, fontSize: 12.5, display: "flex", alignItems: "center", gap: 8 }}>
                <AlertTriangle size={14} />
                {error}
              </div>
            )}
          </>
        )}

        {activeView === "team" ? (
          <TeamPanel api={api} stores={stores} />
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
                <div className="lp-fade-up" style={{ padding: "40px 24px", color: COLORS.textFaint, fontSize: 13, textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
                  <ShieldAlert size={24} color={COLORS.textFaint} style={{ opacity: 0.5 }} />
                  <span>Nenhum alerta por aqui — tudo tranquilo.</span>
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
            setStores((prev) => [...prev, { id: store.id, name: store.name, city: store.city }]);
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Não foi possível aceitar o convite");
      }
      const data = await res.json();
      onAccepted(data.access_token);
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
  const [view, setView] = useState("login"); // "login" | "signup"
  // Sessão persiste no localStorage — sem isso, dar refresh na página
  // (ou fechar e reabrir o navegador) sempre voltava pro login, mesmo
  // com o token ainda válido.
  const [token, setTokenState] = useState(() => localStorage.getItem("vigia_token"));

  function setToken(newToken) {
    if (newToken) {
      localStorage.setItem("vigia_token", newToken);
    } else {
      localStorage.removeItem("vigia_token");
    }
    setTokenState(newToken);
  }

  const inviteToken =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("token") : null;

  if (!token && inviteToken) {
    return <AcceptInviteScreen token={inviteToken} onAccepted={setToken} />;
  }

  if (token) {
    return <Dashboard token={token} onLogout={() => setToken(null)} />;
  }

  if (view === "signup") {
    return <OnboardingScreen onFinished={setToken} onGoToLogin={() => setView("login")} />;
  }

  return <LoginScreen onLogin={setToken} onGoToSignup={() => setView("signup")} />;
}
