from django.urls import path
from . import views

app_name = 'monitoring'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analytics/', views.analytics, name='analytics'),

    # API endpoints (polled by dashboard & analytics every 5s)
    path('api/sensor-data/', views.get_sensor_data, name='sensor_data'),
    path('api/predictions/', views.get_predictions, name='predictions'),
    path('api/historical-data/', views.get_historical_data, name='historical_data'),
    path('api/serial-status/', views.serial_status, name='serial_status'),
]