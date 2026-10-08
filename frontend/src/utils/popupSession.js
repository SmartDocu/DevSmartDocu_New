// 로그인 후 팝업(mainlogin='L')은 같은 로그인 세션 안에서 닫으면 /launcher로 돌아와도 다시 뜨지 않게
// sessionStorage에 기억한다. 로그인할 때마다 clearClosedPopups()로 비워 다음 로그인엔 다시 보이게 한다.
const CLOSED_KEY_PREFIX = 'popup_closed_'

export function isClosedInSession(popupid) {
  try { return sessionStorage.getItem(`${CLOSED_KEY_PREFIX}${popupid}`) === '1' } catch { return false }
}

export function saveClosedInSession(popupid) {
  try { sessionStorage.setItem(`${CLOSED_KEY_PREFIX}${popupid}`, '1') } catch { /* 무시 */ }
}

export function clearClosedPopups() {
  try {
    Object.keys(sessionStorage).filter((k) => k.startsWith(CLOSED_KEY_PREFIX)).forEach((k) => sessionStorage.removeItem(k))
  } catch { /* 무시 */ }
}
