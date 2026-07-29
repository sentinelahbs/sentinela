import React, { useState, useEffect, useCallback } from "react";
import {
  ShieldAlert,
  Camera,
  Store,
  Clock,
  CheckCircle2,
  XCircle,
  TrendingDown,
  Bell,
  Plus,
  Circle,
  Eye,
  Building2,
  LogOut,
  Loader2,
  AlertTriangle,
} from "lucide-react";

// Aponte para a sua instância do backend (app/main.py). Em produção isso
// viria de uma variável de ambiente de build, não hardcoded assim.
const API_BASE = "http://localhost:8000";

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

// --- cliente da API ----------------------------------------------------

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

// --- tela de login -------------------------------------------------------

function LoginScreen({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
        body: JSON.stringify({ email, password }),
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
    <div
      style={{
        fontFamily: "'IBM Plex Sans', sans-serif",
        background: COLORS.bg,
        color: COLORS.text,
        minHeight: 640,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: 12,
        border: `1px solid ${COLORS.border}`,
      }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
        * { box-sizing: border-box; }
      `}</style>
      <form
        onSubmit={handleSubmit}
        style={{
          width: 300,
          background: COLORS.panel,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 10,
          padding: 28,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 22 }}>
          <ShieldAlert size={20} color={COLORS.amber} />
          <span style={{ fontWeight: 700, fontSize: 16 }}>Sentinela</span>
        </div>

        <label style={{ fontSize: 12, color: COLORS.textMuted, display: "block", marginBottom: 5 }}>
          Email
        </label>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={inputStyle}
        />

        <label style={{ fontSize: 12, color: COLORS.textMuted, display: "block", margin: "14px 0 5px" }}>
          Senha
        </label>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={inputStyle}
        />

        {error && (
          <div
            style={{
              marginTop: 14,
              fontSize: 12.5,
              color: COLORS.red,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <AlertTriangle size={13} />
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          style={{
            marginTop: 20,
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
            cursor: "pointer",
          }}
        >
          {loading && <Loader2 size={14} className="lp-spin" />}
          Entrar
        </button>

        <div style={{ marginTop: 14, fontSize: 11, color: COLORS.textFaint, fontFamily: "'IBM Plex Mono', monospace" }}>
          API: {API_BASE}
        </div>
      </form>
    </div>
  );
}

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

// --- badges / thumb (iguais ao protótipo anterior) ------------------------

function StatusBadge({ status }) {
  const map = {
    pending: { label: "Aguardando revisão", color: COLORS.amber },
    confirmed: { label: "Confirmado", color: COLORS.red },
    dismissed: { label: "Falso positivo", color: COLORS.textFaint },
  };
  const s = map[status] || map.pending;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 11,
        fontFamily: "'IBM Plex Mono', monospace",
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        color: s.color,
      }}
    >
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
        background: thumbnailUrl
          ? `#000 url(${thumbnailUrl}) center/cover no-repeat`
          : "repeating-linear-gradient(0deg, #23262f 0px, #23262f 2px, #1b1e26 2px, #1b1e26 4px)",
        border: `1px solid ${COLORS.border}`,
      }}
    >
      {isPending && (
        <div style={{ position: "absolute", top: 5, left: 5, display: "flex", alignItems: "center", gap: 4 }}>
          <div
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: COLORS.red,
              boxShadow: `0 0 6px ${COLORS.red}`,
            }}
          />
          <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 9, color: "#fff" }}>REC</span>
        </div>
      )}
      {!thumbnailUrl && (
        <Camera size={18} color="rgba(255,255,255,0.18)" style={{ position: "absolute", bottom: 6, right: 6 }} />
      )}
    </div>
  );
}

function Stat({ icon, label, value, color }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 6, fontSize: 11, color: COLORS.textFaint, marginBottom: 3 }}>
        {icon}
        {label}
      </div>
      <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: 17, fontWeight: 600, color }}>{value}</div>
    </div>
  );
}

// --- dashboard principal ---------------------------------------------------

