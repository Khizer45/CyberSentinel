import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { LabelBadge, RiskBadge, StatusBadge } from "../components/Badge";
import { Card } from "../components/Card";
import { KeyValueList } from "../components/DataDisplay";
import { PageHeader } from "../components/PageHeader";
import { ScoreSemantics } from "../components/ScoreSemantics";
import { Callout, ErrorState, LoadingState } from "../components/States";
import { ExplanationView } from "../features/alerts/ExplanationView";
import { ReviewPanel } from "../features/alerts/ReviewPanel";
import { useAuth } from "../features/auth/AuthContext";
import { canAnalyze } from "../features/auth/roles";
import { getAlert } from "../services/alerts";
import { getPrediction } from "../services/analyses";
import { queryKeys } from "../services/queryKeys";
import type { PredictionDetail } from "../types/api";
import { formatDateTime, formatNumber, formatRisk, formatScore, humanize } from "../utils/format";

/** Alert details (``/alerts/:alertId``) and prediction details (``/predictions/:predictionId``) share one view. */
export function AlertDetailsPage({ kind }: { kind: "alert" | "prediction" }) {
  const params = useParams();
  const id = (kind === "alert" ? params.alertId : params.predictionId) ?? "";
  const { user } = useAuth();
  const detailKey = kind === "alert" ? (["alerts", "detail", id] as const) : queryKeys.prediction(id);
  const detail = useQuery({ queryKey: detailKey, queryFn: () => (kind === "alert" ? getAlert(id) : getPrediction(id)) });
  const back = kind === "alert" ? { to: "/alerts", label: "Alerts" } : { to: detail.data ? `/analyses/${detail.data.analysis_job_id}` : "/analyses", label: "Analysis results" };

  if (detail.isPending) return <LoadingState label="Loading details…" />;
  if (detail.isError) {
    return (
      <>
        <PageHeader title={kind === "alert" ? "Alert" : "Prediction"} back={back} />
        <Card>
          <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
        </Card>
      </>
    );
  }
  const data = detail.data;
  return (
    <>
      <PageHeader
        title={`${data.is_alert ? "Alert" : "Prediction"} · record ${formatNumber(data.record_index)}`}
        description={`${data.dataset.name} · analysed ${formatDateTime(data.created_at)}`}
        back={back}
        actions={
          <>
            <RiskBadge band={data.risk_band} score={data.risk_score} />
            {data.alert_status ? <StatusBadge status={data.alert_status} /> : null}
          </>
        }
      />
      <ScoreCards data={data} />
      <div className="grid-2" style={{ alignItems: "start" }}>
        <div className="stack">
          <Card title="Explanation">
            {data.explanation ? (
              <ExplanationView explanation={data.explanation} />
            ) : (
              <Callout tone="info">
                No explanation was stored for this prediction. Explanations are generated during analysis for the records selected by the server's
                EXPLAIN_SCOPE setting (by default alerts and records needing review).
              </Callout>
            )}
          </Card>
          <ScoreSemantics calibrated={data.scores_calibrated} />
        </div>
        <div className="stack">
          <ReviewPanel predictionId={data.id} reviews={data.reviews} canReview={canAnalyze(user)} detailKey={detailKey} />
          <ContextCard data={data} />
        </div>
      </div>
    </>
  );
}

function ScoreCards({ data }: { data: PredictionDetail }) {
  return (
    <Card>
      <div className="score-grid">
        <div className="score-tile">
          <div className="label">Policy risk score</div>
          <div className="value">{formatRisk(data.risk_score)}</div>
          <div className="small subtle">{humanize(data.risk_band)} band · not a probability</div>
        </div>
        <div className="score-tile">
          <div className="label">Predicted label</div>
          <div className="value" style={{ fontSize: "1rem", paddingTop: 4 }}>
            <LabelBadge label={data.predicted_label} />
          </div>
          {data.true_label ? <div className="small subtle">Dataset label: {data.true_label}</div> : null}
        </div>
        <div className="score-tile">
          <div className="label">Probability</div>
          <div className="value">{data.scores_calibrated && data.probability !== null ? formatScore(data.probability) : "n/a"}</div>
          <div className="small subtle">{data.scores_calibrated ? "Calibrated model" : "Model not calibrated"}</div>
        </div>
        <div className="score-tile">
          <div className="label">Classifier score</div>
          <div className="value">{formatScore(data.classifier_score)}</div>
          <div className="small subtle">Uncalibrated · 1 − benign score</div>
        </div>
        <div className="score-tile">
          <div className="label">Anomaly score</div>
          <div className="value">{formatScore(data.anomaly_score)}</div>
          <div className="small subtle">{data.is_anomaly === null ? "No anomaly detector" : data.is_anomaly ? "Above threshold" : "Below threshold"}</div>
        </div>
      </div>
    </Card>
  );
}

function ContextCard({ data }: { data: PredictionDetail }) {
  const context = Object.entries(data.flow_context ?? {});
  return (
    <Card title="Context">
      <div className="stack">
        <KeyValueList
          items={[
            { label: "Dataset", value: `${data.dataset.name} (${data.dataset.schema_version ?? "?"})` },
            { label: "Analysis job", value: <Link to={`/analyses/${data.analysis_job_id}`}>{data.job.id.slice(0, 8)} · {humanize(data.job.status)}</Link> },
            { label: "Mode", value: humanize(data.job.requested_mode) },
            { label: "Model", value: `${data.model_version.model_name} ${data.model_version.version}` },
            { label: "Risk policy", value: data.job.risk_policy_version },
            { label: "Record index", value: formatNumber(data.record_index) },
          ]}
        />
        {context.length ? (
          <>
            <h3>Flow context</h3>
            <KeyValueList items={context.map(([key, value]) => ({ label: humanize(key), value: value === null ? "—" : String(value) }))} />
            <p className="small subtle">IP addresses are pseudonymised (keyed hash) before storage.</p>
          </>
        ) : null}
      </div>
    </Card>
  );
}
