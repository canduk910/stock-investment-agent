import { useState } from 'react'
import { addWatchlist, removeWatchlist, updateWatchlistTarget } from '../api.js'
import { addErrorMessage } from '../lib/watchlistLogic.js'

// 챗봇 자연어 편집(manage_watchlist) 확인 카드 — 실제 변경은 사용자가 [확인]을 눌러야 반영된다
// (confirm-before-write, IMP-08). LLM 은 "무엇을 할지 제안"만 하고 자동 실행하지 않는다(자동 매매 아님).
//
// props: args={action, ticker, stock_name, target_price?, sell_target_price?} — 챗봇 tool_call 인자.
//   valid — popupRouter 가 검증한 유효성(6자리 코드·유효 작업). false 면 안내만 하고 쓰기 버튼 없음.
//   onClose — 확인/취소/닫기 시 우측 패널을 원 상태로 되돌리는 콜백.
// 안전: 이 컴포넌트만이 실제 add/remove/updateTarget API 를 호출하며, 반드시 사용자의 명시적 [확인]
//   클릭을 거친다. LLM 응답이 직접 워치리스트를 바꾸는 경로는 없다(제안↔실행 분리).

// 숫자면 천단위 콤마, 아니면 원본 그대로(목표가 표시용).
const num = (v) => (Number.isFinite(Number(v)) ? Number(v).toLocaleString() : v)

export default function ManageWatchlistConfirm({ args, valid, onClose }) {
  const [state, setState] = useState('idle') // idle(질문) | saving(반영 중) | done(성공) | error(실패)
  const [msg, setMsg] = useState('') // 결과 메시지(성공 안내 또는 에러 사유)

  // 유효성 실패 — 잘못된 인자면 쓰기 없이 재입력 안내만(부정확한 편집 실행 방지).
  if (!valid) {
    return (
      <div className="popup__state">
        요청을 정확히 이해하지 못했어요. 6자리 종목코드와 작업(추가·제거·목표가 설정, 목표가는 0 이상)을
        확인해 다시 말씀해 주세요.
      </div>
    )
  }

  const { action, ticker, stock_name, target_price, sell_target_price } = args
  const name = stock_name || ticker // 종목명 없으면 코드로 대체 표시

  // set_target: 제공된 side 만 반영·표시(popupRouter 가 매수/매도 중 최소 1개 유효를 이미 보장).
  const hasBuy = target_price != null && Number.isFinite(Number(target_price)) // 매수 목표가 유효
  const hasSell = sell_target_price != null && Number.isFinite(Number(sell_target_price)) // 매도 목표가 유효
  const targetParts = [] // 확인 질문에 넣을 목표가 조각(제공된 side 만)
  if (hasBuy) targetParts.push(`매수 목표가 ${num(target_price)}원`)
  if (hasSell) targetParts.push(`매도 목표가 ${num(sell_target_price)}원`)

  // 작업별 확인 질문 문구 — add/remove/set_target 세 갈래.
  const question =
    action === 'add'
      ? `‘${name}(${ticker})’을(를) 관심종목에 추가할까요?`
      : action === 'remove'
        ? `‘${name}(${ticker})’을(를) 관심종목에서 제거할까요?`
        : `‘${name}(${ticker})’의 ${targetParts.join(' · ')}(으)로 설정할까요?`

  // [확인] 클릭 시에만 실제 쓰기 — 작업별로 add/remove/부분 target 갱신을 분기 호출.
  async function confirm() {
    setState('saving')
    try {
      if (action === 'add') await addWatchlist({ ticker, stockName: stock_name })
      else if (action === 'remove') await removeWatchlist(ticker)
      else {
        // set_target: 제공된 side 만 담아 부분 PATCH(다른 side 목표가는 서버에서 불변).
        const targets = {}
        if (hasBuy) targets.target_price = Number(target_price)
        if (hasSell) targets.sell_target_price = Number(sell_target_price)
        await updateWatchlistTarget(ticker, targets)
      }
      setState('done')
      setMsg('반영했습니다. 관심종목 화면에서 확인할 수 있어요.')
    } catch (e) {
      // 실패 사유는 상태 코드로 매핑(예 409=상한 초과) — addErrorMessage SSOT.
      setState('error')
      setMsg(addErrorMessage(e?.status))
    }
  }

  // 완료/실패 시 — 결과 메시지 + 닫기만(다시 쓰기 없음).
  if (state === 'done' || state === 'error') {
    return (
      <div className="wl-confirm">
        <p className={`wl-confirm__result ${state === 'error' ? 'is-error' : ''}`}>{msg}</p>
        <div className="wl-confirm__actions">
          <button type="button" className="refresh" onClick={onClose}>
            닫기
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="wl-confirm">
      <p className="wl-confirm__q">{question}</p>
      <p className="wl-confirm__note">
        AI 는 제안만 합니다 — [확인]을 눌러야 반영됩니다(자동 매매·자동 실행 아님).
      </p>
      <div className="wl-confirm__actions">
        <button
          type="button"
          className="wl-confirm__ok"
          onClick={confirm}
          disabled={state === 'saving'}
        >
          {state === 'saving' ? '반영 중…' : '확인'}
        </button>
        <button
          type="button"
          className="wl-confirm__cancel"
          onClick={onClose}
          disabled={state === 'saving'}
        >
          취소
        </button>
      </div>
    </div>
  )
}
