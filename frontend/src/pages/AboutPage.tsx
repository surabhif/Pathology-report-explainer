import { useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'

/** Lightweight markdown → HTML for the model card (headings, lists, bold, code). */
function renderSimpleMarkdown(md: string): string {
  const escaped = md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  const lines = escaped.split('\n')
  const out: string[] = []
  let inList = false

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('### ')) {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push(`<h3>${inline(trimmed.slice(4))}</h3>`)
    } else if (trimmed.startsWith('## ')) {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push(`<h2>${inline(trimmed.slice(3))}</h2>`)
    } else if (trimmed.startsWith('# ')) {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push(`<h1>${inline(trimmed.slice(2))}</h1>`)
    } else if (trimmed.startsWith('- ')) {
      if (!inList) {
        out.push('<ul>')
        inList = true
      }
      out.push(`<li>${inline(trimmed.slice(2))}</li>`)
    } else if (!trimmed) {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push('')
    } else {
      if (inList) {
        out.push('</ul>')
        inList = false
      }
      out.push(`<p>${inline(trimmed)}</p>`)
    }
  }
  if (inList) out.push('</ul>')
  return out.join('\n')
}

function inline(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
}

const FALLBACK_SECTIONS = `
# PathExplain model card

## Problem
Pathology reports are dense and written for clinicians. Patients and non-specialists
struggle to understand diagnosis, staging, and biomarkers.

## Data citation
Demo reports are synthetic / de-identified style text inspired by TCGA pathology
language (BRCA, COAD, LUAD). Do not treat barcodes as real patient identifiers.

## Method
1. Extract a structured fact sheet with quote offsets.
2. Generate plain-language sentences grounded in those facts.
3. Score reading level and run automatic evaluation checks.

## Evaluation
Field accuracy vs gold labels, number grounding, unsupported-sentence checks,
TCGA metadata agreement, clinician Likert scores, and reading-level targets (6–8).

## Limitations
Heuristic / LLM outputs can miss context, invent unsupported phrasing, or
oversimplify. Coverage is limited to a small fact schema and three cancer types.

## Disclaimer
**Research demo, not for clinical use.** Always defer to the original report and care team.
`.trim()

export function AboutPage() {
  const [title, setTitle] = useState('About PathExplain')
  const [body, setBody] = useState(FALLBACK_SECTIONS)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .getAbout()
      .then((res) => {
        setTitle(res.title || 'About PathExplain')
        setBody(res.body || FALLBACK_SECTIONS)
      })
      .catch((e: unknown) => {
        setError(e instanceof ApiError ? e.detail : 'Could not load about content')
      })
  }, [])

  return (
    <article className="page-enter panel markdown-body">
      <div className="page-intro">
        <h1>{title}</h1>
        <p className="muted">
          Model card: problem, data, method, evaluation, limitations, and disclaimer.
        </p>
      </div>
      {error && (
        <p className="muted">
          API about endpoint unavailable ({error}); showing local model card.
        </p>
      )}
      <div dangerouslySetInnerHTML={{ __html: renderSimpleMarkdown(body) }} />
      <section style={{ marginTop: '1.5rem' }}>
        <h2>Limitations (summary)</h2>
        <ul>
          <li>Not validated for clinical decision support.</li>
          <li>Small schema; many report nuances are omitted.</li>
          <li>Mock LLM mode is deterministic heuristics, not a production model.</li>
        </ul>
        <h2>Disclaimer</h2>
        <p>
          <strong>Research demo, not for clinical use.</strong> Do not paste identifiable patient
          information into this system.
        </p>
      </section>
    </article>
  )
}
