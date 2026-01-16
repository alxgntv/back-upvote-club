import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
import os
from email.utils import formataddr

logger = logging.getLogger(__name__)

class EmailService:
    def send_email(self, to_email, subject, html_content, unsubscribe_url=None, campaign_id=None, bcc_email=None, attachments=None):
        # Определяем какой email backend используется
        email_backend = getattr(settings, 'EMAIL_BACKEND', 'unknown')
        email_backend_type = getattr(settings, 'EMAIL_BACKEND_TYPE', 'unknown')
        
        logger.info(f"=" * 80)
        logger.info(f"EMAIL SENDING STARTED")
        logger.info(f"Backend Type: {email_backend_type}")
        logger.info(f"Backend Class: {email_backend}")
        if email_backend_type == 'ses':
            logger.info(f"AWS SES Region: {getattr(settings, 'AWS_SES_REGION_NAME', 'not set')}")
            logger.info(f"AWS SES Configuration Set: {getattr(settings, 'AWS_SES_CONFIGURATION_SET', 'not set')}")
        logger.info(f"To: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Content length: {len(html_content)} chars")
        logger.info(f"From: {settings.DEFAULT_FROM_EMAIL}")
        # Корректно формируем список для bcc
        if bcc_email:
            if isinstance(bcc_email, str):
                bcc = [bcc_email]
                logger.info(f"BCC is a string, converted to list: {bcc}")
            elif isinstance(bcc_email, list):
                bcc = bcc_email
                logger.info(f"BCC is a list: {bcc}")
            else:
                logger.error(f"BCC email has unsupported type: {type(bcc_email)}. Value: {bcc_email}")
                bcc = None
        else:
            bcc = None
            logger.info("No BCC specified")
        try:
            # Создаем EmailMultiAlternatives с красивым именем отправителя
            email = EmailMultiAlternatives(
                subject=subject,
                body='',
                from_email=formataddr(('🧗‍♀️ Upvote.Club', settings.DEFAULT_FROM_EMAIL)),
                to=[to_email],
                bcc=bcc
            )
            
            # Добавляем HTML версию
            email.attach_alternative(html_content, "text/html")
            logger.info("HTML content attached")
            
            # Добавляем вложения, если есть
            if attachments:
                for filename, content, mimetype in attachments:
                    email.attach(filename, content, mimetype)
                logger.info(f"Attached {len(attachments)} files to email")
            
            # Добавляем заголовки
            headers = {}
            
            if unsubscribe_url:
                headers.update({
                    'List-Unsubscribe': f'<{unsubscribe_url}>, <mailto:{settings.DEFAULT_FROM_EMAIL}?subject=unsubscribe>',
                    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
                    'List-Owner': f'<mailto:{settings.DEFAULT_FROM_EMAIL}>',
                    'List-Id': '<mail.upvote.club>',
                })
                logger.info(f"Added unsubscribe header: {unsubscribe_url}")
            
            # Добавляем SES заголовки только если используем SES и есть Configuration Set
            if email_backend_type == 'ses':
                ses_config_set = getattr(settings, 'AWS_SES_CONFIGURATION_SET', None)
                if ses_config_set:
                    headers.update({
                        'X-SES-CONFIGURATION-SET': ses_config_set,
                    })
                    logger.info(f"Added SES Configuration Set: {ses_config_set}")
                else:
                    logger.info("No SES Configuration Set specified (tracking via default SES settings)")
            
            if headers:
                email.extra_headers = headers
            
            logger.info(f"Attempting to send email via {email_backend_type.upper()}")
            email.send(fail_silently=False)
            
            logger.info(f"✓ Email sent successfully via {email_backend_type.upper()} to {to_email}")
            logger.info(f"=" * 80)
            return True
            
        except Exception as e:
            logger.error(f"=" * 80)
            logger.error(f"✗ FAILED to send email via {email_backend_type.upper()}")
            logger.error(f"To: {to_email}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error message: {str(e)}")
            logger.error(f"Backend: {email_backend}")
            logger.error(f"=" * 80)
            return False