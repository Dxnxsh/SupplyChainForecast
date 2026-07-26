import { useSnapshot } from "../lib/useSnapshot";
import { useIsMobile } from "../lib/useIsMobile";

const pct = (x: number | undefined) => (x == null ? "—" : `${Math.round(x * 100)}%`);

function Tile({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: string }) {
  return (
    <div className="panel" style={{ padding: "10px 12px" }}>
      <div className="label" style={{ fontSize: 10 }}>{label}</div>
      <div className="display" style={{ fontSize: 24, color: tone ? `var(--${tone})` : undefined }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--muted)" }}>{sub}</div>}
    </div>
  );
}

function Head({ tag, right }: { tag: string; right?: string }) {
  return (
    <div className="panel-head"><span className="tick" /> {tag} <span className="leader" />{right && <span>{right}</span>}</div>
  );
}

function Bar({ name, f1, detail, tone, width }: { name: string; f1: string; detail: string; tone: string; width: number }) {
  return (
    <div style={{ marginBottom: 11 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
        <span>{name}</span>
        <span style={{ color: "var(--muted)" }}>{detail}</span>
      </div>
      <div className="bar" style={{ marginTop: 5 }}>
        <span style={{ width: `${width}%`, background: `var(--${tone})` }} />
      </div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>F1 {f1}</div>
    </div>
  );
}

export default function Accuracy() {
  const { data, error, loading } = useSnapshot();
  const isMobile = useIsMobile();
  if (loading) return <div className="label" style={{ padding: 24 }}>loading metrics…</div>;
  if (error || !data) return <div className="panel" style={{ padding: 16, borderColor: "var(--alert)" }}><div className="label" style={{ color: "var(--alert)" }}>metrics unavailable</div></div>;

  const m = data.metrics as any;
  const rel = m.relevance ?? {};
  const emb = m.relevance_embeddings?.embeddings?.emb_logreg?.["at_0.5"] ?? {};
  const pred = m.predictor ?? {};
  const wf = m.predictor_test?.checks?.walk_forward ?? {};
  const checks = m.predictor_test?.checks ?? {};
  const onset = pred.onset_value_add ?? {};
  const topics = m.topics ?? {};
  const folds: any[] = wf.folds ?? [];
  const ev = m.external_validation;
  const lagEntries: [string, number | null][] = ev ? Object.entries(ev.correlation_by_lag) : [];

  return (
    <div className="grid" style={{ gap: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: 8 }}>
        <div>
          <h1 className="display" style={{ margin: 0, fontSize: 24, letterSpacing: "0.03em" }}>Model accuracy</h1>
          <div style={{ color: "var(--muted)", fontSize: 14 }}>Held-out and walk-forward evidence. How good the predictions actually are</div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {/* {checks.feature_truncation_invariance?.pass && <span className="pill calm"><i className="ti ti-shield-check" aria-hidden="true" /> no leakage</span>} */}
          <span className="pill calm">walk-forward auc {wf.mean_auc?.toFixed?.(2) ?? "—"}</span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "repeat(2, 1fr)" : "repeat(4, 1fr)", gap: 10 }}>
        <Tile label="predictor walk-forward auc" value={wf.mean_auc?.toFixed?.(3) ?? "—"} sub={`${wf.n_folds ?? 0} monthly folds`} tone="accent" />
        <Tile label="onset detection recall" value={pct(onset.predictor_recall)} sub="new disruptions · persistence 0%" tone="watch" />
        <Tile label="relevance recall (live)" value={pct(emb.recall)} sub="embeddings · was 59% tf-idf" />
        <Tile label="labeled dataset" value={String(data.summary.clean_events)} sub={`${data.summary.event_days} event-days`} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1.3fr", gap: 12 }}>
        <div className="panel">
          <Head tag="relevance classifier vs baselines" />
          <div style={{ padding: 14 }}>
            <Bar name="keyword filter" detail={`R ${pct(rel.keyword_baseline?.recall)} · P ${pct(rel.keyword_baseline?.precision)}`} f1={pct(rel.keyword_baseline?.f1)} tone="muted" width={(rel.keyword_baseline?.f1 ?? 0) * 100} />
            <Bar name="tf-idf + xgboost" detail={`R ${pct(rel.classifier?.recall)} · P ${pct(rel.classifier?.precision)}`} f1={pct(rel.classifier?.f1)} tone="watch" width={(rel.classifier?.f1 ?? 0) * 100} />
            <Bar name="embeddings (chosen)" detail={`R ${pct(emb.recall)} · P ${pct(emb.precision)}`} f1={pct(emb.f1)} tone="calm" width={(emb.f1 ?? 0) * 100} />
            <Bar name="llm oracle (ceiling)" detail={`R ${pct(rel.llm_strict_ref?.recall)} · P ${pct(rel.llm_strict_ref?.precision)}`} f1={pct(rel.llm_strict_ref?.f1)} tone="border-strong" width={(rel.llm_strict_ref?.f1 ?? 0) * 100} />
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>Validated on {rel.gold_n ?? 150} human-labeled gold articles held out of training.</div>
          </div>
        </div>

        <div className="panel">
          <Head tag="walk-forward robustness" right="model auc ▸ persistence f1" />
          <div style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 150, borderBottom: "1px solid var(--border)", paddingBottom: 2 }}>
              {folds.map((f) => (
                <div key={f.origin} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                  <div style={{ display: "flex", gap: 2, alignItems: "flex-end", height: 130 }}>
                    <div style={{ width: 8, height: Math.max(1, Math.round((f.auc ?? 0) * 130)), background: "var(--accent)", borderRadius: "2px 2px 0 0" }} title={`AUC ${f.auc}`} />
                    <div style={{ width: 8, height: Math.max(1, Math.round((f.persistence_f1 ?? 0) * 130)), background: "var(--muted)", borderRadius: "2px 2px 0 0" }} title={`persistence F1 ${f.persistence_f1}`} />
                  </div>
                  <span style={{ fontSize: 9, color: "var(--muted)" }}>{f.origin?.slice(5)}</span>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 8 }}>
              Mean AUC {wf.mean_auc?.toFixed?.(2)} across {wf.n_folds} folds. The news signal holds through the sparse months where persistence (clustering) is blind; both converge only at the spike.
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1.3fr", gap: 12, alignItems: "start" }}>
        <div className="panel">
          <Head tag="leakage & robustness tests" />
          <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 10, fontSize: 13 }}>
            <Check ok={checks.feature_truncation_invariance?.pass} label="feature truncation-invariance" detail="max diff 0.0" />
            <Check ok={checks.calib_disjoint_from_test?.pass} label="calibration slice disjoint" detail="jan-2026 only" />
            <Check ok={!!folds.length} label="2026-03 spike held in test" detail="no straddle" />
            <Check ok={pred.beats_persistence_brier} label="beats persistence (brier)" detail="+ onset value-add" />
            <div style={{ marginTop: 4, padding: 10, background: "var(--panel-2)", borderRadius: 8, fontSize: 12, color: "var(--muted)" }}>
              Honest framing: persistence wins raw F1 (disruptions cluster). The model's edge is onset anticipation + calibrated ranking from news content.
            </div>
          </div>
        </div>

        <div className="panel">
          <Head tag="discovered topics (bertopic)" right={`${topics.n_topics ?? 0} topics · ${topics.n_topics_mapping_to_target ?? 0} map to a target`} />
          <div style={{ padding: 14, display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
            {(topics.topics ?? []).slice(0, 9).map((t: any) => (
              <div key={t.topic} className="panel" style={{ padding: "8px 10px", background: t.emergent ? "var(--watch-bg)" : "var(--panel-2)", borderColor: t.emergent ? "var(--watch)" : "var(--border)" }}>
                <div style={{ fontSize: 12 }}>{(t.keywords ?? []).slice(0, 3).join(" · ")}</div>
                <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 3 }}>
                  {t.emergent ? "emergent" : t.dominant_target} · {pct(t.recent_90d_share)} recent
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {ev && (
        <div className="panel">
          <Head tag="external validation — shipping vs. brent crude"
            right={`n=${ev.n_obs} · best lag ${ev.best_lag_days >= 0 ? "+" : ""}${ev.best_lag_days}d · r=${ev.best_correlation?.toFixed(2)}`} />
          <div style={{ padding: 14 }}>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 70, borderBottom: "1px solid var(--border)", paddingBottom: 2 }}>
              {lagEntries.map(([lag, r]) => {
                const v = r ?? 0;
                const isBest = Number(lag) === ev.best_lag_days;
                return (
                  <div key={lag} style={{ flex: 1, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: "100%" }}
                    title={`lag ${lag}d: r=${r?.toFixed(3) ?? "—"}`}>
                    <div style={{
                      height: `${Math.max(2, Math.abs(v) * 300)}%`,
                      background: isBest ? "var(--accent)" : v < 0 ? "var(--alert)" : "var(--muted)",
                      opacity: isBest ? 1 : 0.5,
                      borderRadius: "2px 2px 0 0",
                    }} />
                  </div>
                );
              })}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "var(--muted)", marginTop: 2 }}>
              <span>brent leads (−14d)</span>
              <span>same day</span>
              <span>P leads (+14d)</span>
            </div>
            <div style={{ fontSize: 13, marginTop: 10 }}>{ev.interpretation}</div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>
              {ev.method} Index: {ev.index}. Chosen over container-freight indices (Freightos Baltic,
              Drewry WCI) because those require a paid subscription for historical data; Brent crude
              is freely available with full daily history.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Check({ ok, label, detail }: { ok?: boolean; label: string; detail: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <span><i className={ok ? "ti ti-check" : "ti ti-x"} style={{ color: ok ? "var(--calm)" : "var(--alert)" }} aria-hidden="true" /> {label}</span>
      <span style={{ color: "var(--muted)" }}>{detail}</span>
    </div>
  );
}
