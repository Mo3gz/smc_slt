from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from .views import CustomPasswordResetConfirmView

urlpatterns = [
    path('', views.login_user, name='login'),
    path('logout_user/', views.logout_user, name='logout'),
    path('register_user/', views.register_user, name='register_user'),
    path('activate/<uidb64>/<token>/', views.activate, name='activate'),
    path('email_confirm/', views.email_confirm, name='email_confirm'),
    path('resend-activation/', views.resend_activation_email, name='resend_activation'),
    path('update-role-<int:user_id>/', views.update_user_role, name='update_user_role'),
    path('pass_reset/', auth_views.PasswordResetView.as_view(template_name='authenticate/password_reset_form.html', email_template_name='authenticate/password_reset_email.html'), name='password_reset'),
    path('password_reset_done/', auth_views.PasswordResetDoneView.as_view(template_name='authenticate/email_confirm.html'), name='password_reset_done'),
    path('password_reset_confirm/<uidb64>/<token>/', CustomPasswordResetConfirmView.as_view(template_name='authenticate/new_pass.html'), name='reset'),
    path('password_reset_complete/', auth_views.PasswordResetCompleteView.as_view(template_name='authenticate/password_reset_complete.html'), name='password_reset_complete'),
]

