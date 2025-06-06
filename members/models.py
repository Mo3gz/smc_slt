# models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    role = models.CharField(
        max_length=10,
        choices=[('User', 'User'), ('WH', 'WH')],
        default='User'
    )
    
    def __str__(self):
        return self.username
