// 세그먼트 선택기 버튼 그룹 SSOT — 우측 패널 탭·차트 주기/기간·궤적 기간·스크리너 시장/단계·
// 로그인 모드 탭이 각자 복제하던 `options.map(<button aria-pressed …>)` 골격을 통합한다.
//
// 설계 원칙(행동 보존):
//   - **래퍼(div/role)·CSS 는 각 자리가 소유** — 이 컴포넌트는 버튼 배열만 반환한다(구조 불변).
//   - 시각 차이는 buttonClass(항상)·activeClass(활성 시 추가 — 미지정이면 aria-pressed 만) prop 주입.
//   - 접근성은 여기서 표준화: type="button"(폼 submit 방지) + aria-pressed(활성 표시).
//   - keyOf 로 옵션의 키 필드를 주입(기본 o.key — 궤적은 months 를 키로 쓴다).
//   - disabled 는 그룹 일괄(차트 로딩 중 전환 방지용) — 자리별 개별 비활성이 필요해지면 그때 확장.
//
// props: options([{key?, label, ...}]), value(현재 키), onChange(키 콜백),
//        buttonClass(필수 시각 클래스), activeClass?(활성 추가 클래스), disabled?, keyOf?
export default function SegmentedControl({
  options,
  value,
  onChange,
  buttonClass,
  activeClass = '',
  disabled = false,
  keyOf = (o) => o.key,
}) {
  return options.map((o) => {
    const k = keyOf(o)
    const isActive = value === k
    return (
      <button
        key={k}
        type="button"
        className={isActive && activeClass ? `${buttonClass} ${activeClass}` : buttonClass}
        aria-pressed={isActive}
        disabled={disabled}
        onClick={() => onChange(k)}
      >
        {o.label}
      </button>
    )
  })
}
