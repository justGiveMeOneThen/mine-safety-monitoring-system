from django.core.mail import send_mail
from django.conf import settings
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PredictiveAlertSystem:
    def __init__(self):
        self.alert_history = {}  # Track sent alerts to avoid spam
        self.alert_cooldown = 300  # 5 minutes between same alerts
    
    def should_send_alert(self, alert_id):
        #Check if enough time has passed since last alert
        if alert_id not in self.alert_history:
            return True
        
        last_alert_time = self.alert_history[alert_id]
        time_since_last = (datetime.now() - last_alert_time).total_seconds()
        
        return time_since_last >= self.alert_cooldown
    
    def send_prediction_alert(self, prediction_data, sector_name):
        severity = prediction_data.get('severity')
        gas_type = prediction_data.get('gasType')
        current_level = prediction_data.get('currentLevel')
        predicted_level = prediction_data.get('predictedLevel')
        time_to_reach = prediction_data.get('timeToReach')
        recommendation = prediction_data.get('recommendation')
        
        # Create unique alert ID
        alert_id = f"{sector_name}_{gas_type}_{severity}"
        
        # Check if we should send this alert
        if not self.should_send_alert(alert_id):
            logger.info(f"Alert cooldown active for {alert_id}")
            return False
        
        # Determine urgency level
        urgency = self._determine_urgency(severity, time_to_reach)
        
        # Build email content
        subject = self._build_subject(severity, sector_name, gas_type, time_to_reach)
        message = self._build_message(
            sector_name, gas_type, current_level, predicted_level,
            time_to_reach, severity, recommendation, urgency
        )
        html_message = self._build_html_message(
            sector_name, gas_type, current_level, predicted_level,
            time_to_reach, severity, recommendation, urgency
        )
        
        # Send email
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=self._get_recipients(severity),
                fail_silently=False,
                html_message=html_message
            )
            
            # Record alert
            self.alert_history[alert_id] = datetime.now()
            logger.info(f"[SUCCESS] Prediction alert sent: {alert_id}")
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to send alert: {e}")
            return False
    
    def _determine_urgency(self, severity, time_to_reach):
        #Determine urgency based on severity and time
        if severity == 'critical':
            if time_to_reach <= 10:
                return 'IMMEDIATE'
            elif time_to_reach <= 20:
                return 'URGENT'
            else:
                return 'HIGH'
        elif severity == 'warning':
            if time_to_reach <= 15:
                return 'MODERATE'
            else:
                return 'LOW'
        return 'INFO'
    
    def _build_subject(self, severity, sector, gas_type, time_to_reach):
        #Build email subject line
        emoji = '🚨' if severity == 'critical' else '⚠️'
        
        if time_to_reach <= 10:
            urgency_text = "IMMEDIATE ACTION REQUIRED"
        elif time_to_reach <= 20:
            urgency_text = "URGENT"
        else:
            urgency_text = "ALERT"
        
        return f"{emoji} {urgency_text}: {gas_type} Prediction - {sector}"
    
    def _build_message(self, sector, gas_type, current, predicted, 
                    time_to_reach, severity, recommendation, urgency):
        """Build plain text email message"""
        unit = '°C' if gas_type == 'Temperature' else 'ppm'
        
        return f"""
MINE SAFETY PREDICTIVE ALERT
{'=' * 50}

URGENCY LEVEL: {urgency}
SECTOR: {sector}
HAZARD TYPE: {gas_type}
SEVERITY: {severity.upper()}

CURRENT READINGS:
  {gas_type}: {current:.2f} {unit}

AI PREDICTION:
  Predicted Level: {predicted:.2f} {unit}
  Estimated Time to Reach: {time_to_reach} minutes
  Expected Time of Occurrence: {(datetime.now() + timedelta(minutes=time_to_reach)).strftime('%Y-%m-%d %H:%M:%S')}

RECOMMENDED ACTION:
{recommendation}

{'=' * 50}
This is an automated alert from the Mine Safety System.
Alert generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

DO NOT REPLY to this email. Check the dashboard for real-time updates
        """
    
    def _build_html_message(self, sector, gas_type, current, predicted,
                            time_to_reach, severity, recommendation, urgency):
        #Build HTML email message
        unit = '°C' if gas_type == 'Temperature' else 'ppm'
        
        # Color scheme based on severity
        if severity == 'critical':
            color = '#ef4444'
            bg_color = '#fee2e2'
        else:
            color = '#f59e0b'
            bg_color = '#fef3c7'
        
        estimated_time = (datetime.now() + timedelta(minutes=time_to_reach)).strftime('%H:%M:%S')
        estimated_date = (datetime.now() + timedelta(minutes=time_to_reach)).strftime('%Y-%m-%d')
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: {color}; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
        .content {{ background: white; padding: 20px; border: 2px solid {color}; border-radius: 0 0 8px 8px; }}
        .alert-box {{ background: {bg_color}; border-left: 4px solid {color}; padding: 15px; margin: 15px 0; }}
        .metric {{ background: #f8fafc; padding: 12px; margin: 8px 0; border-radius: 6px; }}
        .metric-label {{ font-weight: bold; color: #64748b; font-size: 12px; }}
        .metric-value {{ font-size: 24px; font-weight: bold; color: {color}; }}
        .recommendation {{ background: #f1f5f9; padding: 15px; border-left: 4px solid #3b82f6; margin: 15px 0; }}
        .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #64748b; }}
        .urgency {{ background: {color}; color: white; padding: 8px 16px; border-radius: 20px; display: inline-block; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{'🚨' if severity == 'critical' else '⚠️'} MINE SAFETY PREDICTIVE ALERT</h1>
            <p style="margin: 5px 0;">Sector: <strong>{sector}</strong></p>
            <span class="urgency">{urgency}</span>
        </div>
        
        <div class="content">
            <div class="alert-box">
                <h2 style="margin-top: 0; color: {color};">AI Prediction: {gas_type} Hazard</h2>
                <p><strong>Severity:</strong> {severity.upper()}</p>
            </div>
            
            <h3>Current Readings</h3>
            <div class="metric">
                <div class="metric-label">CURRENT {gas_type.upper()}</div>
                <div class="metric-value">{current:.2f} {unit}</div>
            </div>
            
            <h3>AI Prediction</h3>
            <div class="metric">
                <div class="metric-label">PREDICTED LEVEL</div>
                <div class="metric-value">{predicted:.2f} {unit}</div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0;">
                <div class="metric">
                    <div class="metric-label">TIME TO REACH</div>
                    <div style="font-size: 20px; font-weight: bold; color: {color};">
                        {time_to_reach} min
                    </div>
                </div>
                <div class="metric">
                    <div class="metric-label">ESTIMATED TIME</div>
                    <div style="font-size: 16px; font-weight: bold; color: {color};">
                        {estimated_time}<br>
                        <span style="font-size: 12px;">{estimated_date}</span>
                    </div>
                </div>
            </div>
            
            <div class="recommendation">
                <h3 style="margin-top: 0;">Recommended Action</h3>
                <p>{recommendation}</p>
            </div>
        </div>
        
        <div class="footer">
            <p>This is an automated alert from the Mine Safety System</p>
            <p>Alert generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>DO NOT REPLY</strong> on this email.</p>
        </div>
    </div>
</body>
</html>
        """
    
    def _get_recipients(self, severity):
        #Get recipient list based on severity
        # Get from settings or database
        recipients = [settings.DEFAULT_ALERT_EMAIL]
        
        # Add escalation for critical alerts
        if severity == 'critical':
            recipients.extend(getattr(settings, 'CRITICAL_ALERT_EMAILS', []))
        
        return recipients
    
    def send_all_clear_notification(self, sector_name):
        """Send notification when conditions return to normal"""
        subject = f"ALL CLEAR: {sector_name} - Conditions Normalized"
        
        message = f"""
MINE SAFETY STATUS UPDATE
{'=' * 50}

SECTOR: {sector_name}
STATUS: ALL CLEAR

All sensor readings have returned to normal levels.
No immediate hazards detected.

Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Continue monitoring via dashboard:
        """
        
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=[settings.DEFAULT_ALERT_EMAIL],
                fail_silently=False,
            )
            logger.info(f"[SUCCESS] All clear notification sent for {sector_name}")
        except Exception as e:
            logger.error(f"Failed to send all clear: {e}")


# Initialize alert system
alert_system = PredictiveAlertSystem()