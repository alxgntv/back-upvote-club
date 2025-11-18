import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
#from email.mime.image import MIMEImage  # больше не нужен
import os
from email.utils import formataddr

logger = logging.getLogger(__name__)

class EmailService:
    def send_email(self, to_email, subject, html_content, unsubscribe_url=None, campaign_id=None, bcc_email=None, attachments=None):
        logger.info(f"Starting to send email to {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Content length: {len(html_content)} chars")
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
            if unsubscribe_url:
                email.extra_headers = {
                    'List-Unsubscribe': f'<{unsubscribe_url}>, <mailto:{settings.DEFAULT_FROM_EMAIL}?subject=unsubscribe>',
                    'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
                    'List-Owner': f'<mailto:{settings.DEFAULT_FROM_EMAIL}>',
                    'List-Id': '<mail.upvote.club>',
                    'X-SES-CONFIGURATION-SET': 'no-track',
                    'X-SES-MESSAGE-TAGS': 'trackLinks=false,trackOpens=false',
                    'X-SES-RETURN-PATH': settings.DEFAULT_FROM_EMAIL,
                }
                logger.info(f"Added unsubscribe header: {unsubscribe_url}")
            
            logger.info(f"Attempting to send email to {to_email}")
            email.send(fail_silently=False)
            
            logger.info(f"Email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            logger.error(f"Error details: {type(e).__name__}")
            return False