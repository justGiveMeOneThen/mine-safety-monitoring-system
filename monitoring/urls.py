from django.urls import path
from . import views

app_name = 'monitoring'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('analytics/', views.analytics, name='analytics'),
    path('api/sensor-data/', views.get_sensor_data, name='sensor_data'),
    path('api/predictions/', views.get_predictions, name='predictions'),
    path('api/historical-data/', views.get_historical_data, name='historical_data'),
]