# core/management/commands/create_admin.py

import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from dotenv import load_dotenv

class Command(BaseCommand):
    help = 'Creates a superuser from .env variables if one does not exist'

    def handle(self, *args, **kwargs):
        load_dotenv()
        username = os.getenv('ADMIN_USERNAME')
        password = os.getenv('ADMIN_PASSWORD')
        
        if not username or not password:
            self.stdout.write(self.style.ERROR('ADMIN_USERNAME or ADMIN_PASSWORD not set in .env file.'))
            return
            
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, password=password, email='')
            self.stdout.write(self.style.SUCCESS(f'Successfully created superuser: {username}'))
        else:
            self.stdout.write(self.style.WARNING(f'User {username} already exists. Skipping creation.'))