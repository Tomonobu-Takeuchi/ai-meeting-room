"""
email_sender.py - Brevo（sib_api_v3_sdk）を使ったメール送信ヘルパー
"""
import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
BREVO_FROM_EMAIL = os.environ.get('BREVO_FROM_EMAIL', '')
BREVO_FROM_NAME = os.environ.get('BREVO_FROM_NAME', 'AI-PERSONA会議室')
APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5000')


def send_email(to_email: str, subject: str, body_html: str) -> bool:
    """
    Brevo経由でメールを送信する。
    送信失敗時はFalseを返す（例外を外に投げない）。
    """
    if not BREVO_API_KEY or not BREVO_FROM_EMAIL:
        print(f"[email] BREVO_API_KEY or BREVO_FROM_EMAIL not set — skipping send to {to_email}")
        return False
    try:
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
        return True
    except ApiException as e:
        print(f"[email] Brevo ApiException sending to {to_email}: {e}")
        return False
    except Exception as e:
        print(f"[email] send_email failed to {to_email}: {e}")
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
