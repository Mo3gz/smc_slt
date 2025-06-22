# import_users_script.py
import os
import django
import openpyxl
import random
import string

# --- IMPORTANT: Load .env file BEFORE Django setup ---
try:
    from dotenv import load_dotenv
    # Load .env from the current directory where the script is run,
    # or specify a path if your .env is elsewhere (e.g., os.path.join(os.path.dirname(__file__), '..', '.env'))
    load_dotenv()
    print("DEBUG: .env file loaded successfully.")
except ImportError:
    print("WARNING: python-dotenv not installed. If you use .env for settings, please install it: pip install python-dotenv")
except Exception as e:
    print(f"WARNING: Error loading .env file: {e}. Check .env file path/permissions.")

# --- IMPORTANT: Set up Django environment ---
# >>> REPLACE 'your_project_name.settings' with your actual settings path <<<
# Example: If your project's main folder is named 'smc_slt_project', and your settings.py is inside 'smc_slt',
# then the path will be 'smc_slt.settings'
# From your traceback, it seems your project folder is 'smc_slt', so try 'smc_slt.settings'
DJANGO_SETTINGS_PATH = 'smc_slt.settings' # <--- CONFIRM THIS IS YOUR ACTUAL SETTINGS PATH

print(f"DEBUG: Attempting to set DJANGO_SETTINGS_MODULE to: {DJANGO_SETTINGS_PATH}")
os.environ.setdefault('DJANGO_SETTINGS_MODULE', DJANGO_SETTINGS_PATH)

try:
    django.setup()
    print("DEBUG: Django environment setup complete.")
except Exception as e:
    print(f"ERROR: Failed to setup Django environment. Error: {e}")
    print(f"Please double-check that '{DJANGO_SETTINGS_PATH}' is the correct import path to your settings.py.")
    print("Also ensure that your .env file (if used) is correctly loaded and accessible.")
    import sys
    sys.exit(1) # Exit the script if setup fails

# --- IMPORTS THAT DEPEND ON DJANGO SETTINGS MUST COME AFTER django.setup() ---
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.sites.models import Site # MOVED HERE!
from django.urls import reverse
from django.conf import settings # MOVED HERE!

# Now you can import your app-specific models and tokens
from members.models import CustomUser # Adjust 'authenticate' to your app name
from members.tokens import account_activation_token # Adjust 'authenticate' to your app name

# --- Helper function to generate random password ---
def _generate_random_password(length=12):
    characters = string.ascii_letters + string.digits + string.punctuation
    password_chars = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
        random.choice(string.punctuation),
    ]
    password_chars += [random.choice(characters) for _ in range(length - len(password_chars))]
    random.shuffle(password_chars)
    return ''.join(password_chars)

# --- Email sending function for imported users ---
def send_activation_email_for_imported_users(user, to_email, raw_password):
    mail_subject = 'Activate Your Account - Login Details'
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_activation_token.make_token(user)

    try:
        current_site = Site.objects.get_current()
        domain = current_site.domain
    except Site.DoesNotExist:
        domain = 'example.com' # Fallback if Site framework not configured/data missing
        print(f"WARNING: Django Site framework not configured or site data missing. Using {domain} for email link.")
    except Exception as e:
        domain = 'example.com'
        print(f"WARNING: Could not get current site domain: {e}. Using {domain} for email link.")

    activation_url = f"http://{domain}{reverse('activate', kwargs={'uidb64': uidb64, 'token': token})}"

    message_html = render_to_string('authenticate/account_activation_email_import.html', {
        'user': user,
        'activation_url': activation_url,
        'password': raw_password,
        'domain': domain,
    })

    from_email = settings.DEFAULT_FROM_EMAIL if hasattr(settings, 'DEFAULT_FROM_EMAIL') and settings.DEFAULT_FROM_EMAIL else 'noreply@example.com'

    try:
        email = EmailMessage(
            mail_subject,
            message_html,
            from_email,
            to=[to_email]
        )
        email.content_subtype = "html"
        email.send()
        print(f"DEBUG: Activation email with password sent to {to_email}")
    except Exception as e:
        print(f"ERROR: Failed to send activation email to {to_email}: {e}")

