from django.conf import settings
from django.contrib import messages
from decimal import Decimal
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.db.models import Sum, F, DecimalField
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from functools import wraps
from .forms import FeedbackForm, LoginForm, SignUpForm, OTPVerificationForm
from .models import Announcement, CartItem, Category, Feedback, Product, WishlistItem, PendingSignup, Customer, Order, OrderItem
import random


def _current_customer(request):
    customer_id = request.session.get('customer_id')
    if not customer_id:
        return None
    return Customer.objects.filter(id=customer_id, is_active=True).first()


def customer_login_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        customer = _current_customer(request)
        if not customer:
            messages.warning(request, 'Please sign in first.')
            return redirect(f"{reverse('login')}?next={request.path}")
        request.customer = customer
        return view_func(request, *args, **kwargs)
    return _wrapped

@never_cache
@ensure_csrf_cookie
def home(request):
    products = Product.objects.filter(is_active=True)
    categories = Category.objects.all()
    announcements = Announcement.objects.filter(is_active=True).order_by('-created_at')
    approved_feedbacks = Feedback.objects.filter(is_approved=True).order_by('-created_at')[:6]
    wishlist_product_ids = []
    cart_count = 0
    customer = _current_customer(request)
    if customer:
        wishlist_product_ids = list(
            WishlistItem.objects.filter(customer=customer).values_list('product_id', flat=True)
        )
        cart_count = CartItem.objects.filter(customer=customer).aggregate(
            total=Coalesce(Sum('quantity'), 0)
        )['total']
    return render(request, 'florista/home.html', {
        'products': products,
        'products_search_data': [
            {
                'id': p.id,
                'name': p.name,
                'type': p.category.name,
                'price': f"Rs. {p.price}",
            }
            for p in products
        ],
        'categories': categories,
        'announcements': announcements,
        'feedback_form': FeedbackForm(),
        'approved_feedbacks': approved_feedbacks,
        'wishlist_product_ids': wishlist_product_ids,
        'cart_count': cart_count,
        'customer': customer,
        'customer_authenticated': bool(customer),
    })


def _safe_next_url(request, default='/'):
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        return next_url
    return default


