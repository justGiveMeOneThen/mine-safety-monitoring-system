from django.core.management.base import BaseCommand
import serial.tools.list_ports

class Command(BaseCommand):
    help = 'List available serial ports for ESP32'
    
    def handle(self, *args, **options):
        ports = serial.tools.list_ports.comports()
        
        self.stdout.write(self.style.SUCCESS('Available Serial Ports:'))
        for port in ports:
            self.stdout.write(f'  - {port.device}: {port.description}')
        
        if not ports:
            self.stdout.write(self.style.WARNING('No serial ports found'))