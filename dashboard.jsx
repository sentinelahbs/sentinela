import React, { useState, useMemo } from "react";
import {
  ShieldAlert,
  Camera,
  Store,
  Clock,
  CheckCircle2,
  XCircle,
  TrendingDown,
  Bell,
  ChevronDown,
  Plus,
  Circle,
  Eye,
  Building2,
} from "lucide-react";

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

const STORES = [
  { id: "s1", name: "Loja Centro", city: "São Paulo, SP" },
  { id: "s2", name: "Loja Norte Shopping", city: "Rio de Janeiro, RJ" },
  { id: "s3", name: "Loja Barra", city: "Salvador, BA" },
];

const ALERTS = [
  {
    id: "a1",
    storeId: "s1",
    camera: "Câmera 03 — Corredor 2",
    time: "14:22:07",
    date: "hoje",
    confidence: 91,
    status: "pending",
  },
  {
    id: "a2",
    storeId: "s1",
    camera: "Câmera 01 — Entrada",
    time: "13:58:40",
    date: "hoje",
    confidence: 64,
    status: "pending",
  },
  {
    id: "a3",
    storeId: "s2",
    camera: "Câmera 05 — Estoque",
    time: "12:31:12",
    date: "hoje",
    confidence: 88,
    status: "confirmed",
  },
  {
    id: "a4",
    storeId: "s1",
    camera: "Câmera 02 — Caixa",
    time: "11:04:55",
    date: "hoje",
    confidence: 47,
    status: "dismissed",
  },
  {
    id: "a5",
    storeId: "s3",
    camera: "Câmera 04 — Fundos",
    time: "09:17:33",
    date: "ontem",
    confidence: 76,
    status: "pending",
  },
];

function StatusBadge({ status }) {
  const map = {
    pending: { label: "Aguardando revisão", color: COLORS.amber },
    confirmed: { label: "Confirmado", color: COLORS.red },
    dismissed: { label: "Falso positivo", color: COLORS.textFaint },
  };
  const s = map[status];
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

function Thumb({ status }) {
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
        background:
          "repeating-linear-gradient(0deg, #23262f 0px, #23262f 2px, #1b1e26 2px, #1b1e26 4px)",
        border: `1px solid ${COLORS.border}`,
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          background:
            "radial-gradient(circle at 30% 30%, rgba(255,255,255,0.05), transparent 60%)",
        }}
      />
      {isPending && (
        <div
          style={{
            position: "absolute",
            top: 5,
            left: 5,
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          <div
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: COLORS.red,
              boxShadow: `0 0 6px ${COLORS.red}`,
            }}
          />
          <span
            style={{
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: 9,
              color: "#fff",
              letterSpacing: "0.05em",
            }}
          >
            REC
          </span>
        </div>
      )}
      <Camera
        size={18}
        color="rgba(255,255,255,0.18)"
        style={{
          position: "absolute",
          bottom: 6,
          right: 6,
        }}
      />
    </div>
  );
}