function Dashboard({ token, onLogout }) {
  const api = useApiClient(token, onLogout);

  const [stores, setStores] = useState([]);
  const [selectedStore, setSelectedStore] = useState("all");
  const [alerts, setAlerts] = useState([]);
  const [selectedAlertId, setSelectedAlertId] = useState(null);
  const [loadingStores, setLoadingStores] = useState(true);
  const [loadingAlerts, setLoadingAlerts] = useState(false);
  const [error, setError] = useState(null);

  // carrega as lojas do usuário logado (isolamento multi-tenant vem do backend)
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
      const results = await Promise.all(
        targetStores.map((id) => api(`/v1/stores/${id}/alerts`))
      );
      const merged = results.flat().sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      setAlerts(merged);
      if (merged.length > 0) setSelectedAlertId((prev) => prev ?? merged[0].id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingAlerts(false);
    }
  }, [api, stores, selectedStore]);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  async function reviewAlert(id, status) {
    // atualização otimista — a UI responde na hora, e reconcilia com o
    // servidor em seguida
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, status } : a)));
    try {
      await api(`/v1/alerts/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
    } catch (err) {
      setError(err.message);
      loadAlerts(); // desfaz a atualização otimista se a chamada falhou
    }
  }

  const selectedAlert = alerts.find((a) => a.id === selectedAlertId) || alerts[0];
  const pendingCount = alerts.filter((a) => a.status === "pending").length;
  const confirmedCount = alerts.filter((a) => a.status === "confirmed").length;
  const falsePositiveRate = alerts.length
    ? Math.round((alerts.filter((a) => a.status === "dismissed").length / alerts.length) * 100)
    : 0;

  const storeName = selectedStore === "all" ? "Todas as lojas" : stores.find((s) => s.id === selectedStore)?.name;

  return (
    <div
      style={{
        fontFamily: "'IBM Plex Sans', sans-serif",
        background: COLORS.bg,
        color: COLORS.text,
        minHeight: 640,
        display: "flex",
        borderRadius: 12,
        overflow: "hidden",
        border: `1px solid ${COLORS.border}`,
      }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
        * { box-sizing: border-box; }
        .lp-row:hover { background: ${COLORS.panelAlt} !important; }
        .lp-btn { cursor: pointer; transition: opacity .15s ease, transform .1s ease; }
        .lp-btn:hover { opacity: 0.85; }
        .lp-btn:active { transform: scale(0.97); }
        .lp-scroll::-webkit-scrollbar { width: 6px; }
        .lp-scroll::-webkit-scrollbar-thumb { background: ${COLORS.border}; border-radius: 3px; }
        .lp-spin { animation: lp-spin 0.8s linear infinite; }
        @keyframes lp-spin { to { transform: rotate(360deg); } }
      `}</style>

      {/* Sidebar */}
      <div style={{ width: 208, flexShrink: 0, background: COLORS.panel, borderRight: `1px solid ${COLORS.border}`, padding: "20px 14px", display: "flex", flexDirection: "column" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "0 6px", marginBottom: 28 }}>
          <ShieldAlert size={20} color={COLORS.amber} />
          <span style={{ fontWeight: 700, fontSize: 15 }}>Sentinela</span>
        </div>

        <div style={{ fontSize: 10, fontFamily: "'IBM Plex Mono', monospace", color: COLORS.textFaint, letterSpacing: "0.08em", textTransform: "uppercase", padding: "0 6px", marginBottom: 8 }}>
          Lojas
        </div>

        <button
          className="lp-btn"
          onClick={() => setSelectedStore("all")}
          style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: selectedStore === "all" ? COLORS.panelAlt : "transparent", color: selectedStore === "all" ? COLORS.text : COLORS.textMuted, fontSize: 13, textAlign: "left", marginBottom: 2 }}
        >
          <Building2 size={14} />
          Todas as lojas
        </button>

        {loadingStores && (
          <div style={{ fontSize: 12, color: COLORS.textFaint, padding: "8px" }}>Carregando lojas…</div>
        )}

        {stores.map((store) => {
          const count = alerts.filter((a) => a.store_id === store.id && a.status === "pending").length;
          const active = selectedStore === store.id;
          return (
            <button
              key={store.id}
              className="lp-btn"
              onClick={() => setSelectedStore(store.id)}
              style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: active ? COLORS.panelAlt : "transparent", color: active ? COLORS.text : COLORS.textMuted, fontSize: 13, textAlign: "left", marginBottom: 2 }}
            >
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

        <button className="lp-btn" style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: `1px dashed ${COLORS.border}`, background: "transparent", color: COLORS.textFaint, fontSize: 12.5, textAlign: "left", marginTop: 6 }}>
          <Plus size={13} />
          Adicionar loja
        </button>

        <button
          className="lp-btn"
          onClick={onLogout}
          style={{ marginTop: "auto", display: "flex", alignItems: "center", gap: 8, padding: "8px 8px", borderRadius: 7, border: "none", background: "transparent", color: COLORS.textFaint, fontSize: 12.5, textAlign: "left" }}
        >
          <LogOut size={13} />
          Sair
        </button>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 22px", borderBottom: `1px solid ${COLORS.border}` }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{storeName}</div>
            <div style={{ fontSize: 12, color: COLORS.textFaint, fontFamily: "'IBM Plex Mono', monospace", marginTop: 2 }}>
              {loadingAlerts ? "Atualizando…" : `${alerts.length} evento(s)`}
            </div>
          </div>
          <div style={{ display: "flex", gap: 20 }}>
            <Stat icon={<Bell size={14} color={COLORS.amber} />} label="Pendentes" value={pendingCount} color={COLORS.amber} />
            <Stat icon={<ShieldAlert size={14} color={COLORS.red} />} label="Confirmados" value={confirmedCount} color={COLORS.red} />
            <Stat icon={<TrendingDown size={14} color={COLORS.teal} />} label="Taxa de falso positivo" value={`${falsePositiveRate}%`} color={COLORS.teal} />
          </div>
        </div>

        {error && (
          <div style={{ padding: "10px 22px", background: "rgba(242,85,90,0.1)", color: COLORS.red, fontSize: 12.5, display: "flex", alignItems: "center", gap: 8 }}>
            <AlertTriangle size={14} />
            {error}
          </div>
        )}

        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          <div className="lp-scroll" style={{ width: 340, flexShrink: 0, borderRight: `1px solid ${COLORS.border}`, overflowY: "auto", padding: "10px 0" }}>
            {!loadingAlerts && alerts.length === 0 && (
              <div style={{ padding: 24, color: COLORS.textFaint, fontSize: 13, textAlign: "center" }}>
                Nenhum alerta por aqui.
              </div>
            )}
            {alerts.map((alert) => {
              const store = stores.find((s) => s.id === alert.store_id);
              const active = selectedAlertId === alert.id;
              return (
                <div
                  key={alert.id}
                  className="lp-row"
                  onClick={() => setSelectedAlertId(alert.id)}
                  style={{ display: "flex", gap: 10, padding: "10px 16px", cursor: "pointer", background: active ? COLORS.panelAlt : "transparent", borderLeft: active ? `2px solid ${COLORS.amber}` : "2px solid transparent" }}
                >
                  <Thumb status={alert.status} thumbnailUrl={alert.thumbnail_url} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {alert.camera_label}
                    </div>
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

          <div style={{ flex: 1, padding: 22, overflowY: "auto" }} className="lp-scroll">
            {selectedAlert ? (
              <>
                <div style={{ position: "relative", width: "100%", aspectRatio: "16/9", borderRadius: 10, background: "#000", border: `1px solid ${COLORS.border}`, overflow: "hidden", marginBottom: 18 }}>
                  {selectedAlert.clip_url ? (
                    <video
                      key={selectedAlert.id}
                      src={selectedAlert.clip_url}
                      controls
                      style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000" }}
                    />
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
                    <div style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 4 }}>
                      {stores.find((s) => s.id === selectedAlert.store_id)?.name}
                    </div>
                  </div>
                  <StatusBadge status={selectedAlert.status} />
                </div>

                <div style={{ display: "flex", gap: 10, marginBottom: 24 }}>
                  <button
                    className="lp-btn"
                    onClick={() => reviewAlert(selectedAlert.id, "confirmed")}
                    style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", borderRadius: 8, border: "none", background: COLORS.red, color: "#fff", fontSize: 13, fontWeight: 600 }}
                  >
                    <ShieldAlert size={14} />
                    Confirmar ocorrência
                  </button>
                  <button
                    className="lp-btn"
                    onClick={() => reviewAlert(selectedAlert.id, "dismissed")}
                    style={{ display: "flex", alignItems: "center", gap: 6, padding: "9px 14px", borderRadius: 8, border: `1px solid ${COLORS.border}`, background: "transparent", color: COLORS.textMuted, fontSize: 13, fontWeight: 500 }}
                  >
                    <XCircle size={14} />
                    Marcar como falso positivo
                  </button>
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
                      {selectedAlert.status === "confirmed" ? (
                        <CheckCircle2 size={13} color={COLORS.red} />
                      ) : (
                        <XCircle size={13} color={COLORS.textFaint} />
                      )}
                      {selectedAlert.status === "confirmed" ? "Ocorrência confirmada pelo gestor" : "Marcado como falso positivo pelo gestor"}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div style={{ color: COLORS.textFaint, fontSize: 13 }}>
                {loadingAlerts ? "Carregando alertas…" : "Nenhum alerta selecionado."}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// --- raiz: troca entre login e dashboard -----------------------------------

export default function App() {
  const [token, setToken] = useState(null);

  if (!token) {
    return <LoginScreen onLogin={setToken} />;
  }
  return <Dashboard token={token} onLogout={() => setToken(null)} />;
}
