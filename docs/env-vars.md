# 환경변수 (.env)

프로젝트 루트에 `.env` 파일 생성. Django와 FastAPI가 공유한다.

```bash
# Supabase
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service role key>

# LLM API Keys
CLAUDE_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-proj-...
GOOGLE_API_KEY=...

# 암호화 (Fernet)
ENCRYPTION_KEY=<base64 Fernet key>

# 공통
PROJECT_DEBUG=True
SECRET_KEY=<django secret>

# 이메일 (Gmail SMTP)
EMAIL_HOST_PASSWORD=<gmail app password>

# SMS (Naver Cloud)
NAVER_ACCESS_KEY_ID=...
NAVER_SECRET_KEY=...
NAVER_SMS_SERVICE_ID=ncp:sms:kr:...
NAVER_SMS_FROM_NUMBER=010xxxxxxxx
```
