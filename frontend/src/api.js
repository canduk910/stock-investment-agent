// 백엔드(FastAPI) 호출 헬퍼. 엔드포인트 계약은 api/main.py 와 일치해야 한다.
export async function fetchMacroIndicators() {
  const res = await fetch('/api/macro/indicators')
  if (!res.ok) throw new Error(`API ${res.status}`)
  return res.json()
}