# --- Main import function ---
def run_import(excel_file_path):
    print(f"Starting user import from {excel_file_path}...")

    try:
        workbook = openpyxl.load_workbook(excel_file_path)
        sheet = workbook.active
    except FileNotFoundError:
        print(f"ERROR: Excel file '{excel_file_path}' not found.")
        return
    except Exception as e:
        print(f"ERROR: Error opening Excel file: {e}")
        return

    header = [cell.value for cell in sheet[1]]
    
    required_columns = ['username', 'Email', 'role']
    if not all(col in header for col in required_columns):
        print(f"ERROR: Excel file must contain 'username', 'Email', and 'role' columns. Found: {header}")
        return

    users_created_count = 0
    users_updated_count = 0
    users_skipped_count = 0
    errors = []

    for row_index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        data = dict(zip(header, row))
        
        original_username = data.get('username')
        email = data.get('Email')
        role = data.get('role')

        if not original_username or not email or not role:
            errors.append(f"Row {row_index}: Missing username, email, or role. Skipped.")
            users_skipped_count += 1
            continue

        if role not in ['User', 'WH']:
            errors.append(f"Row {row_index}: Invalid role '{role}'. Must be 'User' or 'WH'. Skipped.")
            users_skipped_count += 1
            continue

        # 1. Truncate username to first two names
        name_parts = original_username.split()
        if len(name_parts) > 2:
            base_processed_username = " ".join(name_parts[:2])
            print(f"DEBUG: Truncated username '{original_username}' to '{base_processed_username}'")
        else:
            base_processed_username = original_username

        # 2. Replace spaces with underscores
        base_processed_username_underscored = base_processed_username.replace(' ', '_')
        print(f"DEBUG: Converted username to '{base_processed_username_underscored}' by replacing spaces with underscores.")

        # --- REVISED UNIQUENESS HANDLING FOR USERNAME ---
        # Find a truly unique username BEFORE attempting to create/update
        final_unique_username = base_processed_username_underscored
        attempt_suffix = 0
        max_attempts = 100 # Safety limit to prevent infinite loops

        # Loop until a username is found that does NOT exist in the database
        # or max_attempts is reached.
        while get_user_model().objects.filter(username=final_unique_username).exists() and attempt_suffix < max_attempts:
            attempt_suffix += 1
            final_unique_username = f"{base_processed_username_underscored}_{attempt_suffix}"
            print(f"DEBUG: Username '{base_processed_username_underscored}' already exists. Trying '{final_unique_username}'.")
        
        # If we failed to find a unique username after many attempts, skip this row.
        if attempt_suffix >= max_attempts:
            errors.append(f"Row {row_index} ({original_username}, {email}): Could not find unique username after {max_attempts} attempts. Skipped.")
            users_skipped_count += 1
            continue # Move to the next row in Excel
        # --- END REVISED UNIQUENESS HANDLING ---

        try:
            with transaction.atomic():
                # Now, use the final_unique_username.
                # get_or_create will find by email. If it creates, it uses this final_unique_username.
                # If it finds an existing user by email, it will update their username if different.
                user, created = get_user_model().objects.get_or_create(
                    email=email, # Primary lookup is email
                    defaults={
                        'username': final_unique_username, # Provide the already-guaranteed-unique username
                        'role': role,
                        'is_active': False,
                    }
                )
                
                if created:
                    # User was newly created. Its username is already set to final_unique_username.
                    raw_password = _generate_random_password()
                    user.set_password(raw_password)
                    user.save() # Save the user with the unique username and hashed password
                    send_activation_email_for_imported_users(user, email, raw_password)
                    print(f'Created user: {user.username} ({user.email})')
                    users_created_count += 1
                else:
                    # User already existed based on email.
                    # We update their username and role if they differ from the Excel data.
                    # We don't need to generate a suffix for an existing user's username here;
                    # the goal is to make their username match what's derived from the Excel sheet.
                    if user.username != final_unique_username or user.role != role:
                        user.username = final_unique_username
                        user.role = role
                        user.save()
                        print(f'Updated existing user: {user.username} ({user.email})')
                        users_updated_count += 1
                    else:
                        print(f'Skipped existing user (no changes): {user.username} ({user.email})')
                        users_skipped_count += 1

        except Exception as e:
            # Catch any other unexpected errors during transaction (e.g., database issues, email failure)
            errors.append(f"Error processing row {row_index} ({original_username}, {email}): {e}")
            users_skipped_count += 1

    print('User import complete!')
    print(f'Total users created: {users_created_count}')
    print(f'Total users updated: {users_updated_count}')
    print(f'Total users skipped/errored: {users_skipped_count}')
    if errors:
        print("\nErrors encountered:")
        for error in errors:
            print(f"- {error}")

if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print("Usage: python import_users_script.py <path_to_excel_file>")
        sys.exit(1)
    
    excel_file = sys.argv[1]
    run_import(excel_file)