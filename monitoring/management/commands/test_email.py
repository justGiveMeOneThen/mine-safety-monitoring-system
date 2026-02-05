from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings

class Command(BaseCommand):
    help = 'Test email configuration'
    
    def handle(self, *args, **options):
        try:
            send_mail(
                subject='🧪 Mine Safety System - Test Email',
                message='If you receive this, email is configured correctly!',
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[settings.DEFAULT_ALERT_EMAIL],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS('✅ Test email sent successfully!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Failed to send: {e}'))