// Visual language for indicator judgement codes (manual §9.25).
export type JudgementKind = 'ok' | 'over' | 'under' | 'feed' | 'reject' | 'other'

export const JUDGEMENT_KIND: Record<string, JudgementKind> = {
  OK: 'ok',
  HI: 'over',
  HH: 'over',
  LO: 'under',
  LL: 'under',
  TD: 'feed',
  US: 'feed',
  MD: 'reject',
  E1: 'reject',
  E2: 'reject',
}

export const KIND_VAR: Record<JudgementKind, string> = {
  ok: 'var(--ok)',
  over: 'var(--over)',
  under: 'var(--under)',
  feed: 'var(--feed)',
  reject: 'var(--reject)',
  other: 'var(--muted-foreground)',
}

export const kindOf = (code: string | null | undefined): JudgementKind =>
  (code && JUDGEMENT_KIND[code]) || 'other'

export const colorOf = (code: string | null | undefined) => KIND_VAR[kindOf(code)]
