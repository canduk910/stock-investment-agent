import { useState } from 'react'
import { addWatchlist, removeWatchlist, updateWatchlistTarget } from '../api.js'
import { addErrorMessage } from '../lib/watchlistLogic.js'

// 챗봇 자연어 편집(manage_watchlist) 확인 카드 — 실제 변경은 사용자가 [확인]을 눌러야 반영된다
// (confirm-before-write, IMP-08). LLM 은 "무엇을 할지 제안"만 하고 자동 실행하지 않는다(자동 매매 아님).
const num = (v) => (Number.isFinite(Number(v)) ? Number(v).toLocaleString() : v)

export default function ManageWatchlistConfirm({ args, valid, onClose }) {
  const [state, setState] = useState('idle') // idle | saving | done | error
  const [msg, setMsg] = useState('')

  if (!valid) {
    return (
      <div className="popup__state">
        요청을 정확히 이해하지 못했어요. 6자리 종목코드와 작업(추가·제거·목표가 설정, 목표가는 0 이상)을
        확인해 다시 말씀해 주세요.
      </div>
    )
  }

  const { action, ticker, stock_name, target_price, sell_target_price } = args
  const name = stock_name || ticker

  // set_target: 제공된 side 만 반영·표시(popupRouter 가 매수/매도 중 최소 1개 유효를 이미 보장).
  const hasBuy = target_price != null && Number.isFinite(Number(target_price))
  const hasSell = sell_target_price != null && Number.isFinite(Number(sell_target_price))
  const targetParts = []
  if (hasBuy) targetParts.push(`매수 목표가 ${num(target_price)}원`)
  if (hasSell) targetParts.push(`매도 목표가 ${num(sell_target_price)}원`)

  const question =
    action === 'add'
      ? `‘${name}(${ticker})’을(를) 관심종목에 추가할까요?`
      : action === 'remove'
        ? `‘${name}(${ticker})’을(를) 관심종목에서 제거할까요?`
        : `‘${name}(${ticker})’의 ${targetParts.join(' · ')}(으)로 설정할까요?`

  async function confirm() {
    setState('saving')
    try {
      if (action === 'add') await addWatchlist({ ticker, stockName: stock_name })
      else if (action === 'remove') await removeWatchlist(ticker)
      else {
        const targets = {}
        if (hasBuy) targets.target_price = Number(target_price)
        if (hasSell) targets.sell_target_price = Number(sell_target_price)
        await updateWatchlistTarget(ticker, targets)
      }
      setState('done')
      setMsg('반영했습니다. 관심종목 화면에서 확인할 수 있어요.')
    } catch (e) {
      setState('error')
      setMsg(addErrorMessage(e?.status))
    }
  }

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
