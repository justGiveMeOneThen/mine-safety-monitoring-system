from django.core.management.base import BaseCommand
from monitoring.alerts import alert_system

class Command(BaseCommand):
    help = 'Test predictive alert system'
    
    def handle(self, *args, **options):
        # Mock prediction data
        test_prediction = {
            'gasType': 'Carbon Monoxide',
            'currentLevel': 35.5,
            'predictedLevel': 55.2,
            'timeToReach': 12,
            'severity': 'critical',
            'recommendation': 'This is a test alert. Evacuate immediately if real.'
        }
        
        result = alert_system.send_prediction_alert(test_prediction, 'Sector 1')
        
        if result:
            self.stdout.write(self.style.SUCCESS('✅ Alert sent successfully!'))
        else:
            self.stdout.write(self.style.WARNING('⚠️ Alert in cooldown or failed'))