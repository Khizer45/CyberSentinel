import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Badge } from "../../components/Badge";
import { Button } from "../../components/Button";
import { Card } from "../../components/Card";
import { SelectField, TextAreaField } from "../../components/FormFields";
import { EmptyState, ErrorCallout } from "../../components/States";
import { useToast } from "../../components/Toast";
import { addReview } from "../../services/analyses";
import { queryKeys } from "../../services/queryKeys";
import { DISPOSITIONS, type Disposition, type Review } from "../../types/api";
import { fieldErrors } from "../../utils/errors";
import { formatDateTime, humanize } from "../../utils/format";

export const DISPOSITION_HINTS: Record<Disposition, string> = {
  true_positive: "Confirmed malicious activity — closes the alert.",
  false_positive: "The model was wrong; the flow is legitimate — closes the alert.",
  benign: "Unusual but harmless (e.g. authorised scanning) — closes the alert.",
  duplicate: "Already handled under another alert — closes the alert.",
  needs_investigation: "More work needed — marks the alert as investigating.",
};

const TONES: Record<Disposition, "danger" | "success" | "neutral" | "warning"> = {
  true_positive: "danger",
  false_positive: "success",
  benign: "success",
  duplicate: "neutral",
  needs_investigation: "warning",
};

export function DispositionBadge({ disposition }: { disposition: Disposition }) {
  return <Badge tone={TONES[disposition]}>{humanize(disposition)}</Badge>;
}

interface ReviewPanelProps {
  predictionId: string;
  reviews: Review[];
  canReview: boolean;
  /** Query key of the detail view to refresh after a review. */
  detailKey: readonly unknown[];
}

/** Append-only review history plus the form to record a new disposition (reviews cannot be edited or deleted). */
export function ReviewPanel({ predictionId, reviews, canReview, detailKey }: ReviewPanelProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [disposition, setDisposition] = useState<Disposition | "">("");
  const [notes, setNotes] = useState("");
  const mutation = useMutation({
    mutationFn: () => addReview(predictionId, { disposition: disposition as Disposition, notes: notes.trim() || null }),
    onSuccess: async () => {
      toast.success("Review recorded.");
      setDisposition("");
      setNotes("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: detailKey }),
        queryClient.invalidateQueries({ queryKey: queryKeys.alertsAll }),
        queryClient.invalidateQueries({ queryKey: queryKeys.prediction(predictionId) }),
      ]);
    },
  });
  const errors = fieldErrors(mutation.error);
  const ordered = [...reviews].sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <Card title="Analyst review" subtitle="Reviews are append-only and recorded in the audit log.">
      <div className="stack">
        {canReview ? (
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (disposition) mutation.mutate();
            }}
          >
            <SelectField
              label="Disposition"
              placeholder="Select a disposition"
              value={disposition}
              onChange={(event) => setDisposition(event.target.value as Disposition)}
              options={DISPOSITIONS.map((value) => ({ value, label: humanize(value) }))}
              hint={disposition ? DISPOSITION_HINTS[disposition] : undefined}
              error={errors.disposition}
            />
            <TextAreaField
              label="Notes"
              value={notes}
              maxLength={2000}
              rows={4}
              placeholder="Evidence, ticket reference, next steps… (do not paste secrets or credentials)"
              onChange={(event) => setNotes(event.target.value)}
              error={errors.notes}
            />
            {!errors.disposition && !errors.notes ? <ErrorCallout error={mutation.error} /> : null}
            <div>
              <Button type="submit" variant="primary" loading={mutation.isPending} disabled={!disposition}>
                Record review
              </Button>
            </div>
          </form>
        ) : null}
        {ordered.length ? (
          <ul className="timeline" aria-label="Review history">
            {ordered.map((review) => (
              <li key={review.id}>
                <div className="row-between">
                  <DispositionBadge disposition={review.disposition} />
                  <span className="small subtle">{formatDateTime(review.created_at)}</span>
                </div>
                <p className="small" style={{ marginTop: 6 }}>
                  <strong>{review.reviewer.display_name}</strong>
                </p>
                {review.notes ? <p style={{ whiteSpace: "pre-wrap", marginTop: 4 }}>{review.notes}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No reviews yet" message={canReview ? "Record the first disposition above." : undefined} />
        )}
      </div>
    </Card>
  );
}
