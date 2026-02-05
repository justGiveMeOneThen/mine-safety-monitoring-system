from django.test import TestCase, Client
from django.urls import reverse

class DashboardTests(TestCase):
    def setUp(self):
        self.client = Client()
    
    def test_home_page(self):
        response = self.client.get(reverse('monitoring:home'))
        self.assertEqual(response.status_code, 200)
    
    def test_sensor_api(self):
        response = self.client.get(reverse('monitoring:sensor_data'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('sensors', response.json())
    
    def test_ml_predictions(self):
        response = self.client.get(reverse('monitoring:predictions'))
        self.assertEqual(response.status_code, 200)