# admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser  # Import the custom user model

class CustomUserAdmin(UserAdmin):
    # List of fields to display in the user list view
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')

    # Fields to include in the User's edit form
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('role',)}),  # Add 'role' here
    )

    # Fields to display in the user change form (the form that shows when you edit a user)
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('role',)}),  # Add 'role' here as well
    )

# Register the custom user model with the custom admin
admin.site.register(CustomUser, CustomUserAdmin)
