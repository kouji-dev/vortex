/** POST multipart FormData with XMLHttpRequest so `upload.onprogress` can report bytes sent (fetch has no upload progress). */

export type KnowledgeBaseDocumentUploadResult = {
  document_id?: number | null
  status: string
  filename?: string
  ingest_error?: string
}

export type KnowledgeBaseDocumentUploadResponse = {
  results: KnowledgeBaseDocumentUploadResult[]
}

function parseKbDocumentUploadResponse(parsed: unknown): KnowledgeBaseDocumentUploadResponse {
  if (
    parsed &&
    typeof parsed === 'object' &&
    'results' in parsed &&
    Array.isArray((parsed as { results: unknown }).results)
  ) {
    return parsed as KnowledgeBaseDocumentUploadResponse
  }
  if (parsed && typeof parsed === 'object' && 'document_id' in parsed) {
    const p = parsed as KnowledgeBaseDocumentUploadResult & { document_id: number }
    return {
      results: [
        {
          document_id: p.document_id,
          status: p.status,
          filename: p.filename,
          ingest_error: p.ingest_error,
        },
      ],
    }
  }
  throw new Error('Unexpected upload response shape')
}

function headersInitToRecord(headers: HeadersInit): Record<string, string> {
  const out: Record<string, string> = {}
  if (headers instanceof Headers) {
    headers.forEach((value, key) => {
      out[key] = value
    })
    return out
  }
  if (Array.isArray(headers)) {
    for (const [k, v] of headers) {
      out[k] = v
    }
    return out
  }
  for (const [k, v] of Object.entries(headers)) {
    if (typeof v === 'string') out[k] = v
  }
  return out
}

export function postFormDataWithUploadProgress(
  url: string,
  formData: FormData,
  headers: HeadersInit,
  onProgress: (percent: number, lengthComputable: boolean) => void,
): Promise<KnowledgeBaseDocumentUploadResponse> {
  const headerRecord = headersInitToRecord(headers)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    for (const [key, value] of Object.entries(headerRecord)) {
      if (key.toLowerCase() === 'content-type') continue
      xhr.setRequestHeader(key, value)
    }

    xhr.upload.addEventListener('progress', (ev) => {
      if (ev.lengthComputable && ev.total > 0) {
        onProgress(Math.min(100, Math.round((ev.loaded / ev.total) * 100)), true)
      } else {
        onProgress(0, false)
      }
    })

    xhr.onload = () => {
      const raw = xhr.responseText
      let parsed: unknown
      try {
        parsed = raw ? JSON.parse(raw) : null
      } catch {
        reject(new Error(raw || `Upload failed (${xhr.status})`))
        return
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const detail =
          parsed &&
          typeof parsed === 'object' &&
          'detail' in parsed &&
          (parsed as { detail: unknown }).detail != null
            ? String((parsed as { detail: unknown }).detail)
            : null
        reject(new Error(detail || raw || `Upload failed (${xhr.status})`))
        return
      }
      resolve(parseKbDocumentUploadResponse(parsed))
    }
    xhr.onerror = () => reject(new Error('Network error'))
    xhr.onabort = () => reject(new Error('Upload cancelled'))
    xhr.send(formData)
  })
}
