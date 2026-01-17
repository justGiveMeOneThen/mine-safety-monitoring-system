# monitoring/models.py

from django.db import models
from django.utils import timezone

class Sector(models.Model):
    """Mine sector information"""
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class SensorReading(models.Model):
    """
    Store sensor readings from ESP32
    Future: Will be populated via serial port data
    """
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE, related_name='readings')
    carbon_monoxide = models.FloatField(help_text='CO level in ppm')
    temperature = models.FloatField(help_text='Temperature in Celsius')
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    
    # ESP32 specific fields (for future use)
    device_id = models.CharField(max_length=50, blank=True, null=True)
    raw_data = models.JSONField(blank=True, null=True, help_text='Raw sensor data from ESP32')
    
    def __str__(self):
        return f"{self.sector.name} - {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['sector', '-timestamp']),
        ]
    
    @property
    def co_status(self):
        """Return CO level status"""
        if self.carbon_monoxide > 50:
            return 'critical'
        elif self.carbon_monoxide > 30:
            return 'warning'
        return 'normal'
    
    @property
    def temp_status(self):
        """Return temperature status"""
        if self.temperature > 35:
            return 'critical'
        elif self.temperature > 30:
            return 'warning'
        return 'normal'


class Prediction(models.Model):
    """Store ML model predictions"""
    SEVERITY_CHOICES = [
        ('normal', 'Normal'),
        ('warning', 'Warning'),
        ('critical', 'Critical'),
    ]
    
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE, related_name='predictions')
    prediction_type = models.CharField(max_length=50, help_text='CO or Temperature')
    current_level = models.FloatField()
    predicted_level = models.FloatField()
    time_to_reach = models.IntegerField(help_text='Minutes until predicted level')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='normal')
    recommendation = models.TextField()
    model_used = models.CharField(max_length=100, default='risk_model.joblib')
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    
    def __str__(self):
        return f"{self.sector.name} - {self.prediction_type} - {self.severity}"
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['sector', '-timestamp']),
        ]


class Alert(models.Model):
    """Store safety alerts"""
    ALERT_TYPES = [
        ('co_high', 'High CO Level'),
        ('temp_high', 'High Temperature'),
        ('sensor_failure', 'Sensor Failure'),
        ('prediction_critical', 'Critical Prediction'),
    ]
    
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('acknowledged', 'Acknowledged'),
        ('resolved', 'Resolved'),
    ]
    
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE, related_name='alerts')
    alert_type = models.CharField(max_length=30, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=Prediction.SEVERITY_CHOICES, default='warning')
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    acknowledged_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.sector.name}"
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]


class ESP32Device(models.Model):
    """
    Store ESP32 device information for future IoT integration
    """
    device_id = models.CharField(max_length=50, unique=True)
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE, related_name='devices')
    serial_port = models.CharField(max_length=50, blank=True, help_text='e.g., /dev/ttyUSB0 or COM3')
    baud_rate = models.IntegerField(default=9600)
    is_online = models.BooleanField(default=False)
    last_seen = models.DateTimeField(blank=True, null=True)
    firmware_version = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.device_id} - {self.sector.name}"
    
    class Meta:
        ordering = ['sector__name']
        verbose_name = 'ESP32 Device'
        verbose_name_plural = 'ESP32 Devices'