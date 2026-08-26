export function resolveSubmitAction({ loading, stopping }) {
  if (stopping) return 'ignore'
  return loading ? 'stop' : 'send'
}

export function normalizeVisibleStreamStage(stage) {
  if (stage?.stage === 'completed') {
    return { stage: 'finalizing', label: '正在完成' }
  }
  return stage
}
