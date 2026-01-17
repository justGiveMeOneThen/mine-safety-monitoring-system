# monitoring/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Sector, SensorReading, Prediction, Alert, ESP32Device

@admin.register(Sector)
class SectorAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at', 'device_count', 'reading_count']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    ordering = ['name']
    
    def device_count(self, obj):
        return obj.devices.count()
    device_count.short_description = 'Devices'
    
    def reading_count(self, obj):
        return obj.readings.count()
    reading_count.short_description = 'Readings'


@admin.register(SensorReading)
class SensorReadingAdmin(admin.ModelAdmin):
    list_display = ['sector', 'carbon_monoxide', 'temperature', 'co_status_badge', 'temp_status_badge', 'timestamp', 'device_id']
    list_filter = ['sector', 'timestamp']
    search_fields = ['sector__name', 'device_id']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']
    
    fieldsets = (
        ('Sector Information', {
            'fields': ('sector', 'device_id')
        }),
        ('Sensor Data', {
            'fields': ('carbon_monoxide', 'temperature', 'timestamp')
        }),
        ('Raw Data', {
            'fields': ('raw_data',),
            'classes': ('collapse',)
        }),
    )
    
    def co_status_badge(self, obj):
        status = obj.co_status
        colors = {
            'critical': '#ef4444',
            'warning': '#f59e0b',
            'normal': '#10b981'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            colors[status],
            status.upper()
        )
    co_status_badge.short_description = 'CO Status'
    
    def temp_status_badge(self, obj):
        status = obj.temp_status
        colors = {
            'critical': '#ef4444',
            'warning': '#f59e0b',
            'normal': '#10b981'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            colors[status],
            status.upper()
        )
    temp_status_badge.short_description = 'Temp Status'


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = ['sector', 'prediction_type', 'current_level', 'predicted_level', 'severity_badge', 'time_to_reach', 'timestamp']
    list_filter = ['severity', 'prediction_type', 'sector', 'timestamp']
    search_fields = ['sector__name', 'recommendation']
    date_hierarchy = 'timestamp'
    ordering = ['-timestamp']
    readonly_fields = ['timestamp']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('sector', 'prediction_type', 'severity')
        }),
        ('Prediction Details', {
            'fields': ('current_level', 'predicted_level', 'time_to_reach')
        }),
        ('Recommendation', {
            'fields': ('recommendation',)
        }),
        ('Model Information', {
            'fields': ('model_used', 'timestamp')
        }),
    )
    
    def severity_badge(self, obj):
        colors = {
            'critical': '#ef4444',
            'warning': '#f59e0b',
            'normal': '#10b981'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            colors[obj.severity],
            obj.severity.upper()
        )
    severity_badge.short_description = 'Severity'


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['sector', 'alert_type', 'severity_badge', 'status_badge', 'created_at', 'action_buttons']
    list_filter = ['status', 'severity', 'alert_type', 'created_at']
    search_fields = ['sector__name', 'message']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Alert Information', {
            'fields': ('sector', 'alert_type', 'severity', 'status')
        }),
        ('Details', {
            'fields': ('message',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'acknowledged_at', 'resolved_at')
        }),
    )
    
    actions = ['mark_acknowledged', 'mark_resolved']
    
    def severity_badge(self, obj):
        colors = {
            'critical': '#ef4444',
            'warning': '#f59e0b',
            'normal': '#10b981'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            colors[obj.severity],
            obj.severity.upper()
        )
    severity_badge.short_description = 'Severity'
    
    def status_badge(self, obj):
        colors = {
            'active': '#ef4444',
            'acknowledged': '#f59e0b',
            'resolved': '#10b981'
        }
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: bold;">{}</span>',
            colors[obj.status],
            obj.status.upper()
        )
    status_badge.short_description = 'Status'
    
    def action_buttons(self, obj):
        if obj.status == 'active':
            return format_html(
                '<a class="button" href="#">Acknowledge</a>'
            )
        elif obj.status == 'acknowledged':
            return format_html(
                '<a class="button" href="#">Resolve</a>'
            )
        return format_html('<span style="color: #10b981;">✓ Resolved</span>')
    action_buttons.short_description = 'Actions'
    
    def mark_acknowledged(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='active').update(
            status='acknowledged',
            acknowledged_at=timezone.now()
        )
        self.message_user(request, f'{updated} alert(s) marked as acknowledged.')
    mark_acknowledged.short_description = 'Mark as Acknowledged'
    
    def mark_resolved(self, request, queryset):
        from django.utils import timezone
        updated = queryset.exclude(status='resolved').update(
            status='resolved',
            resolved_at=timezone.now()
        )
        self.message_user(request, f'{updated} alert(s) marked as resolved.')
    mark_resolved.short_description = 'Mark as Resolved'


@admin.register(ESP32Device)
class ESP32DeviceAdmin(admin.ModelAdmin):
    list_display = ['device_id', 'sector', 'serial_port', 'baud_rate', 'online_status', 'last_seen']
    list_filter = ['is_online', 'sector', 'baud_rate']
    search_fields = ['device_id', 'sector__name', 'serial_port']
    ordering = ['sector__name']
    
    fieldsets = (
        ('Device Information', {
            'fields': ('device_id', 'sector', 'firmware_version')
        }),
        ('Connection Settings', {
            'fields': ('serial_port', 'baud_rate')
        }),
        ('Status', {
            'fields': ('is_online', 'last_seen')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
    )
    
    def online_status(self, obj):
        if obj.is_online:
            return format_html(
                '<span style="color: #10b981; font-weight: bold;">● Online</span>'
            )
        return format_html(
            '<span style="color: #ef4444; font-weight: bold;">● Offline</span>'
        )
    online_status.short_description = 'Status'


# Customize admin site header and title
admin.site.site_header = 'Mine Safety Monitoring System'
admin.site.site_title = 'Mine Safety Admin'
admin.site.index_title = 'Dashboard Administration'