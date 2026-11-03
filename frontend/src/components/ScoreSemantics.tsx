import { Callout } from "./States";

/** Explains what each score means so that analysts do not over-interpret model outputs (SRS, SAD 4.x). */
export function ScoreSemantics({ calibrated }: { calibrated?: boolean }) {
  return (
    <Callout tone="info" title="How to read these scores">
      <ul>
        <li>
          <strong>Probability</strong> is shown only for models whose probabilities were calibrated during training
          {calibrated === false ? "; this model is not calibrated, so no probability is shown." : "."}
        </li>
        <li>
          <strong>Classifier score</strong> (1 − score of the benign class) is an uncalibrated model score, useful for ranking flows but
          not a likelihood.
        </li>
        <li>
          <strong>Anomaly score</strong> is higher for flows that look unusual compared with the benign training traffic. Unusual does
          not necessarily mean malicious.
        </li>
        <li>
          <strong>Risk score</strong> (0–100) and band come from the versioned risk policy. It is a prioritisation score, not a
          probability.
        </li>
      </ul>
      <p className="small muted" style={{ marginTop: 6 }}>
        Model outputs are decision support and require analyst review; they are not proof of compromise.
      </p>
    </Callout>
  );
}
