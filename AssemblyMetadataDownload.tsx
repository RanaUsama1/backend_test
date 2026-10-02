import { useState } from 'react';
import { BACKEND_API_URL } from '../config';

export function AssemblyMetadataDownload({ accession }: { accession: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      if (!BACKEND_API_URL) throw new Error('Backend URL is not configured.');
      const base = BACKEND_API_URL.replace(/\/+$/, '');
      const response = await fetch(
        `${base}/api/assembly/${encodeURIComponent(accession)}/download`
      );
      if (!response.ok) {
        const details = await response.json().catch(() => null);
        throw new Error(details?.message ?? `Download failed (HTTP ${response.status}).`);
      }
      if (!response.headers.get('content-type')?.includes('application/zip')) {
        throw new Error('The backend did not return a metadata ZIP file.');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${accession}_metadata.zip`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Metadata download failed.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button type="button" disabled={busy} onClick={download}
        className="w-full bg-slate-800 text-white px-4 py-2 rounded-lg disabled:opacity-50">
        {busy ? 'Fetching source metadata…' : 'Download source metadata ZIP'}
      </button>
      {error && <p role="alert" className="mt-2 text-sm text-red-600">{error}</p>}
      <p className="mt-2 text-sm text-slate-500">
        Fetches a new snapshot. Extract the ZIP and open report.html to read it offline.
        Check manifest.json for source failures.
      </p>
    </div>
  );
}
