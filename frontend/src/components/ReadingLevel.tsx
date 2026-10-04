interface Props {
  original: number | null | undefined
  explanation: number | null | undefined
}

/** Flesch–Kincaid grade display with the MVP target note (6th–8th grade). */
export function ReadingLevel({ original, explanation }: Props) {
  const fmt = (n: number | null | undefined) =>
    n == null || Number.isNaN(n) ? '—' : n.toFixed(1)

  return (
    <div className="reading-level">
      <div>
        Original report grade: <strong>{fmt(original)}</strong>
      </div>
      <div>
        Explanation grade: <strong>{fmt(explanation)}</strong>
      </div>
      <div className="muted">Target: roughly 6th–8th grade reading level</div>
    </div>
  )
}
