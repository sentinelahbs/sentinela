import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  ShieldAlert,
  Building2,
  Store,
  Users,
  Loader2,
  AlertTriangle,
  Circle,
  ArrowLeft,
  LogOut,
  Eye,
  EyeOff,
  Check,
} from "lucide-react";

// Sem VITE_API_BASE definida (ex: rodando local com `npm run dev`),
// cai no backend de produção — troque pra http://localhost:8000 num
// .env.local se for testar contra o backend local.
const API_BASE = import.meta.env.VITE_API_BASE || "https://api.vigialoja.com.br";
// Mesma site key pública já usada pelo dashboard de clientes — reaproveitar
// evita precisar criar um segundo widget no Cloudflare Turnstile.
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

const globalFonts = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
  * { box-sizing: border-box; }
  .lp-row:hover { background: ${COLORS.panelAlt} !important; cursor: pointer; }
  .lp-btn { cursor: pointer; transition: opacity .15s ease; }
  .lp-btn:hover { opacity: 0.85; }
  .lp-spin { animation: lp-spin 0.8s linear infinite; }
  @keyframes lp-spin { to { transform: rotate(360deg); } }
  @keyframes lp-fade-up { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
  .lp-fade-up { animation: lp-fade-up .25s ease both; }
`;

const inputStyle = {
  width: "100%",
  padding: "9px 10px",
  borderRadius: 7,
  border: `1px solid ${COLORS.border}`,
  background: COLORS.panelAlt,
  color: COLORS.text,
  fontSize: 13,
  outline: "none",
};

const STATUS_MAP = {
  none: { label: "Sem assinatura", color: COLORS.textFaint },
  pending: { label: "Pagamento pendente", color: COLORS.amber },
  active: { label: "Ativa", color: COLORS.teal },
  overdue: { label: "Em atraso", color: COLORS.red },
  canceled: { label: "Cancelada", color: COLORS.textFaint },
};

function StatusBadge({ status }) {
  const s = STATUS_MAP[status] || STATUS_MAP.none;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "'IBM Plex Mono', monospace", letterSpacing: "0.04em", textTransform: "uppercase", color: s.color }}>
      <Circle size={7} fill={s.color} stroke="none" />
      {s.label}
    </span>
  );
}

function useApiClient(token, onUnauthorized) {
  return useCallback(
    async (path) => {
      const res = await fetch(`${API_BASE}${path}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.status === 401) {
        onUnauthorized();
        throw new Error("Sessão expirada, faça login novamente.");
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Erro ${res.status}`);
      }
      return res.json();
    },
    [token, onUnauthorized]
  );
}

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
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
      <ShieldAlert size={size} color={COLORS.amber} />
      <span style={{ fontWeight: 700, fontSize }}>VigIA</span>
    </div>
  );
}

// Shell compartilhado pelas telas de autenticação (login, esqueci a
// senha, redefinir senha) — mesmo padrão visual usado no dashboard de
// clientes (app-with-onboarding.jsx), adaptado ao formato "cartão" de
// altura fixa já usado neste painel.
function AuthShell({ children, width = 300 }) {
  return (
    <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", background: COLORS.bg, color: COLORS.text, minHeight: 640, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 12, border: `1px solid ${COLORS.border}` }}>
      <style>{globalFonts}</style>
      <div className="lp-fade-up" style={{ width, background: COLORS.panel, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 28 }}>
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

function LoginScreen({ onLogin, onGoToForgot }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

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
    <AuthShell width={300}>
      <form onSubmit={handleSubmit}>
        <Logo />
        <div style={{ fontSize: 11.5, color: COLORS.textFaint, marginBottom: 20 }}>Painel administrativo interno</div>

        <Field label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <Field label="Senha" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        <div style={{ marginTop: -6, marginBottom: 14, textAlign: "right" }}>
          <span className="lp-btn" onClick={onGoToForgot} style={{ fontSize: 12, color: COLORS.textMuted, textDecoration: "underline" }}>
            Esqueceu a senha?
          </span>
        </div>

        <Turnstile onVerify={setTurnstileToken} />
        <ErrorNote message={error} />
        <PrimaryButton type="submit" loading={loading} disabled={loading || (TURNSTILE_SITE_KEY && !turnstileToken)}>
          Entrar
        </PrimaryButton>
      </form>
    </AuthShell>
  );
}

// --- RECUPERAÇÃO DE SENHA ------------------------------------------------
// Mesmos endpoints /v1/auth/forgot-password e /v1/auth/reset-password do
// dashboard de clientes — só muda app: "admin" (decide pra qual painel o
// link do email aponta) e o parâmetro de URL lido abaixo em App():
// ?reset_token= (não ?token=, que no dashboard de clientes é usado pelo
// convite de equipe — aqui no admin esse parâmetro nem existe, mas
// mantemos o mesmo nome pra reaproveitar o mesmo backend sem ambiguidade).

function ForgotPasswordScreen({ onGoToLogin }) {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sent, setSent] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/v1/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, app: "admin" }),
      });
      if (!res.ok) {
        if (res.status === 429) {
          throw new Error("Muitas tentativas seguidas — aguarde um minuto e tente de novo.");
        }
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || "Não foi possível processar o pedido");
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
      <AuthShell width={320}>
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
    <AuthShell width={320}>
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
        Informe o email da sua conta de administrador — vamos enviar um link para você criar uma nova senha.
      </p>
      <form onSubmit={handleSubmit}>
        <Field label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <ErrorNote message={error} />
        <PrimaryButton type="submit" loading={loading}>Enviar link</PrimaryButton>
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
        headers: { "Content-Type": "application/json" },
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
      onReset(data.access_token);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell width={320}>
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

function AccessDenied({ onLogout }) {
  return (
    <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", background: COLORS.bg, color: COLORS.text, minHeight: 640, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 12, border: `1px solid ${COLORS.border}` }}>
      <style>{globalFonts}</style>
      <div style={{ textAlign: "center", maxWidth: 320 }}>
        <AlertTriangle size={28} color={COLORS.red} style={{ marginBottom: 12 }} />
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>Acesso restrito</div>
        <div style={{ fontSize: 13, color: COLORS.textMuted, marginBottom: 18 }}>
          Esta conta não tem permissão de administrador do VigIA. Este painel é interno, não é o dashboard de clientes.
        </div>
        <button className="lp-btn" onClick={onLogout} style={{ padding: "9px 16px", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: "transparent", color: COLORS.textMuted, fontSize: 13 }}>
          Sair
        </button>
      </div>
    </div>
  );
}

function CompanyDetail({ api, companyId, onBack }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api(`/v1/admin/companies/${companyId}`)
      .then(setDetail)
      .catch((err) => setError(err.message));
  }, [api, companyId]);

  if (error) return <div style={{ padding: 22, color: COLORS.red, fontSize: 13 }}>{error}</div>;
  if (!detail) return <div style={{ padding: 22, color: COLORS.textFaint, fontSize: 13 }}>Carregando…</div>;

  return (
    <div style={{ padding: 22, flex: 1, overflowY: "auto" }}>
      <button className="lp-btn" onClick={onBack} style={{ display: "flex", alignItems: "center", gap: 6, border: "none", background: "transparent", color: COLORS.textMuted, fontSize: 12.5, marginBottom: 16 }}>
        <ArrowLeft size={13} />
        Voltar
      </button>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
        <div>
          <div style={{ fontSize: 17, fontWeight: 600 }}>{detail.name}</div>
          <div style={{ fontSize: 11.5, color: COLORS.textFaint, fontFamily: "'IBM Plex Mono', monospace", marginTop: 3 }}>
            cliente desde {new Date(detail.created_at).toLocaleDateString("pt-BR")}
          </div>
        </div>
        <StatusBadge status={detail.subscription_status} />
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20, fontSize: 12.5 }}>
        <span style={{ color: COLORS.textFaint }}>Câmeras:</span>
        <span
          style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontWeight: 600,
            color: detail.cameras_used >= detail.camera_limit && detail.camera_limit > 0 ? COLORS.red : COLORS.text,
          }}
        >
          {detail.cameras_used} / {detail.camera_limit}
        </span>
      </div>

      <div style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.textFaint, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8 }}>
        Lojas ({detail.stores.length})
      </div>
      <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, overflow: "hidden", marginBottom: 22 }}>
        {detail.stores.length === 0 && <div style={{ padding: 14, fontSize: 12.5, color: COLORS.textFaint }}>Nenhuma loja cadastrada.</div>}
        {detail.stores.map((s, i) => (
          <div key={s.id} style={{ padding: "10px 14px", borderTop: i === 0 ? "none" : `1px solid ${COLORS.borderSoft}`, fontSize: 13 }}>
            {s.name} {s.city && <span style={{ color: COLORS.textFaint }}>— {s.city}</span>}
          </div>
        ))}
      </div>

      <div style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.textFaint, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8 }}>
        Equipe ({detail.users.length})
      </div>
      <div style={{ border: `1px solid ${COLORS.border}`, borderRadius: 8, overflow: "hidden" }}>
        {detail.users.map((u, i) => (
          <div key={u.id} style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", borderTop: i === 0 ? "none" : `1px solid ${COLORS.borderSoft}` }}>
            <div>
              <div style={{ fontSize: 13 }}>{u.name}</div>
              <div style={{ fontSize: 11, color: COLORS.textFaint }}>{u.email}</div>
            </div>
            <div style={{ fontSize: 10.5, fontFamily: "'IBM Plex Mono', monospace", textTransform: "uppercase", color: u.role === "owner" ? COLORS.amber : COLORS.teal }}>
              {u.role === "owner" ? "dono" : "gestor"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AdminPanel({ token, onLogout }) {
  const api = useApiClient(token, onLogout);
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    api("/v1/admin/companies")
      .then((data) => {
        setCompanies(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [api]);

  const totalStores = companies.reduce((sum, c) => sum + c.store_count, 0);
  const activeCount = companies.filter((c) => c.subscription_status === "active").length;
  const overdueCount = companies.filter((c) => c.subscription_status === "overdue").length;

  return (
    <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", background: COLORS.bg, color: COLORS.text, minHeight: 640, display: "flex", flexDirection: "column", borderRadius: 12, overflow: "hidden", border: `1px solid ${COLORS.border}` }}>
      <style>{globalFonts}</style>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 22px", borderBottom: `1px solid ${COLORS.border}` }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ShieldAlert size={19} color={COLORS.amber} />
          <span style={{ fontWeight: 700, fontSize: 15 }}>VigIA</span>
          <span style={{ fontSize: 11, color: COLORS.textFaint, marginLeft: 4 }}>· admin interno</span>
        </div>
        <button className="lp-btn" onClick={onLogout} style={{ display: "flex", alignItems: "center", gap: 6, border: "none", background: "transparent", color: COLORS.textFaint, fontSize: 12.5 }}>
          <LogOut size={13} />
          Sair
        </button>
      </div>

      <div style={{ display: "flex", gap: 24, padding: "16px 22px", borderBottom: `1px solid ${COLORS.border}` }}>
        <Stat icon={<Building2 size={14} color={COLORS.text} />} label="Empresas" value={companies.length} />
        <Stat icon={<Store size={14} color={COLORS.text} />} label="Lojas no total" value={totalStores} />
        <Stat icon={<Circle size={14} color={COLORS.teal} />} label="Assinaturas ativas" value={activeCount} color={COLORS.teal} />
        <Stat icon={<AlertTriangle size={14} color={COLORS.red} />} label="Em atraso" value={overdueCount} color={COLORS.red} />
      </div>

      {error && (
        <div style={{ padding: "10px 22px", background: "rgba(242,85,90,0.1)", color: COLORS.red, fontSize: 12.5 }}>{error}</div>
      )}

      {selectedId ? (
        <CompanyDetail api={api} companyId={selectedId} onBack={() => setSelectedId(null)} />
      ) : (
        <div style={{ flex: 1, overflowY: "auto" }}>
          {loading ? (
            <div style={{ padding: 22, color: COLORS.textFaint, fontSize: 13 }}>Carregando empresas…</div>
          ) : companies.length === 0 ? (
            <div style={{ padding: 22, color: COLORS.textFaint, fontSize: 13 }}>Nenhuma empresa cadastrada ainda.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ textAlign: "left", color: COLORS.textFaint, fontSize: 10.5, fontFamily: "'IBM Plex Mono', monospace", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  <th style={{ padding: "10px 22px" }}>Empresa</th>
                  <th style={{ padding: "10px 12px" }}>Lojas</th>
                  <th style={{ padding: "10px 12px" }}>Usuários</th>
                  <th style={{ padding: "10px 12px" }}>Câmeras</th>
                  <th style={{ padding: "10px 12px" }}>Cliente desde</th>
                  <th style={{ padding: "10px 22px" }}>Cobrança</th>
                </tr>
              </thead>
              <tbody>
                {companies.map((c) => (
                  <tr key={c.id} className="lp-row" onClick={() => setSelectedId(c.id)} style={{ borderTop: `1px solid ${COLORS.borderSoft}` }}>
                    <td style={{ padding: "12px 22px", fontWeight: 500 }}>{c.name}</td>
                    <td style={{ padding: "12px" }}>{c.store_count}</td>
                    <td style={{ padding: "12px" }}>{c.user_count}</td>
                    <td
                      style={{
                        padding: "12px",
                        fontFamily: "'IBM Plex Mono', monospace",
                        fontSize: 12,
                        color: c.cameras_used >= c.camera_limit && c.camera_limit > 0 ? COLORS.red : COLORS.textMuted,
                      }}
                    >
                      {c.cameras_used} / {c.camera_limit}
                    </td>
                    <td style={{ padding: "12px", color: COLORS.textFaint, fontFamily: "'IBM Plex Mono', monospace", fontSize: 12 }}>
                      {new Date(c.created_at).toLocaleDateString("pt-BR")}
                    </td>
                    <td style={{ padding: "12px 22px" }}>
                      <StatusBadge status={c.subscription_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ icon, label, value, color }) {
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: COLORS.textFaint, marginBottom: 3 }}>
        {icon}
        {label}
      </div>
      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 17, fontWeight: 600, color: color || COLORS.text }}>{value}</div>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState(null);
  const [me, setMe] = useState(null);
  const [checkingMe, setCheckingMe] = useState(false);
  const [view, setView] = useState("login"); // "login" | "forgot"

  useEffect(() => {
    if (!token) {
      setMe(null);
      return;
    }
    setCheckingMe(true);
    fetch(`${API_BASE}/v1/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data) => {
        setMe(data);
        setCheckingMe(false);
      })
      .catch(() => {
        setToken(null);
        setCheckingMe(false);
      });
  }, [token]);

  // Parâmetro próprio (não "token") — este painel não tem fluxo de
  // convite, mas usa o mesmo nome do dashboard de clientes pra reaproveitar
  // o mesmo backend de recuperação de senha sem qualquer ambiguidade.
  const resetToken =
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("reset_token") : null;

  if (!token && resetToken) {
    return <ResetPasswordScreen token={resetToken} onReset={setToken} />;
  }

  if (!token && view === "forgot") {
    return <ForgotPasswordScreen onGoToLogin={() => setView("login")} />;
  }

  if (!token) {
    return <LoginScreen onLogin={setToken} onGoToForgot={() => setView("forgot")} />;
  }

  if (checkingMe || !me) {
    return (
      <div style={{ fontFamily: "'IBM Plex Sans', sans-serif", background: COLORS.bg, color: COLORS.textFaint, minHeight: 640, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 12, border: `1px solid ${COLORS.border}`, fontSize: 13 }}>
        <style>{globalFonts}</style>
        Verificando acesso…
      </div>
    );
  }

  if (!me.is_platform_admin) {
    return <AccessDenied onLogout={() => setToken(null)} />;
  }

  return <AdminPanel token={token} onLogout={() => setToken(null)} />;
}
