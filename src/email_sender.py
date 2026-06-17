"""
email_sender.py - メール送信ヘルパー
・ZOHO_SMTP_USER が設定されている場合 → Zoho SMTP（Phase1〜2仮運用）
・未設定の場合 → Brevo SDK（Phase3以降・復旧後）
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# Zoho SMTP設定
ZOHO_SMTP_HOST     = os.environ.get('ZOHO_SMTP_HOST', 'smtp.zoho.jp')
ZOHO_SMTP_PORT     = int(os.environ.get('ZOHO_SMTP_PORT', '587'))
ZOHO_SMTP_USER     = os.environ.get('ZOHO_SMTP_USER', '')
ZOHO_SMTP_PASSWORD = os.environ.get('ZOHO_SMTP_PASSWORD', '')

# Brevo設定（復旧後用・変数は残存）
BREVO_API_KEY    = os.environ.get('BREVO_API_KEY', '')
BREVO_FROM_EMAIL = os.environ.get('BREVO_FROM_EMAIL', '')
BREVO_FROM_NAME  = os.environ.get('BREVO_FROM_NAME', 'AI-PERSONA会議室')

# 送信者名（共通）
MAIL_FROM_NAME = os.environ.get('MAIL_FROM_NAME', 'AI-PERSONA会議室')
APP_BASE_URL   = os.environ.get('APP_BASE_URL', 'http://localhost:5000')


def _send_via_zoho(to_email: str, subject: str, body_html: str) -> bool:
    """Zoho SMTP経由で送信"""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f"{MAIL_FROM_NAME} <{ZOHO_SMTP_USER}>"
        msg['To']      = to_email
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))

        with smtplib.SMTP(ZOHO_SMTP_HOST, ZOHO_SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(ZOHO_SMTP_USER, ZOHO_SMTP_PASSWORD)
            server.sendmail(ZOHO_SMTP_USER, to_email, msg.as_string())
        print(f"[email] Zoho SMTP sent to {to_email}: {subject}")
        return True
    except smtplib.SMTPException as e:
        print(f"[email] SMTPException sending to {to_email}: {e}")
        return False
    except Exception as e:
        print(f"[email] _send_via_zoho failed to {to_email}: {e}")
        return False


def _send_via_brevo(to_email: str, subject: str, body_html: str) -> bool:
    """Brevo SDK経由で送信（復旧後用）"""
    try:
        import sib_api_v3_sdk
        from sib_api_v3_sdk.rest import ApiException
        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = BREVO_API_KEY
        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(configuration)
        )
        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            sender={"name": BREVO_FROM_NAME, "email": BREVO_FROM_EMAIL},
            to=[{"email": to_email}],
            subject=subject,
            html_content=body_html,
        )
        api_instance.send_transac_email(send_smtp_email)
        print(f"[email] Brevo sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"[email] _send_via_brevo failed to {to_email}: {e}")
        return False


def send_email(to_email: str, subject: str, body_html: str) -> bool:
    """
    メールを送信する。
    ZOHO_SMTP_USER が設定されていればZoho SMTPを使用。
    未設定の場合はBrevo SDKにフォールバック。
    送信失敗時はFalseを返す（例外を外に投げない）。
    """
    if ZOHO_SMTP_USER and ZOHO_SMTP_PASSWORD:
        return _send_via_zoho(to_email, subject, body_html)
    elif BREVO_API_KEY and BREVO_FROM_EMAIL:
        print(f"[email] Zoho not configured — falling back to Brevo")
        return _send_via_brevo(to_email, subject, body_html)
    else:
        print(f"[email] No mail provider configured — skipping send to {to_email}")
        return False


def send_email_change_confirmation(to_email: str, confirm_url: str) -> bool:
    """
    メールアドレス変更確認メールを送信する。
    件名：【AI-PERSONA会議室】メールアドレス変更の確認
    本文：confirm_urlをクリックして変更を確定するよう案内。
    有効期限24時間である旨を明記。
    """
    subject = "【AI-PERSONA会議室】メールアドレス変更の確認"
    body_html = f"""
<html>
<body style="font-family: sans-serif; color: #333; line-height: 1.6;">
  <h2 style="color: #7C3AED;">メールアドレス変更の確認</h2>
  <p>AI-PERSONA会議室をご利用いただきありがとうございます。</p>
  <p>メールアドレスの変更リクエストを受け付けました。<br>
  下記のボタンをクリックして、変更を確定してください。</p>
  <p style="margin: 24px 0;">
    <a href="{confirm_url}"
       style="background:#7C3AED;color:#fff;padding:12px 24px;border-radius:6px;
              text-decoration:none;font-weight:bold;display:inline-block;">
      メールアドレス変更を確定する
    </a>
  </p>
  <p style="color: #666; font-size: 13px;">
    ※ このリンクの有効期限は<strong>24時間</strong>です。<br>
    ※ 心当たりがない場合は、このメールを無視してください。<br>
    ※ リンクが機能しない場合は以下のURLをブラウザに貼り付けてください：
  </p>
  <p style="font-size: 12px; color: #888; word-break: break-all;">{confirm_url}</p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
  <p style="font-size: 12px; color: #aaa;">AI-PERSONA会議室</p>
</body>
</html>
"""
    return send_email(to_email, subject, body_html)
