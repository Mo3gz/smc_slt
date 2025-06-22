from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm, PasswordResetForm
from .forms import RegisterUserForm, SetPasswordForm, CustomSetPasswordForm, UpdateUserRoleForm
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import EmailMessage, send_mail
from .models import CustomUser  # Import your custom user model
from .tokens import account_activation_token
from django.contrib.auth.views import PasswordResetConfirmView
from django.contrib.auth.decorators import user_passes_test
from django.views.decorators.cache import never_cache
from django.urls import reverse_lazy
from django.contrib.auth.views import PasswordResetView
from django.urls import reverse

@never_cache  # Prevent browser from caching login page (fixes CSRF token issues)
def login_user(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']

        # Check if the user exists
        try:
            user = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            messages.warning(request, "User Not Found! This user does not exist. Please sign up or check your credentials.")
            return redirect('login')

        # Check if the user is active before authenticating
        if not user.is_active:
            messages.warning(request, "Your account is not activated yet. Please check your email.")
            return redirect('email_confirm')  # Redirect user to activation instructions page

        # Authenticate user
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('page_list_event')
        else:
            messages.warning(request, "Invalid Login! The username or password you entered is incorrect. Please try again.")
            return redirect('login')

    else:
        return render(request, 'authenticate/login.html')


def logout_user(request):
    logout(request)
    messages.success(request, ("You Were Logged Out!"))
    return redirect('login')


def activate(request, uidb64, token):
    User = get_user_model()

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and account_activation_token.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, 'Thank you for your email confirmation. Now you can login to your account.')
        return redirect('login')
    else:
        messages.error(request, 'Activation link is invalid!')
        return redirect('login')

    return redirect('page_list_event')


def activateEmail(request, user, to_email):
    mail_subject = 'Activate your user account.'
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_activation_token.make_token(user)
    # Using request.build_absolute_uri with reverse for robust URL building
    activation_url = request.build_absolute_uri(
        reverse('activate', kwargs={'uidb64': uidb64, 'token': token})
    )

    # --- THIS IS THE ONLY LINE THAT CHANGES TO USE THE TEMPLATE ---
    message = render_to_string('authenticate/account_activation_email_import.html', {
        'user': user,
        'activation_url': activation_url,
        'password': user.password,
    })
    # --- END OF CHANGE ---

    email = EmailMessage(mail_subject, message, 'smc.slt2025@gmail.com', to=[to_email])
    
    # --- ADD THIS LINE to tell the email client it's HTML ---
    email.content_subtype = "html" 
    # --- END OF ADDITION ---

    email.send() # Make sure the email is actually sent


def register_user(request):
    if request.method == 'POST':
        form = RegisterUserForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data.get('email')
            user = form.save(commit=False)
            user.is_active = False  # Deactivate the user until email is confirmed
            user.save()

            activateEmail(request, user, email)  # Send activation email
            return redirect('email_confirm')

    else:
        form = RegisterUserForm()

    context = {
        'form': form
    }

    return render(request, 'authenticate/register_user.html', context)


def email_confirm(request):
    return render(request, 'authenticate/email_confirm.html')


def resend_activation_email(request):
    User = get_user_model()

    if request.method == 'POST':
        email = request.POST.get('email')

        try:
            user = User.objects.get(email=email)

            if user.is_active:
                messages.success(request, "Your account is already activated. You can log in.")
                return redirect('login')

            # Generate a new activation link
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = account_activation_token.make_token(user)
            activation_url = f"{'https' if request.is_secure() else 'http'}://{get_current_site(request).domain}/activate/{uidb64}/{token}"

            # Send the activation email
            mail_subject = 'Resend: Activate Your Account'
            message = f"Hello {user.username},\n\nClick the link below to activate your account:\n\n{activation_url}"
            send_mail(mail_subject, message, 'smc.slt2025@gmail.com', [email])

            messages.success(request, "A new activation email has been sent. Please check your inbox.")
            return redirect('login')

        except User.DoesNotExist:
            messages.error(request, "No account found with this email.")

    return render(request, 'authenticate/resend_activation.html')


@user_passes_test(lambda u: u.is_superuser)
def update_user_role(request, user_id):
    user = get_object_or_404(CustomUser, id=user_id)

    if request.method == 'POST':
        form = UpdateUserRoleForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"User role updated successfully.")
            return redirect('page_list_users')  # Redirect to user list page

    else:
        form = UpdateUserRoleForm(instance=user)

    return render(request, 'authenticate/update-user-role.html', {'form': form, 'user': user})


# --- NEW: Delete User View ---
@user_passes_test(lambda u: u.is_superuser) # Only superusers can delete
def delete_user(request, user_id):
    # Get the user to be deleted, or return 404 if not found
    user_to_delete = get_object_or_404(CustomUser, id=user_id)

    # IMPORTANT SECURITY CHECK: Prevent a superuser from deleting their own account
    if request.user.id == user_to_delete.id:
        messages.error(request, "You cannot delete your own account.")
        return redirect('page_list_users')

    if request.method == 'POST':
        try:
            username = user_to_delete.username # Store username for the message
            user_to_delete.delete() # Perform the deletion
            messages.success(request, f"User '{username}' deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting user '{username}': {e}")
        return redirect('page_list_users') # Redirect back to the user list
    else:
        # If someone tries to access this view with a GET request (e.g., by typing the URL),
        # we don't allow it for security reasons.
        messages.error(request, "Invalid request method for deleting a user. Please use the delete button.")
        return redirect('page_list_users')

class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = CustomSetPasswordForm


# ---- Custom Password Reset View ----
class CustomPasswordResetView(PasswordResetView):
    template_name = 'authenticate/password_reset_form.html'
    email_template_name = 'authenticate/password_reset_email.html'
    form_class = PasswordResetForm
    success_url = reverse_lazy('password_reset_done')

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        UserModel = get_user_model()
        users = UserModel.objects.filter(email=email, is_active=True)
        if users.exists():
            return super().form_valid(form)  # Send reset email as usual
        else:
            messages.error(self.request, "No account found with this email address.")
            return self.form_invalid(form)