def _send_signup_otp(username, email, password_hash):
    PendingSignup.objects.filter(email__iexact=email, is_used=False).update(is_used=True)
    code = f"{random.randint(100000, 999999)}"
    PendingSignup.objects.create(
        username=username,
        email=email,
        password_hash=password_hash,
        code=code,
    )
    subject = 'Florista Email Verification OTP'
    body = (
        f"Hello {username},\n\n"
        f"Welcome to Florista.\n\n"
        f"Your one-time verification code is: {code}\n"
        f"This code is valid for 2 minutes.\n\n"
        f"For your security, do not share this code with anyone.\n\n"
        f"Warm regards,\n"
        f"Team Florista"
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
    return code


@never_cache
@ensure_csrf_cookie
def signup_view(request):
    if _current_customer(request):
        return redirect('home')
    form = SignUpForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        username = form.cleaned_data['username'].strip()
        email = form.cleaned_data['email'].strip().lower()
        password_hash = make_password(form.cleaned_data['password1'])
        try:
            _send_signup_otp(username, email, password_hash)
            messages.success(request, 'OTP email sent. Your account will be created after verification.')
        except Exception as exc:
            latest_pending = PendingSignup.objects.filter(email__iexact=email, is_used=False).order_by('-created_at').first()
            debug_hint = ''
            if getattr(settings, 'DEV_SHOW_OTP_ON_SCREEN', False) and latest_pending:
                debug_hint = f' Your OTP is: {latest_pending.code}'
            messages.warning(
                request,
                f'OTP email could not be sent. Error: {exc}.{debug_hint}'
            )
        return redirect(f"{reverse('verify_otp')}?email={email}")
    return render(request, 'florista/signup.html', {'form': form, 'next_url': _safe_next_url(request)})


@never_cache
@ensure_csrf_cookie
def login_view(request):
    if _current_customer(request):
        return redirect('home')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if PendingSignup.objects.filter(email__iexact=email, is_used=False).exists():
            messages.warning(request, 'Your account is not verified yet. Please verify OTP.')
            return redirect(f"{reverse('verify_otp')}?email={email}")
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        customer = form.get_user()
        request.session['customer_id'] = customer.id
        messages.success(request, 'Logged in successfully.')
        return redirect(_safe_next_url(request))
    return render(request, 'florista/login.html', {'form': form, 'next_url': _safe_next_url(request)})


@never_cache
@ensure_csrf_cookie
def verify_otp_view(request):
    initial_email = request.GET.get('email', '')
    form = OTPVerificationForm(request.POST or None, initial={'email': initial_email})
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email'].strip().lower()
        code = form.cleaned_data['code'].strip()
        if Customer.objects.filter(email__iexact=email).exists():
            messages.info(request, 'This email is already verified. Please sign in.')
            return redirect('login')
        otp = PendingSignup.objects.filter(email__iexact=email, code=code, is_used=False).order_by('-created_at').first()
        if not otp or otp.expires_at < timezone.now():
            messages.error(request, 'OTP is invalid or expired. Please resend the code.')
            return redirect(f"{reverse('verify_otp')}?email={email}")

        if Customer.objects.filter(username__iexact=otp.username).exists():
            messages.error(request, 'This username is no longer available. Please sign up again.')
            otp.is_used = True
            otp.save(update_fields=['is_used'])
            return redirect('signup')

        Customer.objects.create(
            username=otp.username,
            email=otp.email.lower(),
            password_hash=otp.password_hash,
            is_active=True,
        )
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        PendingSignup.objects.filter(email__iexact=email, is_used=False).update(is_used=True)
        messages.success(request, 'Email verified successfully. You can now sign in.')
        return redirect('login')
    return render(request, 'florista/verify_otp.html', {'form': form, 'initial_email': initial_email})


@never_cache
def resend_otp_view(request):
    if request.method != 'POST':
        return redirect('signup')
    email = request.POST.get('email', '').strip().lower()
    if Customer.objects.filter(email__iexact=email).exists():
        messages.info(request, 'This account is already verified. You can sign in.')
        return redirect('login')
    pending = PendingSignup.objects.filter(email__iexact=email, is_used=False).order_by('-created_at').first()
    if not pending:
        messages.error(request, 'No pending signup found for this email. Please sign up again.')
        return redirect('signup')
    try:
        _send_signup_otp(pending.username, pending.email.lower(), pending.password_hash)
        messages.success(request, 'A new OTP has been sent to your email.')
    except Exception as exc:
        debug_hint = ''
        latest_pending = PendingSignup.objects.filter(email__iexact=email, is_used=False).order_by('-created_at').first()
        if getattr(settings, 'DEV_SHOW_OTP_ON_SCREEN', False) and latest_pending:
            debug_hint = f' Your OTP is: {latest_pending.code}'
        messages.error(request, f'OTP email could not be sent. Error: {exc}.{debug_hint}')
    return redirect(f"{reverse('verify_otp')}?email={email}")


def logout_view(request):
    if request.method == 'POST':
        request.session.pop('customer_id', None)
        messages.success(request, 'Logged out successfully.')
    return redirect('home')


@customer_login_required
def add_to_cart(request, product_id):
    if request.method != 'POST':
        return redirect('home')
    product = get_object_or_404(Product, id=product_id, is_active=True)
    cart_item, created = CartItem.objects.get_or_create(customer=request.customer, product=product)
    if not created:
        cart_item.quantity += 1
        cart_item.save(update_fields=['quantity'])
    messages.success(request, f'{product.name} added to cart.')
    return redirect(request.POST.get('next', 'home'))


@customer_login_required
def cart_view(request):
    cart_items = CartItem.objects.filter(customer=request.customer).select_related('product').order_by('-created_at')
    cart_total = cart_items.aggregate(
    total=Coalesce(
        Sum(
            F('quantity') * F('product__price'),
            output_field=DecimalField()
        ),
        Decimal('0.00'),
        output_field=DecimalField()
    )
)['total']
    return render(request, 'florista/cart.html', {'cart_items': cart_items, 'cart_total': cart_total})


@customer_login_required
def remove_from_cart(request, item_id):
    if request.method == 'POST':
        item = get_object_or_404(CartItem, id=item_id, customer=request.customer)
        item.delete()
        messages.success(request, 'Item removed from cart.')
    return redirect('cart')


@customer_login_required
def update_cart_quantity(request, item_id):
    if request.method != 'POST':
        return redirect('cart')
    item = get_object_or_404(CartItem, id=item_id, customer=request.customer)
    action = request.POST.get('action')
    if action == 'increase':
        item.quantity += 1
        item.save(update_fields=['quantity'])
    elif action == 'decrease':
        item.quantity -= 1
        if item.quantity <= 0:
            item.delete()
        else:
            item.save(update_fields=['quantity'])
    return redirect('cart')


@customer_login_required
def toggle_wishlist(request, product_id):
    if request.method != 'POST':
        return redirect('home')
    product = get_object_or_404(Product, id=product_id, is_active=True)
    item = WishlistItem.objects.filter(customer=request.customer, product=product)
    if item.exists():
        item.delete()
        messages.success(request, f'{product.name} removed from favourites.')
    else:
        WishlistItem.objects.create(customer=request.customer, product=product)
        messages.success(request, f'{product.name} added to favourites.')
    return redirect(request.POST.get('next', 'home'))


@customer_login_required
def wishlist_view(request):
    wishlist_items = WishlistItem.objects.filter(customer=request.customer).select_related('product').order_by('-created_at')
    return render(request, 'florista/wishlist.html', {'wishlist_items': wishlist_items})


def submit_feedback(request):
    if request.method != 'POST':
        return redirect('home')

    form = FeedbackForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Please fill all feedback fields correctly.')
        return redirect('home')

    feedback = form.save(commit=False)
    customer = _current_customer(request)
    if customer:
        feedback.customer = customer
    feedback.save()

    subject = f'New Website Feedback from {feedback.name}'
    body = (
        f'Name: {feedback.name}\n'
        f'Email: {feedback.email}\n'
        f'Rating: {feedback.rating}/5\n\n'
        f'Message:\n{feedback.message}\n'
    )
    recipient = getattr(settings, 'FEEDBACK_NOTIFICATION_EMAIL', 'kainatkabeer.bs.it@gmail.com')
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False)
        messages.success(request, 'Feedback submitted and email notification sent successfully.')
    except Exception:
        messages.warning(
            request,
            'Feedback saved, but email notification could not be sent. Please set EMAIL_HOST_PASSWORD (Gmail App Password).'
        )

    return redirect('home')

