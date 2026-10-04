import type { GlossaryTerm } from '../types'

export function GlossaryPanel({ terms }: { terms: GlossaryTerm[] }) {
  if (!terms.length) {
    return <p className="muted">No glossary terms matched this report.</p>
  }
  return (
    <div className="glossary">
      <dl>
        {terms.map((t) => (
          <div key={t.term}>
            <dt>{t.term}</dt>
            <dd>{t.definition}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