export default function LossPreventionDashboard() {
  const [selectedStore, setSelectedStore] = useState("all");
  const [storeMenuOpen, setStoreMenuOpen] = useState(false);
  const [alerts, setAlerts] = useState(ALERTS);
  const [selectedAlertId, setSelectedAlertId] = useState(ALERTS[0].id);

  const filteredAlerts = useMemo(() => {
    if (selectedStore === "all") return alerts;
    return alerts.filter((a) => a.storeId === selectedStore);
  }, [alerts, selectedStore]);

  const selectedAlert =
    alerts.find((a) => a.id === selectedAlertId) || filteredAlerts[0];

  const pendingCount = filteredAlerts.filter(
    (a) => a.status === "pending"
  ).length;
  const confirmedCount = filteredAlerts.filter(
    (a) => a.status === "confirmed"
  ).length;
  const falsePositiveRate = Math.round(
    (filteredAlerts.filter((a) => a.status === "dismissed").length /
      Math.max(filteredAlerts.length, 1)) *
      100
  );

  const storeName =
    selectedStore === "all"
      ? "Todas as lojas"
      : STORES.find((s) => s.id === selectedStore)?.name;

  function resolveAlert(id, status) {
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status } : a))
    );
  }

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
      `}</style>

      {/* Sidebar */}
      <div
        style={{
          width: 208,
          flexShrink: 0,
          background: COLORS.panel,
          borderRight: `1px solid ${COLORS.border}`,
          padding: "20px 14px",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "0 6px",
            marginBottom: 28,
          }}
        >
          <ShieldAlert size={20} color={COLORS.amber} />
          <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>
            Sentinela
          </span>
        </div>

        <div
          style={{
            fontSize: 10,
            fontFamily: "'IBM Plex Mono', monospace",
            color: COLORS.textFaint,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            padding: "0 6px",
            marginBottom: 8,
          }}
        >
          Lojas
        </div>

        <button
          className="lp-btn"
          onClick={() => setSelectedStore("all")}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 8px",
            borderRadius: 7,
            border: "none",
            background: selectedStore === "all" ? COLORS.panelAlt : "transparent",
            color: selectedStore === "all" ? COLORS.text : COLORS.textMuted,
            fontSize: 13,
            textAlign: "left",
            marginBottom: 2,
          }}
        >
          <Building2 size={14} />
          Todas as lojas
        </button>

        {STORES.map((store) => {
          const count = alerts.filter(
            (a) => a.storeId === store.id && a.status === "pending"
          ).length;
          const active = selectedStore === store.id;
          return (
            <button
              key={store.id}
              className="lp-btn"
              onClick={() => setSelectedStore(store.id)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
                padding: "8px 8px",
                borderRadius: 7,
                border: "none",
                background: active ? COLORS.panelAlt : "transparent",
                color: active ? COLORS.text : COLORS.textMuted,
                fontSize: 13,
                textAlign: "left",
                marginBottom: 2,
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Store size={14} />
                {store.name}
              </span>
              {count > 0 && (
                <span
                  style={{
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: 10,
                    background: COLORS.amber,
                    color: "#1a1200",
                    borderRadius: 10,
                    padding: "1px 6px",
                    fontWeight: 600,
                  }}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}

        <button
          className="lp-btn"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 8px",
            borderRadius: 7,
            border: `1px dashed ${COLORS.border}`,
            background: "transparent",
            color: COLORS.textFaint,
            fontSize: 12.5,
            textAlign: "left",
            marginTop: 6,
          }}
        >
          <Plus size={13} />
          Adicionar loja
        </button>

        <div style={{ marginTop: "auto", padding: "0 6px" }}>
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
            Plano
          </div>
          <div style={{ fontSize: 12.5, color: COLORS.textMuted }}>
            SaaS · 3 lojas · 12 câmeras
          </div>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Top bar */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 22px",
            borderBottom: `1px solid ${COLORS.border}`,
          }}
        >
          <div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{storeName}</div>
            <div
              style={{
                fontSize: 12,
                color: COLORS.textFaint,
                fontFamily: "'IBM Plex Mono', monospace",
                marginTop: 2,
              }}
            >
              {selectedStore === "all"
                ? "Visão consolidada da rede"
                : STORES.find((s) => s.id === selectedStore)?.city}
            </div>
          </div>
          <div style={{ display: "flex", gap: 20 }}>
            <Stat
              icon={<Bell size={14} color={COLORS.amber} />}
              label="Pendentes"
              value={pendingCount}
              color={COLORS.amber}
            />
            <Stat
              icon={<ShieldAlert size={14} color={COLORS.red} />}
              label="Confirmados hoje"
              value={confirmedCount}
              color={COLORS.red}
            />
            <Stat
              icon={<TrendingDown size={14} color={COLORS.teal} />}
              label="Taxa de falso positivo"
              value={`${falsePositiveRate}%`}
              color={COLORS.teal}
            />
          </div>
        </div>

        {/* Body: feed + detail */}
        <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
          {/* Feed */}
          <div
            className="lp-scroll"
            style={{
              width: 340,
              flexShrink: 0,
              borderRight: `1px solid ${COLORS.border}`,
              overflowY: "auto",
              padding: "10px 0",
            }}
          >
            {filteredAlerts.length === 0 && (
              <div
                style={{
                  padding: 24,
                  color: COLORS.textFaint,
                  fontSize: 13,
                  textAlign: "center",
                }}
              >
                Nenhum alerta para esta loja.
              </div>
            )}
            {filteredAlerts.map((alert) => {
              const store = STORES.find((s) => s.id === alert.storeId);
              const active = selectedAlertId === alert.id;
              return (
                <div
                  key={alert.id}
                  className="lp-row"
                  onClick={() => setSelectedAlertId(alert.id)}
                  style={{
                    display: "flex",
                    gap: 10,
                    padding: "10px 16px",
                    cursor: "pointer",
                    background: active ? COLORS.panelAlt : "transparent",
                    borderLeft: active
                      ? `2px solid ${COLORS.amber}`
                      : "2px solid transparent",
                  }}
                >
                  <Thumb status={alert.status} />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div
                      style={{
                        fontSize: 12.5,
                        fontWeight: 500,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {alert.camera}
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: COLORS.textFaint,
                        marginTop: 2,
                      }}
                    >
                      {selectedStore === "all" ? `${store.name} · ` : ""}
                      {alert.date} {alert.time}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      <StatusBadge status={alert.status} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Detail */}
          <div style={{ flex: 1, padding: 22, overflowY: "auto" }} className="lp-scroll">
            {selectedAlert ? (
              <>
                <div
                  style={{
                    position: "relative",
                    width: "100%",
                    aspectRatio: "16/9",
                    borderRadius: 10,
                    background:
                      "repeating-linear-gradient(0deg, #23262f 0px, #23262f 2px, #191c24 2px, #191c24 4px)",
                    border: `1px solid ${COLORS.border}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginBottom: 18,
                  }}
                >
                  <Eye size={30} color="rgba(255,255,255,0.15)" />
                  <div
                    style={{
                      position: "absolute",
                      top: 10,
                      left: 12,
                      fontFamily: "'IBM Plex Mono', monospace",
                      fontSize: 11,
                      color: "rgba(255,255,255,0.55)",
                    }}
                  >
                    {selectedAlert.camera} · {selectedAlert.date} {selectedAlert.time}
                  </div>
                  <div
                    style={{
                      position: "absolute",
                      bottom: 10,
                      right: 12,
                      fontFamily: "'IBM Plex Mono', monospace",
                      fontSize: 11,
                      color: COLORS.amber,
                    }}
                  >
                    confiança: {selectedAlert.confidence}%
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 18,
                  }}
                >
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600 }}>
                      Evento de comportamento suspeito
                    </div>
                    <div
                      style={{ fontSize: 12.5, color: COLORS.textMuted, marginTop: 4 }}
                    >
                      {STORES.find((s) => s.id === selectedAlert.storeId)?.name} ·{" "}
                      {STORES.find((s) => s.id === selectedAlert.storeId)?.city}
                    </div>
                  </div>
                  <StatusBadge status={selectedAlert.status} />
                </div>

                <div style={{ display: "flex", gap: 10, marginBottom: 24 }}>
                  <button
                    className="lp-btn"
                    onClick={() => resolveAlert(selectedAlert.id, "confirmed")}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "9px 14px",
                      borderRadius: 8,
                      border: "none",
                      background: COLORS.red,
                      color: "#fff",
                      fontSize: 13,
                      fontWeight: 600,
                    }}
                  >
                    <ShieldAlert size={14} />
                    Confirmar ocorrência
                  </button>
                  <button
                    className="lp-btn"
                    onClick={() => resolveAlert(selectedAlert.id, "dismissed")}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "9px 14px",
                      borderRadius: 8,
                      border: `1px solid ${COLORS.border}`,
                      background: "transparent",
                      color: COLORS.textMuted,
                      fontSize: 13,
                      fontWeight: 500,
                    }}
                  >
                    <XCircle size={14} />
                    Marcar como falso positivo
                  </button>
                </div>

                <div
                  style={{
                    borderTop: `1px solid ${COLORS.borderSoft}`,
                    paddingTop: 16,
                  }}
                >
                  <div
                    style={{
                      fontSize: 10,
                      fontFamily: "'IBM Plex Mono', monospace",
                      color: COLORS.textFaint,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      marginBottom: 10,
                    }}
                  >
                    Registro de auditoria
                  </div>
                  <AuditRow
                    icon={<Clock size={13} color={COLORS.textFaint} />}
                    text={`Evento detectado às ${selectedAlert.time}`}
                  />
                  <AuditRow
                    icon={<Eye size={13} color={COLORS.textFaint} />}
                    text="Clipe de 15s gerado automaticamente (5s antes / 10s depois)"
                  />
                  {selectedAlert.status !== "pending" && (
                    <AuditRow
                      icon={
                        selectedAlert.status === "confirmed" ? (
                          <CheckCircle2 size={13} color={COLORS.red} />
                        ) : (
                          <XCircle size={13} color={COLORS.textFaint} />
                        )
                      }
                      text={
                        selectedAlert.status === "confirmed"
                          ? "Ocorrência confirmada pelo gestor"
                          : "Marcado como falso positivo pelo gestor"
                      }
                    />
                  )}
                </div>
              </>
            ) : (
              <div style={{ color: COLORS.textFaint, fontSize: 13 }}>
                Selecione um alerta para revisar.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ icon, label, value, color }) {
  return (
    <div style={{ textAlign: "right" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: 6,
          fontSize: 11,
          color: COLORS.textFaint,
          marginBottom: 3,
        }}
      >
        {icon}
        {label}
      </div>
      <div
        style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: 17,
          fontWeight: 600,
          color,
        }}
      >
        {value}
      </div>
    </div>
  );
}

function AuditRow({ icon, text }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontSize: 12.5,
        color: COLORS.textMuted,
        padding: "5px 0",
      }}
    >
      {icon}
      {text}
    </div>
  );
}
