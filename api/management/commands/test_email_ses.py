import logging
from django.core.management.base import BaseCommand
from api.email_service import EmailService
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Test email sending via configured backend (SMTP or SES)'

    def add_arguments(self, parser):
        parser.add_argument('--to', type=str, required=True, help='Email address to send test email to')

    def handle(self, *args, **options):
        to_email = options['to']
        
        logger.info(f"Starting test email send to {to_email}")
        self.stdout.write(f"Sending test email to {to_email}...")
        self.stdout.write(f"Current EMAIL_BACKEND_TYPE: {getattr(settings, 'EMAIL_BACKEND_TYPE', 'not set')}")
        self.stdout.write(f"Current EMAIL_BACKEND: {getattr(settings, 'EMAIL_BACKEND', 'not set')}")
        
        html_content = """
<html>
<body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <h1 style="color: #4f46e5; margin-bottom: 20px;">🧗‍♀️ Upvote.Club Test Email</h1>
        <p style="font-size: 16px; line-height: 1.6; color: #333;">
            This is a test email sent from Upvote.Club backend.
        </p>
        <div style="background: #f0f9ff; padding: 15px; border-radius: 5px; margin: 20px 0;">
            <p style="margin: 0; color: #0369a1;"><strong>Email Backend:</strong> {backend_type}</p>
            <p style="margin: 5px 0 0 0; color: #0369a1;"><strong>Backend Class:</strong> {backend_class}</p>
        </div>
        <p style="color: #666; font-size: 14px; margin-top: 30px;">
            If you received this email, the email sending configuration is working correctly! ✅
        </p>
    </div>
</body>
</html>
""".format(
            backend_type=getattr(settings, 'EMAIL_BACKEND_TYPE', 'not set'),
            backend_class=getattr(settings, 'EMAIL_BACKEND', 'not set')
        )
        
        email_service = EmailService()
        result = email_service.send_email(
            to_email=to_email,
            subject='🧗‍♀️ Upvote.Club - Test Email from SES',
            html_content=html_content
        )
        
        if result:
            self.stdout.write(self.style.SUCCESS(f'✓ Test email sent successfully to {to_email}'))
            logger.info(f"Test email sent successfully to {to_email}")
        else:
            self.stdout.write(self.style.ERROR(f'✗ Failed to send test email to {to_email}'))
            logger.error(f"Failed to send test email to {to_email}")
