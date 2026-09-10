import type { Preview } from "./api";

export function ImportPanel({
  preview,
  busy,
  disabled,
  activeCount,
  onUpload,
  onActivate,
}: {
  preview: Preview | null;
  busy: boolean;
  disabled: boolean;
  activeCount: number;
  onUpload: (file: File) => void;
  onActivate: () => void;
}) {
  return (
    <section className="card space-y-4">
      <div className="flex justify-between items-start gap-4">
        <div>
          <p className="eyebrow">02 / YAHOO IMPORT</p>
          <h2>
            {preview
              ? "Review staged import"
              : activeCount
                ? "Yahoo pool active"
                : "Bring in your player pool"}
          </h2>
          <p className="muted">Uploading leaves your active pool and selections unchanged.</p>
        </div>
        <label className="upload">
          {busy ? "Working…" : "Upload Yahoo CSV"}
          <input
            aria-label="Upload Yahoo CSV"
            type="file"
            accept=".csv,text/csv"
            disabled={disabled}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onUpload(file);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      {preview ? (
        <>
          {preview.errors.map((error) => (
            <p role="alert" className="error" key={error}>
              {error}
            </p>
          ))}
          <div className="flex gap-7">
            <div className="stat">
              {preview.summary.records ?? 0}
              <small>records</small>
            </div>
            <div className="stat">
              {preview.summary.games ?? 0}
              <small>games</small>
            </div>
            <div className="stat">
              {preview.summary.eligible_ids ?? 0}
              <small>eligible IDs</small>
            </div>
            <div className="stat text-amber-800">
              {preview.summary.quarantined_rows ?? 0}
              <small>quarantined rows</small>
            </div>
          </div>
          <p className="muted">
            Imported {new Date(preview.imported_at).toLocaleString()} · Provider update time:
            unknown
          </p>
          <p>
            {preview.changes.added.length} added · {preview.changes.removed.length} removed ·{" "}
            {preview.changes.changed.length} changed from active pool
          </p>
          <details>
            <summary>Inspect quarantined records ({preview.summary.quarantined_rows ?? 0})</summary>
            {preview.rows
              .filter((p) => p.issues.length)
              .map((p) => (
                <details className="conflict" key={p.row_id}>
                  <summary>
                    {p.name} · {p.yahoo_id} · line {p.line}
                  </summary>
                  <p className="error">{p.issues.join(" · ")}</p>
                  <pre>{JSON.stringify(p.raw, null, 2)}</pre>
                </details>
              ))}
          </details>
          {!preview.setup_matches ? (
            <p className="error">Setup changed. Upload again to revalidate before activation.</p>
          ) : null}
          <button
            disabled={
              disabled ||
              !!preview.errors.length ||
              !preview.setup_matches ||
              !preview.summary.eligible_ids
            }
            onClick={onActivate}
          >
            Activate reviewed pool
          </button>
        </>
      ) : activeCount ? (
        <p className="muted">
          {activeCount} eligible entries. Upload a replacement to review changes.
        </p>
      ) : (
        <p className="empty">
          Choose the original Yahoo export. Conflicting records will remain inspectable.
        </p>
      )}
    </section>
  );
}