@customer_login_required
def checkout_view(request):

    cart_items = CartItem.objects.filter(customer=request.customer)

    if not cart_items.exists():
        messages.warning(request, "Your cart is empty.")
        return redirect('cart')

    total = sum(item.product.price * item.quantity for item in cart_items)

    if request.method == "POST":

        order = Order.objects.create(
            customer=request.customer,
            full_name=request.POST.get('full_name'),
            phone=request.POST.get('phone'),
            address=request.POST.get('address'),
            city=request.POST.get('city'),
            payment_method=request.POST.get('payment_method'),
            total_amount=total
        )

        order_items_text = ""

        for item in cart_items:

            OrderItem.objects.create(
                order=order,
                product=item.product,
                quantity=item.quantity,
                price=item.product.price
            )

            order_items_text += (
                f"{item.product.name} x {item.quantity} "
                f"= Rs. {item.product.price * item.quantity}\n"
            )

# EMAIL TO CUSTOMER
        subject = f"🌸 Florista Order Confirmation #{order.id}"

        body = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
          🌺 FLORISTA ORDER CONFIRMATION 🌺
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Hello {order.full_name}! 🎀

Your beautiful order has been placed successfully! 🌷

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 ORDER DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Order ID:    #{order.id}
City:        {order.city}
Payment:     {order.get_payment_method_display()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🛒 ITEMS ORDERED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{order_items_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 TOTAL AMOUNT: Rs. {order.total_amount}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Thank you for choosing Florista! 🌸
Your flowers are being prepared with love.

With warm regards,
🌷 Team Florista

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """

        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [request.customer.email],
            fail_silently=True
        )

        cart_items.delete()

        messages.success(request, "Order placed successfully!")
        return redirect('orders')

    return render(request, 'florista/checkout.html', {
        'cart_items': cart_items,
        'total': total
    })
    
    
    
@customer_login_required
def my_orders_view(request):

    orders = Order.objects.filter(
        customer=request.customer
    ).order_by('-created_at')

    return render(request, 'florista/orders.html', {
        'orders': orders
    })    



@customer_login_required
def cancel_order_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, customer=request.customer)

    if order.status in ['shipped', 'delivered']:
        messages.error(request, "This order cannot be cancelled.")
        return redirect('orders')

    order.status = 'cancelled'
    order.cancelled_at = timezone.now()
    order.save()

    messages.success(request, f"Order #{order.id} has been cancelled.")
    return redirect('orders')