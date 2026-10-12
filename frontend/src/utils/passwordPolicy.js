// 비밀번호 정책(가입·초대 가입·비밀번호 변경 공통): 8자 이상 + 영문·숫자·특수문자를 모두 포함.
// 서버(backend/app/routers/auth.py validate_password_policy)와 같은 규칙이다.
export const isPasswordPolicyOk = (pw) =>
  pw.length >= 8 && /[A-Za-z]/.test(pw) && /\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)
