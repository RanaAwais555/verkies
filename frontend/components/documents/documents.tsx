"use client";

import { Download, FileText, Trash2, Upload } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { Badge, Button, Empty, ErrorNote, Field, IconButton, inputClass, Panel, Skeleton } from "@/components/ui";
import { api, withQuery } from "@/lib/client";
import { formatDate } from "@/lib/format";
import { useAction, useApi, useCanChange } from "@/lib/hooks";
import type { Deal, DocumentKind, Project, VrosDocument } from "@/lib/types";

export const DOCUMENT_KINDS: { key: DocumentKind; label: string }[] = [
  { key: "proposal", label: "Proposal" },
  { key: "requirements", label: "Requirements" },
  { key: "brief", label: "Brief" },
  { key: "contract", label: "Contract" },
  { key: "sow", label: "Statement of work" },
  { key: "meeting_notes", label: "Meeting notes" },
  { key: "screenshot", label: "Screenshot" },
  { key: "project_document", label: "Project document" },
  { key: "other", label: "Other" },
];

// What the API accepts (backend/app/documents/files.py); checked there from the file's own bytes.
const ACCEPT = ".pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.webp,.txt,.md,.csv";
const MAX_BYTES = 10 * 1024 * 1024;

function size(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function DocumentRow({ doc, showAccount }: { doc: VrosDocument; showAccount?: boolean }) {
  const { busy, error, run } = useAction();
  const [confirming, setConfirming] = useState(false);
  const writable = useCanChange();
  return (
    <li className="flex flex-wrap items-start gap-3 py-3 first:pt-0 last:pb-0" data-testid="document">
      <span aria-hidden className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-sunken text-fg-3">
        <FileText className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-fg">{doc.title}</span>
          <Badge>{doc.kind_label}</Badge>
        </span>
        <span className="block break-all text-xs text-fg-3">
          {doc.filename} · {size(doc.size_bytes)} · {formatDate(doc.created_at)}
          {doc.uploaded_by && ` · ${doc.uploaded_by}`}
          {showAccount && doc.account_name && ` · ${doc.account_name}`}
        </span>
        <ErrorNote error={error} />
      </span>
      <span className="flex items-center gap-1">
        <a
          href={`/api/v1/documents/${doc.id}/download`}
          download={doc.filename}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium text-accent-text hover:bg-surface-2"
        >
          <Download aria-hidden className="h-4 w-4" />
          Download
        </a>
        {confirming ? (
          <>
            <Button variant="danger" className="h-8 px-2.5 text-xs" busy={busy} onClick={() => run(() => api(`/documents/${doc.id}`, { method: "DELETE" }))}>
              Remove
            </Button>
            <Button variant="ghost" className="h-8 px-2.5 text-xs" onClick={() => setConfirming(false)}>
              Keep
            </Button>
          </>
        ) : (
          writable && (
            <IconButton label={`Remove ${doc.title}`} onClick={() => setConfirming(true)}>
              <Trash2 className="h-4 w-4" />
            </IconButton>
          )
        )}
      </span>
    </li>
  );
}

/** Upload a file to an account, optionally for one of its deals or projects. */
function UploadForm({
  accountId,
  projectId,
  dealId,
  projects,
  deals,
  onDone,
  onCancel,
}: {
  accountId: string;
  projectId?: string;
  dealId?: string;
  projects?: Project[];
  deals?: Deal[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const { busy, error, setError, run } = useAction();
  const fileRef = useRef<HTMLInputElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError(new Error(`That file is ${size(file.size)}. Files can be up to ${size(MAX_BYTES)}.`));
      return;
    }
    const path = withQuery(`/accounts/${accountId}/documents`, {
      filename: file.name,
      kind: String(data.get("kind") ?? "other"),
      title: String(data.get("title") ?? "").trim(),
      project_id: projectId ?? String(data.get("project") ?? ""),
      deal_id: dealId ?? String(data.get("deal") ?? ""),
    });
    if (await run(() => api(path, { method: "POST", body: file }).then(() => true))) onDone();
  }

  return (
    <form onSubmit={submit} className="animate-rise space-y-3 rounded-xl border border-border bg-surface-2 p-3.5" data-testid="upload-form">
      <Field label="File to upload" hint="PDF, Word, Excel, PowerPoint, images, text or CSV, up to 10 MB.">
        <input ref={fileRef} name="file" type="file" required accept={ACCEPT} className={inputClass} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="What it is">
          <select name="kind" defaultValue={projectId ? "project_document" : "other"} className={inputClass}>
            {DOCUMENT_KINDS.map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Title (optional)" hint="The file name if left empty.">
          <input name="title" maxLength={200} className={inputClass} />
        </Field>
        {!projectId && projects && projects.length > 0 && (
          <Field label="Project (optional)">
            <select name="project" defaultValue="" className={inputClass}>
              <option value="">None</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
        )}
        {!dealId && deals && deals.length > 0 && (
          <Field label="Deal (optional)">
            <select name="deal" defaultValue="" className={inputClass}>
              <option value="">None</option>
              {deals.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>
      <ErrorNote error={error} />
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" busy={busy} icon={<Upload className="h-4 w-4" />}>
          Upload
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

/** Documents for an account, a project or a deal, with an upload form. */
export function DocumentsPanel({
  accountId,
  projectId,
  dealId,
  withLinks,
  description,
}: {
  accountId: string;
  projectId?: string;
  dealId?: string;
  /** On the account: offer its projects and deals to link the upload to. */
  withLinks?: boolean;
  description?: string;
}) {
  const query = withQuery("/documents", { account_id: projectId || dealId ? undefined : accountId, project_id: projectId, deal_id: dealId });
  const { data, error } = useApi<VrosDocument[]>(query);
  const { data: projects } = useApi<Project[]>(withLinks ? `/projects?account_id=${accountId}&status=all` : null);
  const { data: deals } = useApi<Deal[]>(withLinks ? `/deals?account_id=${accountId}&status=all` : null);
  const [adding, setAdding] = useState(false);
  const writable = useCanChange();
  return (
    <Panel
      title="Documents"
      description={description ?? "Proposals, contracts, briefs, notes and files. Downloads only; nothing is opened inside VROS."}
      testId="documents"
      actions={
        writable &&
        !adding && (
          <Button onClick={() => setAdding(true)} icon={<Upload className="h-4 w-4" />}>
            Upload
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {adding && (
          <UploadForm
            accountId={accountId}
            projectId={projectId}
            dealId={dealId}
            projects={projects}
            deals={deals}
            onCancel={() => setAdding(false)}
            onDone={() => setAdding(false)}
          />
        )}
        {error ? (
          <ErrorNote error={error} />
        ) : !data ? (
          <Skeleton rows={2} />
        ) : data.length === 0 ? (
          <Empty icon={<FileText className="h-4 w-4" />}>No documents yet.</Empty>
        ) : (
          <ul className="divide-y divide-grid">
            {data.map((d) => (
              <DocumentRow key={d.id} doc={d} />
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}
