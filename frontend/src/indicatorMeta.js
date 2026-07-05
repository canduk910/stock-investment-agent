// 지표 키 → 표시 메타(라벨/단위/설명). 표시 전용이며, 값·판정은 백엔드가 담당한다.
// 백엔드 indicators 의 키와 정확히 일치해야 한다(경계 계약).
export const INDICATOR_META = {
  t10y2y: { label: '장단기 금리차', unit: '%p', hint: '10년−2년 국채' },
  hy_spread: { label: 'HY 신용스프레드', unit: '%', hint: '하이일드 위험' },
  vix: { label: 'VIX 변동성', unit: '', hint: '공포 지수' },
  dollar_index: { label: '달러지수', unit: '', hint: '광범위 무역가중' },
  fear_greed: { label: '공포탐욕지수', unit: '/100', hint: 'CNN' },
  gdp: { label: '미국 GDP', unit: 'B$', hint: '버핏지수 분모' },
}

// 카드 표시 순서.
export const INDICATOR_ORDER = [
  't10y2y',
  'hy_spread',
  'vix',
  'dollar_index',
  'fear_greed',
  'gdp',
]
