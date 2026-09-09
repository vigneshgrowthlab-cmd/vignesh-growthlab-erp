import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Modal, Button } from '@/components/ui'
import { Upload, Download, AlertTriangle, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'

const MAX_UPLOAD_MB = 10

function downloadBlob(data, filename) {
  const url = URL.createObjectURL(new Blob([data]))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

/**
 * Reusable CSV bulk-import dialog.
 *
 * Props:
 *  - title            modal title
 *  - entityLabel      noun used in messages (e.g. "customers")
 *  - uploadFn(file)   -> axios promise resolving to { data: {success_count, skipped_count, error_count, errors, skipped} }
 *  - templateFn()     -> axios promise resolving to a CSV blob
 *  - templateName     download filename for the template
 *  - invalidateKey    react-query key to invalidate on success
 *  - columns          optional array of column-name strings to show as a hint
 *  - onClose
 */
export default function BulkImportModal({
  title, entityLabel, uploadFn, templateFn, templateName,
  invalidateKey, columns, onClose,
}) {
  const qc = useQueryClient()
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const onFileSelect = (f) => {
    if (!f) { setFile(null); setResult(null); return }
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) {
      toast.error(`File too large (${(f.size / 1024 / 1024).toFixed(1)} MB). Max ${MAX_UPLOAD_MB} MB.`)
      return
    }
    setFile(f)
    setResult(null)
  }

  const downloadTemplate = async () => {
    try {
      const res = await templateFn()
      downloadBlob(res.data, templateName)
    } catch {
      toast.error('Could not download template')
    }
  }

  const upload = async () => {
    if (!file) return
    setLoading(true)
    try {
      const { data } = await uploadFn(file)
      setResult(data)
      if (data.success_count > 0 && invalidateKey) qc.invalidateQueries({ queryKey: [invalidateKey] })
      const skipped = data.skipped_count || 0
      if (data.error_count === 0 && skipped === 0) {
        toast.success(`${data.success_count} ${entityLabel} imported`)
      } else if (data.success_count > 0) {
        toast(`${data.success_count} imported, ${skipped} skipped, ${data.error_count} failed`, { icon: '⚠️' })
      } else if (skipped > 0 && data.error_count === 0) {
        toast(`All ${skipped} rows skipped (already exist)`, { icon: 'ℹ️' })
      } else {
        toast.error(`All ${data.error_count} rows failed — see details`)
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Upload failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title={title} onClose={onClose}>
      <div className="space-y-4">
        <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg text-sm">
          <span className="text-gray-600">New here? Start from the template.</span>
          <Button variant="secondary" size="sm" onClick={downloadTemplate}>
            <Download size={14} /> Download template
          </Button>
        </div>

        {columns?.length > 0 && (
          <div className="text-xs text-gray-500">
            <span className="font-medium text-gray-600">Columns: </span>
            {columns.join(', ')}
          </div>
        )}

        <div className="p-4 border-2 border-dashed border-gray-200 rounded-lg text-center">
          <Upload size={24} className="mx-auto text-gray-300 mb-2" />
          <label className="cursor-pointer">
            <span className="text-sm text-primary underline">Choose CSV file</span>
            <input type="file" accept=".csv" className="hidden"
              onChange={e => onFileSelect(e.target.files[0])} />
          </label>
          {file && <div className="mt-2 text-xs text-gray-500">{file.name} ({(file.size / 1024).toFixed(1)} KB)</div>}
          <div className="mt-1 text-xs text-gray-400">UTF-8 CSV · max {MAX_UPLOAD_MB} MB</div>
        </div>

        {result && (
          <div className="space-y-3">
            {/* Summary counts */}
            <div className="flex flex-wrap gap-2 text-xs font-medium">
              <span className="px-2.5 py-1 rounded-full bg-green-100 text-green-700">
                {result.success_count} imported
              </span>
              {result.skipped_count > 0 && (
                <span className="px-2.5 py-1 rounded-full bg-amber-100 text-amber-800">
                  {result.skipped_count} skipped
                </span>
              )}
              {result.error_count > 0 && (
                <span className="px-2.5 py-1 rounded-full bg-red-100 text-red-700">
                  {result.error_count} failed
                </span>
              )}
            </div>

            {/* Skipped rows — highlighted with reason */}
            {result.skipped?.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 overflow-hidden">
                <div className="px-3 py-2 bg-amber-100 text-amber-800 text-xs font-semibold flex items-center gap-1.5">
                  <AlertTriangle size={13} /> Skipped rows (already exist — not imported)
                </div>
                <div className="max-h-44 overflow-y-auto divide-y divide-amber-100">
                  {result.skipped.map((s, i) => (
                    <div key={`s${i}`} className="px-3 py-1.5 text-xs text-amber-900 flex gap-2">
                      <span className="font-mono text-amber-500 shrink-0">Row {s.row}</span>
                      <span className="font-medium shrink-0">{s.data}</span>
                      <span className="text-amber-700">— {s.reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Failed rows */}
            {result.errors?.length > 0 && (
              <div className="rounded-lg border border-red-200 bg-red-50 overflow-hidden">
                <div className="px-3 py-2 bg-red-100 text-red-700 text-xs font-semibold flex items-center gap-1.5">
                  <XCircle size={13} /> Failed rows (fix and re-upload)
                </div>
                <div className="max-h-44 overflow-y-auto divide-y divide-red-100">
                  {result.errors.map((e, i) => (
                    <div key={`e${i}`} className="px-3 py-1.5 text-xs text-red-900 flex gap-2">
                      <span className="font-mono text-red-400 shrink-0">Row {e.row}</span>
                      {e.data && <span className="font-medium shrink-0">{e.data}</span>}
                      <span className="text-red-700">— {e.errors.join(', ')}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <div className="flex gap-3 justify-end">
          <Button variant="secondary" onClick={onClose}>Close</Button>
          <Button variant="primary" loading={loading} onClick={upload} disabled={!file || loading}>
            Upload &amp; Import
          </Button>
        </div>
      </div>
    </Modal>
  )
}
