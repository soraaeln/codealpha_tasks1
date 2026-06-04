from django import forms
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from .models import Feedback, PendingSignup, Customer


class SignUpForm(forms.Form):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'required': True, 'autocomplete': 'email'}))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'required': True, 'autocomplete': 'username'}))
    password1 = forms.CharField(widget=forms.PasswordInput(attrs={'required': True, 'autocomplete': 'new-password', 'minlength': 8}))
    password2 = forms.CharField(widget=forms.PasswordInput(attrs={'required': True, 'autocomplete': 'new-password', 'minlength': 8}))

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if Customer.objects.filter(email__iexact=email).exists():
            raise ValidationError('An account with this email already exists. Please sign in.')
        if PendingSignup.objects.filter(email__iexact=email, is_used=False).exists():
            raise ValidationError('An OTP verification is already pending for this email. Please verify or resend OTP.')
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if Customer.objects.filter(username__iexact=username).exists():
            raise ValidationError('This username is already taken.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError('Passwords do not match.')
        if password1:
            validate_password(password1)
        return cleaned_data


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={'required': True, 'autocomplete': 'email', 'placeholder': 'you@example.com'}
        )
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={'required': True, 'autocomplete': 'current-password'}))

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        password = self.cleaned_data.get('password')

        if not email or not password:
            raise ValidationError('Email and password are required.')

        customer = Customer.objects.filter(email__iexact=email, is_active=True).first()
        if not customer:
            raise ValidationError('No account is registered with this email. Please sign up first.')

        if not check_password(password, customer.password_hash):
            raise ValidationError('Invalid email or password.')
        self.user_cache = customer
        return self.cleaned_data

    def get_user(self):
        return self.user_cache


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ('name', 'email', 'rating', 'message')


class OTPVerificationForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={'required': True, 'autocomplete': 'email'}))
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={'required': True, 'autocomplete': 'one-time-code', 'placeholder': '6-digit OTP'})
    )
